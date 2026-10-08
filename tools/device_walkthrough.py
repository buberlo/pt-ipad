#!/usr/bin/env python3
"""Run the pinned scripted FULL route in the foreground under one bounded iPad lease.

This is a scripted evidence capture, not touch, microphone, visual or performance
acceptance. It never takes over an existing game process or silently renews a lease.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import signal
import shutil
import stat
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit
import uuid
import wave

from summarize_present_trace import summarize, TraceError

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "com.konradkern.pt.native"
DEVELOPER = "/Applications/Xcode.app/Contents/Developer"
DEVICECTL = str(Path(DEVELOPER) / "usr/bin/devicectl")
CLEANUP_RESERVE = 120
MAX_LEASE_SECONDS = 35 * 60
STARTUP_LIMIT_SECONDS = 90
FOREGROUND_READY = "700 smenu 0\n700 sexpect menu 0\n700 sstep 15\n"
RUNTIME_VARIANT = "foreground-full-native-rate1-v1"
F120_WAIT = "700 sdemo gc_p02_080\n700 swait 2\n700 sstep 15\n"
F160_WAIT = "700 sdemo gc_p05_010\n700 swait 2\n"
ROUTE_END_GRACE_SECONDS = 30


class WalkthroughError(ValueError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    if not isinstance(value, str):
        raise WalkthroughError("lease timestamp is missing")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise WalkthroughError("lease timestamp lacks a timezone")
    return result


def lease_identity(record, thread, parent_pid, now=None, teardown=False):
    """Validate an actual direct-child command lease; return immutable identity/deadline."""
    now = now or utc_now()
    if not thread or not isinstance(record, dict):
        raise WalkthroughError("a thread and an explicit lease record are required")
    command = record.get("commandLease")
    if (record.get("owner") != "pt-native" or record.get("threadId") != thread or
            not isinstance(command, dict) or command.get("wrapperPid") != parent_pid or
            not isinstance(command.get("token"), str) or not command["token"]):
        raise WalkthroughError("this process is not the direct child of its own PT command lease")
    state = record.get("status", "")
    if not teardown and (record.get("deviceWorkPaused", False) is not False or not isinstance(state, str) or
            "paused" in state.lower() or state.lower().startswith("user-stopped") or state.lower() == "stopped"):
        raise WalkthroughError("device work is paused")
    if not teardown and "allowedOwners" in record and (not isinstance(record["allowedOwners"], list) or "pt-native" not in record["allowedOwners"]):
        raise WalkthroughError("PT is not an allowed device owner")
    seconds = command.get("timeoutSeconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or not 0 < seconds <= MAX_LEASE_SECONDS:
        raise WalkthroughError("walkthrough lease must be bounded to at most 35 minutes")
    claimed, reserved = timestamp(command.get("claimedAt")), timestamp(record.get("reservedUntil"))
    deadline = min(claimed.timestamp() + seconds, reserved.timestamp())
    if claimed > now or deadline <= now.timestamp():
        raise WalkthroughError("lease is future-dated or expired")
    return (command["token"], claimed.isoformat(), reserved.isoformat(), seconds), deadline


def read_lease(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
            raise WalkthroughError("lease record is not a bounded regular file")
        return json.loads(source.read(1024 * 1024 + 1))


def local_device_path(value):
    if not isinstance(value, str) or not value:
        raise WalkthroughError("device command did not return an absolute path")
    if value.startswith("file:"):
        url = urlsplit(value)
        if url.scheme != "file" or url.netloc not in ("", "localhost") or url.query or url.fragment:
            raise WalkthroughError("unexpected device file URL")
        value = unquote(url.path)
    if (not value.startswith("/") or any(ord(c) < 32 for c in value) or "\\" in value or
            any(part in (".", "..") for part in value.split("/"))):
        raise WalkthroughError("unsafe returned device path")
    return PurePosixPath(value)


def copied_destination(payload, relative):
    result = payload.get("result", {})
    if result.get("domain") != "appDataContainer" or result.get("domainIdentifier") != BUNDLE:
        raise WalkthroughError("copy result does not identify the PT data container")
    values = [result[key] for key in ("destination", "path") if key in result]
    if not values:
        raise WalkthroughError("copy result lacks its actual destination")
    paths = [local_device_path(value) for value in values]
    if any(path != paths[0] for path in paths):
        raise WalkthroughError("copy result has conflicting destinations")
    expected = PurePosixPath(relative)
    if paths[0].parts[-len(expected.parts):] != expected.parts:
        raise WalkthroughError("copy landed outside the requested session directory")
    return paths[0]


def running_processes(payload):
    rows = payload.get("result", {}).get("runningProcesses")
    if not isinstance(rows, list):
        raise WalkthroughError("process query returned no valid process list")
    for row in rows:
        if not isinstance(row, dict) or type(row.get("processIdentifier")) is not int or row["processIdentifier"] <= 0:
            raise WalkthroughError("malformed process identity")
    return rows


def pt_executable(value):
    try:
        path = local_device_path(value)
        return path.name == "pt" and path.parent.name == "pt.app"
    except WalkthroughError:
        return False


def owned_process(rows, identity):
    """Never treat a reused PID with another executable as the launched game."""
    for row in rows:
        if row["processIdentifier"] == identity["pid"]:
            if not row.get("executable"):
                raise WalkthroughError("matching process PID has no executable identity; disappearance is unconfirmed")
            local_device_path(row["executable"])
            if row.get("executable") != identity["executable"]:
                return False
            if row.get("auditToken") is not None and identity.get("audit_token") is not None:
                return row["auditToken"] == identity["audit_token"]
            return True
    return False


def launched_identity(payload, arguments, before_pids):
    result = payload.get("result", {})
    options, process = result.get("launchOptions", {}), result.get("process", {})
    if (options.get("arguments") != arguments or options.get("activatedWhenStarted") is not True or
            options.get("terminateExistingInstances") is not False or
            type(process.get("processIdentifier")) is not int or process["processIdentifier"] <= 0 or
            process["processIdentifier"] in before_pids or not pt_executable(process.get("executable"))):
        raise WalkthroughError("launch returned no unambiguous new PT process identity")
    invocation = payload.get("info", {}).get("arguments", [])
    if BUNDLE not in invocation:
        raise WalkthroughError("launch response does not identify the requested PT bundle")
    return {"pid": process["processIdentifier"], "executable": process["executable"], "audit_token": process.get("auditToken")}


def load_pinned_route():
    upstream = ROOT / "upstream/pt-pc"
    expected = json.loads((ROOT / "source-lock.json").read_text())["pt_pc"]["commit"]
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=upstream, text=True).strip()
    if git("rev-parse", "HEAD") != expected or git("status", "--porcelain"):
        raise WalkthroughError("pinned upstream must match source-lock.json and be clean")
    source = upstream / "tools/walkthrough.py"
    spec = importlib.util.spec_from_file_location("pt_pinned_walkthrough", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scenario = module.SCENARIOS["full"]
    if scenario["start_floor"] is not None or scenario["route"] != module.FULL:
        raise WalkthroughError("upstream FULL scenario changed unexpectedly")
    files = [source, *(module.ROUTES / f"{name}.txt" for name in sorted(set(module.FULL) | {"speedrun_boot", "padboot"}))]
    hashes = {str(path.relative_to(upstream)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    return module, {"upstream_commit": expected, "route": list(module.FULL), "input_sha256": hashes,
                    "foreground_preface": {"upstream_route": "speedrun_boot", "readiness_commands": FOREGROUND_READY.splitlines(),
                                           "readiness_reference": "tests/walkthrough/padboot.txt",
                                           "purpose": "Dismiss the real first-boot options menu with a scripted Escape key, then wait for StartGame before FULL navigation.",
                                           "physical_input_verified": False},
                    "checkpoint_patterns": scenario["expect"]}


def foreground_variant(module, shots=None):
    """Add read-only synchronization to the upstream route for demo-rate 1."""
    if module.FULL.count("f120") != 1 or module.FULL.count("f160") != 1:
        raise WalkthroughError("FULL route synchronization anchors changed")
    prefix = module.load_route(["speedrun_boot"], shots) + FOREGROUND_READY
    pieces, insertions = [], []
    for index, name in enumerate(module.FULL):
        piece = module.load_route([name], shots)
        if name == "f120":
            if module.FULL[index + 1:index + 2] != ["start"]:
                raise WalkthroughError("f120 is no longer followed by the expected restart route")
            piece += F120_WAIT
            insertions.append({"route_index": index, "route_part": name, "placement": "after the complete f120 part, before restart navigation",
                               "commands": F120_WAIT.splitlines()})
        elif name == "f160":
            anchor = "700 swait 400\n"
            if piece.count(anchor) != 1 or piece.count("700 ssteps 10\n") != 1 or piece.index(anchor) > piece.index("700 ssteps 10\n"):
                raise WalkthroughError("f160 intro/ten-step synchronization anchor changed")
            piece = piece.replace(anchor, anchor + F160_WAIT)
            insertions.append({"route_index": index, "route_part": name, "placement": "after existing swait400, before the ten-step puzzle sequence",
                               "commands": F160_WAIT.splitlines()})
        pieces.append(piece)
    original = module.load_route(module.FULL, shots)
    script = prefix + "".join(pieces)
    if not script.endswith("700 slog\n"):
        raise WalkthroughError("FULL no longer ends in its observable slog command")
    return script, {"name": RUNTIME_VARIANT, "demo_rate": 1,
                    "original_rendered_full_sha256": hashlib.sha256(original.encode()).hexdigest(),
                    "foreground_prefix_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
                    "rendered_variant_sha256": hashlib.sha256(script.encode()).hexdigest(),
                    "insertions": insertions, "original_commands_preserved": True,
                    "inserted_commands_change_game_flags_or_progression": False,
                    "expected_sequential_log_commands": len(re.findall(r"^700 slog$", script, re.MULTILINE)),
                    "completion_observation": "Count existing sequential slog outputs; the pinned FULL tail ends with the last slog. No completion command is injected."}


def foreground_route(module, shots=None):
    return foreground_variant(module, shots)[0]


def startup_failure(observed, elapsed):
    first_game = observed["first_game_log_seconds"]
    if first_game is not None and first_game > STARTUP_LIMIT_SECONDS:
        return f"StartGame occurred at log second {first_game:.3f}, after the {STARTUP_LIMIT_SECONDS}-second startup limit"
    if elapsed >= STARTUP_LIMIT_SECONDS and first_game is None:
        return f"StartGame was not observed within {STARTUP_LIMIT_SECONDS} seconds; menu/loading time cannot qualify as gameplay"
    return None


def inspect_route_log(text, patterns, expected_log_commands=0):
    lines = text.splitlines()
    position, checkpoints = 0, []
    for pattern in patterns:
        expression = re.compile(pattern)
        found = next((i for i in range(position, len(lines)) if expression.search(lines[i])), None)
        checkpoints.append({"pattern": pattern, "line": found + 1 if found is not None else None,
                            "observed": found is not None})
        if found is not None:
            position = found + 1
    failures = []
    expression = re.compile(r"input script:.*(?:gave up|stuck at|shot .*dropped|next shot dropped|cannot open)|input script:.*expectations, [1-9][0-9]* failed")
    for i, line in enumerate(lines):
        if expression.search(line):
            failures.append({"line": i + 1, "message": line})
    runtime_errors = [{"line": i + 1, "message": line} for i, line in enumerate(lines)
                      if re.search(r"^\[\s*[0-9]+(?:\.[0-9]+)?\]\s+error\b", line) or
                      ("script:" in line and "failed or missing" in line)]
    backgrounds = [{"line": i + 1, "message": line} for i, line in enumerate(lines)
                   if "iPad lifecycle: suspending" in line or "focus: game frozen in the background" in line]
    transitions = []
    first_game_seconds = ending_seconds = final_log_seconds = route_commands_exhausted_seconds = None
    sequential_logs = 0
    for i, line in enumerate(lines):
        clock = re.match(r"^\[\s*([0-9]+(?:\.[0-9]+)?)\]", line)
        seconds = float(clock[1]) if clock else None
        if seconds is not None:
            final_log_seconds = seconds
            if re.search(r"input script seq frame \d+: step \d+ floor ", line):
                sequential_logs += 1
                if expected_log_commands > 0 and sequential_logs == expected_log_commands:
                    route_commands_exhausted_seconds = seconds
            if first_game_seconds is None and "controller: ChangeGameStep(StartGame)" in line:
                first_game_seconds = seconds
            if ending_seconds is None and ("floor: NextFloor f160 -> ending" in line or "controller: ChangeGameStep(GotoEnding)" in line):
                ending_seconds = seconds
        match = re.search(r"floor: NextFloor (\w+) -> (\w+)", line)
        if match:
            transitions.append({"line": i + 1, "from": match[1], "to": match[2]})
    return {"checkpoints": checkpoints, "checkpoints_complete": bool(patterns) and all(x["observed"] for x in checkpoints),
            "route_failures": failures, "runtime_errors": runtime_errors, "background_events": backgrounds,
            "latest_floor": transitions[-1]["to"] if transitions else None, "floor_transitions": transitions,
            "first_game_log_seconds": first_game_seconds, "ending_transition_log_seconds": ending_seconds,
            "sequential_log_commands_observed": sequential_logs,
            "route_commands_exhausted_log_seconds": route_commands_exhausted_seconds,
            "final_log_seconds": final_log_seconds,
            "pre_ending_log_span_seconds": (ending_seconds - first_game_seconds)
                if ending_seconds is not None and first_game_seconds is not None else None,
            "after_ending_transition_log_span_seconds": (final_log_seconds - ending_seconds)
                if ending_seconds is not None and final_log_seconds is not None else None,
            "shutdown_logged": any("game: stopped" in line for line in lines),
            "trace_write_ok_logged": bool(re.search(r"display trace:.*write_ok=(?:true|1)", text))}


def route_stop_reason(observed):
    if observed["checkpoints_complete"]:
        return "full_route_milestones_observed"
    exhausted = observed.get("route_commands_exhausted_log_seconds")
    end = observed.get("final_log_seconds")
    if exhausted is not None and end is not None and end - exhausted >= ROUTE_END_GRACE_SECONDS:
        return "route_commands_exhausted_without_complete_ending"
    return None


def trace_evidence(path):
    report = summarize(path, target_fps=30, warmup_seconds=30, window_seconds=60)
    longest = max((segment["observed_interval_seconds"] for segment in report["segments"]), default=0)
    return {"summary": report, "longest_retained_segment_seconds": longest,
            "has_20_minute_contiguous_actual_intervals": longest >= 1200 and not report["trace_discontinuity"],
            "acceptance": False}


def voice_metadata(path):
    with wave.open(str(path), "rb") as source:
        frames, rate = source.getnframes(), source.getframerate()
        if (source.getnchannels() != 1 or source.getsampwidth() != 2 or rate != 16000 or
                source.getcomptype() != "NONE" or not 0 < frames <= rate * 600):
            raise WalkthroughError("--voice-input requires 16 kHz mono PCM16 WAV, longer than zero and at most ten minutes")
        # Reject a truncated file whose header advertises more data than it contains.
        actual = 0
        while data := source.readframes(65536):
            actual += len(data)
        if actual != frames * 2:
            raise WalkthroughError("--voice-input has truncated PCM data")
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while data := source.read(1024 * 1024):
            digest.update(data)
    return {"mode": "prerecorded_wav", "sha256": digest.hexdigest(), "seconds": frames / rate,
            "sample_rate": rate, "channels": 1, "sample_bytes": 2, "physical_microphone": False}


class Capture:
    def __init__(self, args):
        self.args = args
        self.record = Path(os.environ.get("PT_IPAD_LEASE_RECORD", str(ROOT.parent / "madeira/installation/ipad-access.json")))
        self.thread, self.parent = os.environ.get("CODEX_THREAD_ID"), os.getppid()
        self.identity, self.deadline = lease_identity(read_lease(self.record), self.thread, self.parent)
        self.receipt_token = os.environ.get("PT_DEVICE_LEASE_TOKEN")
        if not self.receipt_token or self.receipt_token != self.identity[0]:
            raise WalkthroughError("cleanup-receipt lease token is missing or does not match this command lease")
        # Also enforce a monotonic bound if wall time changes during this invocation.
        self.monotonic_deadline = time.monotonic() + self.deadline - time.time()
        self.env = dict(os.environ, DEVELOPER_DIR=DEVELOPER)
        self.cancelled = False
        self.command_index = 0
        self.process = None
        self.launch_attempted = False
        self.launch_json = None
        self.before_pids = set()
        self.cleanup_deadline = None
        self.teardown = False
        self.relative = PurePosixPath("Documents/PTDiagnostics") / ("pt-" + uuid.uuid4().hex)
        self.report = {"schema": "pt-ipad-device-walkthrough-v1", "device": args.device,
                       "session_directory": str(self.relative), "requested_seconds": args.seconds,
                       "lease_deadline": datetime.fromtimestamp(self.deadline, timezone.utc).isoformat(),
                       "capture_started": utc_now().isoformat(), "captures": [], "errors": [],
                       "cleanup_confirmed": False, "acceptance": False,
                       "scripted_navigation": True, "injected_voice": True,
                       "physical_touch_verified": False, "physical_microphone_verified": False,
                       "foreground_requested": True, "foreground_visually_reviewed": False,
                       "limitations": ["Process presence alone does not prove foreground visibility.",
                                       "Route screenshot capture can introduce real presentation stalls; retained intervals are not edited to remove them.",
                                       "Outer lease wrapper has a two-second forced-stop grace; abrupt wrapper termination can prevent cleanup confirmation."]}

    def cleanup_receipt(self):
        if not self.report["cleanup_confirmed"]:
            return
        path = self.args.output / "cleanup.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"lease_token": self.receipt_token, "cleanup_confirmed": True}) + "\n")
        temporary.replace(path)

    def persist(self):
        path = self.args.output / "walkthrough.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.report, indent=2) + "\n")
        temporary.replace(path)

    def remaining(self, teardown=False):
        identity, deadline = lease_identity(read_lease(self.record), self.thread, self.parent, teardown=teardown)
        if identity != self.identity or deadline != self.deadline:
            raise WalkthroughError("lease identity changed; device operations refused")
        return min(self.deadline - time.time(), self.monotonic_deadline - time.monotonic())

    def command(self, name, operation, extra=(), timeout=30, cleanup=False):
        if self.cancelled and not cleanup:
            raise KeyboardInterrupt("walkthrough interrupted")
        teardown = cleanup and self.teardown
        if teardown and operation not in (["info", "processes"], ["process", "terminate"]):
            raise WalkthroughError("only exact-process teardown is permitted during cleanup")
        remaining = self.remaining(teardown=teardown) - (0 if cleanup else CLEANUP_RESERVE)
        if cleanup and self.cleanup_deadline is not None:
            remaining = min(remaining, self.cleanup_deadline - time.monotonic())
        allowance = min(timeout, math.floor(remaining - 3))
        if allowance < 1:
            raise WalkthroughError("lease cleanup reserve reached; no further normal device operation")
        self.command_index += 1
        stem = self.args.output / f"{self.command_index:03d}-{name}"
        json_path = stem.with_suffix(".json")
        if name == "launch":
            self.launch_attempted = True
            self.launch_json = json_path
        cmd = [DEVICECTL, "device", *operation, "--device", self.args.device,
               "--timeout", str(allowance), "--json-output", str(json_path), *map(str, extra)]
        try:
            result = subprocess.run(cmd, env=self.env, capture_output=True, text=True, timeout=allowance + 2)
            stem.with_suffix(".log").write_text(result.stdout + result.stderr)
        except subprocess.TimeoutExpired as error:
            stem.with_suffix(".log").write_text(f"Host command timeout after {allowance + 2}s\n")
            raise WalkthroughError(f"{name}: device command timed out") from error
        print(f"{name}: exit {result.returncode}", flush=True)
        if result.returncode:
            raise WalkthroughError(f"{name}: exit {result.returncode}; see {stem.name}.log")
        payload = json.loads(json_path.read_text())
        if payload.get("info", {}).get("outcome") not in (None, "success"):
            raise WalkthroughError(f"{name}: device command did not report success")
        return payload

    def processes(self, label, cleanup=False):
        return running_processes(self.command(label, ["info", "processes"], cleanup=cleanup, timeout=15))

    def copy_from(self, label, source, destination, cleanup=False, timeout=25):
        return self.command(label, ["copy", "from"],
                            ["--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                             "--source", source, "--destination", destination], cleanup=cleanup, timeout=timeout)

    def cleanup_process(self):
        if self.launch_attempted and not self.process:
            # A launch timeout can still have created the app. Trust only the retained
            # result for this exact invocation, never a newly observed unrelated PID.
            if self.launch_json and self.launch_json.is_file():
                try:
                    self.process = launched_identity(json.loads(self.launch_json.read_text()),
                                                     self.report["launch_arguments"], self.before_pids)
                    self.report["process"] = self.process
                    self.report["launch_identity_recovered"] = True
                except (OSError, ValueError, KeyError):
                    pass
            if not self.process:
                rows = self.processes("cleanup-ambiguous-launch", cleanup=True)
                if any(not row.get("executable") or pt_executable(row.get("executable")) for row in rows):
                    raise WalkthroughError("launch identity is ambiguous and PT absence cannot be established; reservation must remain for explicit recovery")
                self.report["cleanup_confirmed"] = True
                self.report["cleanup_reason"] = "No PT process exists after ambiguous launch; no PID was terminated"
                return
        if not self.process:
            self.report["cleanup_confirmed"] = True
            return
        rows = self.processes("cleanup-before", cleanup=True)
        if owned_process(rows, self.process):
            try:
                self.command("terminate-owned", ["process", "terminate"], ["--pid", self.process["pid"]], cleanup=True, timeout=8)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                # The request may have succeeded remotely despite a failed host reply.
                # Only a subsequent process snapshot can establish whether cleanup finished.
                self.report["termination_request_error"] = str(error)
        for attempt in range(5):
            rows = self.processes(f"cleanup-confirm-{attempt}", cleanup=True)
            if not owned_process(rows, self.process):
                self.report["cleanup_confirmed"] = True
                self.report["cleanup_finished"] = utc_now().isoformat()
                return
            if attempt == 2:
                # Rechecked the exact executable/PID immediately before escalation.
                try:
                    self.command("kill-owned", ["process", "terminate"], ["--pid", self.process["pid"], "--kill"], cleanup=True, timeout=5)
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    self.report["kill_request_error"] = str(error)
            time.sleep(.25)
        raise WalkthroughError("own game process termination could not be confirmed")

    def execute(self):
        self.args.output.mkdir(parents=True, exist_ok=False)
        self.persist()
        route_metadata = {"checkpoint_patterns": []}
        started = None
        staged = False
        try:
            module, route_metadata = load_pinned_route()
            self.report["route_source"] = route_metadata
            if any(pt_executable(row.get("executable")) for row in self.processes("processes-before")):
                raise WalkthroughError("PT is already running; preserving the existing session")
            if self.args.app:
                app = self.args.app.resolve()
                info = plistlib.loads((app / "Info.plist").read_bytes())
                if info.get("CFBundleIdentifier") != BUNDLE:
                    raise WalkthroughError("--app is not the PT native bundle")
                self.report["installed_app"] = {"path": str(app), "build": info.get("CFBundleVersion"),
                                                "executable_sha256": hashlib.sha256((app / info["CFBundleExecutable"]).read_bytes()).hexdigest()}
                self.command("install", ["install", "app"], [app], timeout=100)
            local = self.args.output / "session-input"
            local.mkdir()
            (local / "shots").mkdir()
            (local / "shots/.keep").write_text("Route-owned screenshots only.\n")
            self.report["voice_input"] = {"mode": "real_microphone_default", "physical_microphone_verified": False}
            if self.args.voice_input:
                self.report["voice_input"] = voice_metadata(self.args.voice_input)
                shutil.copyfile(self.args.voice_input, local / "voice-input.wav")
                if voice_metadata(local / "voice-input.wav") != self.report["voice_input"]:
                    raise WalkthroughError("voice WAV changed while staging")
            route = local / "sessionroute.txt"
            route.write_text(foreground_route(module), encoding="utf-8")
            copied = self.command("stage-session", ["copy", "to"],
                                  ["--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                                   "--source", local, "--destination", self.relative], timeout=40)
            device_dir = copied_destination(copied, self.relative)
            variant, variant_metadata = foreground_variant(module, str(device_dir / "shots"))
            route.write_text(variant, encoding="utf-8")
            self.report["route_source"]["runtime_variant"] = variant_metadata
            self.report["route_source"]["foreground_helper_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            expected_log_commands = variant_metadata["expected_sequential_log_commands"]
            script = route.read_text()
            self.report["injected_voice"] = any(re.match(r"\d+ svoice\b", line) for line in script.splitlines())
            self.report["route_sha256"] = hashlib.sha256(route.read_bytes()).hexdigest()
            confirmed = self.command("stage-route", ["copy", "to"],
                                     ["--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                                      "--source", route, "--destination", self.relative / route.name])
            device_route = copied_destination(confirmed, self.relative / route.name)
            if device_route.parent != device_dir:
                raise WalkthroughError("route copy returned a different device container")
            staged = True
            if self.remaining() < self.args.seconds + CLEANUP_RESERVE + 20:
                raise WalkthroughError("installation/staging used the launch budget; full requested run cannot fit lease")
            before_launch = self.processes("processes-before-launch")
            self.before_pids = {row["processIdentifier"] for row in before_launch}
            if any(pt_executable(row.get("executable")) for row in before_launch):
                raise WalkthroughError("PT started during staging; preserving that session")
            child_env = {"PT_PRESENT_TRACE_PATH": str(device_dir / "present.csv"), "PT_SYSTEM_LANGUAGE": "en-US", "PT_LOG_TICKS": "1"}
            if self.args.voice_input:
                child_env["PT_VOICE_INPUT"] = str(device_dir / "voice-input.wav")
            arguments = ["--no-save", "--no-mods", "--seed", "1", "--demo-rate", "1", "--input-script", str(device_route),
                         "--log", str(device_dir / "pt.log"), "--settings", str(device_dir / "session.ini")]
            self.report["launch_arguments"] = arguments
            self.report["launch_environment"] = child_env
            launched = self.command("launch", ["process", "launch"],
                                    ["--activate", "--environment-variables", json.dumps(child_env), BUNDLE, *arguments])
            self.process = launched_identity(launched, arguments, self.before_pids)
            self.report["process"] = self.process
            self.report["launch_finished"] = utc_now().isoformat()
            started = time.monotonic()
            next_capture, next_log, next_poll = 30.0, 30.0, 5.0
            self.persist()
            while time.monotonic() - started < self.args.seconds:
                if self.cancelled:
                    raise KeyboardInterrupt("walkthrough interrupted")
                if self.remaining() < CLEANUP_RESERVE + 20:
                    raise WalkthroughError("ending run before lease cleanup reserve")
                elapsed = time.monotonic() - started
                if elapsed >= next_poll:
                    if not owned_process(self.processes(f"processes-{int(elapsed)}"), self.process):
                        self.report["process_exited_early"] = True
                        break
                    next_poll = elapsed + 15
                if elapsed >= next_log:
                    log = self.args.output / f"runtime-{int(elapsed):04d}.log"
                    self.copy_from(f"runtime-{int(elapsed)}", self.relative / "pt.log", log)
                    observed = inspect_route_log(log.read_text(errors="replace"), route_metadata["checkpoint_patterns"], expected_log_commands)
                    self.report["latest_route_observation"] = {"runtime_log": log.name, "elapsed_seconds": elapsed, "result": observed}
                    if observed["background_events"]:
                        self.report["background_events"] = observed["background_events"]
                        raise WalkthroughError("native log reports background suspension; continuous foreground run ended")
                    if reason := startup_failure(observed, elapsed):
                        self.report["startup_failure"] = reason
                        raise WalkthroughError(reason)
                    if reason := route_stop_reason(observed):
                        self.report["stop_reason"] = reason
                        self.report["stop_observation"] = {"runtime_log": log.name, "elapsed_seconds": elapsed}
                        self.persist()
                        break
                    if elapsed >= next_capture:
                        image = self.args.output / f"screen-{int(elapsed):04d}.png"
                        self.command(f"screenshot-{int(elapsed)}", ["capture", "screenshot"], ["--destination", image], timeout=15)
                        self.report["captures"].append({"elapsed_seconds": time.monotonic() - started, "image": image.name,
                                                        "runtime_log": log.name, "route_floor_from_log": observed["latest_floor"],
                                                        "foreground_pixels_reviewed": False})
                        next_capture += 120
                    next_log = (min(elapsed + 30, STARTUP_LIMIT_SECONDS)
                                if observed["first_game_log_seconds"] is None else elapsed + 30)
                    self.persist()
                time.sleep(.25)
            self.report["capture_loop_completed"] = not self.report.get("process_exited_early", False)
            self.report.setdefault("stop_reason", "process_exited" if self.report.get("process_exited_early") else "requested_duration_reached")
        except (Exception, KeyboardInterrupt) as error:
            self.report["errors"].append(str(error) or type(error).__name__)
        finally:
            self.report["host_observed_process_seconds"] = time.monotonic() - started if started is not None else 0
            self.persist()
            try:
                self.cleanup_deadline = time.monotonic() + 40
                self.teardown = True
                self.cleanup_process()
                self.cleanup_receipt()
            except (Exception, KeyboardInterrupt) as error:
                self.report["errors"].append("cleanup: " + (str(error) or type(error).__name__))
            self.cleanup_deadline = None
            self.teardown = False
            self.persist()
            if staged and not self.cancelled:
                # Stop the exact owned process before spending the remaining lease on copies.
                for name in ("pt.log", "present.csv", "shots"):
                    try:
                        self.copy_from("collect-" + name.replace(".", "-"), self.relative / name,
                                       self.args.output / name, cleanup=True, timeout=25)
                    except (Exception, KeyboardInterrupt) as error:
                        self.report["errors"].append("collection " + name + ": " + str(error))
            elif staged:
                self.report["collection_skipped"] = "Interrupted: only exact-owned process teardown is permitted; retained runtime logs/screenshots are partial evidence and final trace was not copied."
            self.report["capture_finished"] = utc_now().isoformat()
            self.persist()
        log = self.args.output / "pt.log"
        if log.is_file():
            expected = self.report.get("route_source", {}).get("runtime_variant", {}).get("expected_sequential_log_commands", 0)
            self.report["route_result"] = inspect_route_log(log.read_text(errors="replace"), route_metadata["checkpoint_patterns"], expected)
            self.report["route_result_source"] = "pt.log"
        elif "latest_route_observation" in self.report:
            self.report["route_result"] = self.report["latest_route_observation"]["result"]
            self.report["route_result_source"] = self.report["latest_route_observation"]["runtime_log"]
        trace = self.args.output / "present.csv"
        if trace.is_file():
            try:
                evidence = trace_evidence(trace)
                (self.args.output / "presentation-summary.json").write_text(json.dumps(evidence, indent=2) + "\n")
                self.report["timing"] = {key: value for key, value in evidence.items() if key != "summary"}
                # Log clocks and driver actualPresentTime have no established common
                # origin here. Do not turn an ending/menu tail into gameplay duration.
                self.report["timing"]["representative_gameplay_gate"] = "open: scene-matched actual-interval analysis and visual review required"
                self.report["timing"]["includes_ending_transition"] = self.report.get("route_result", {}).get("ending_transition_log_seconds") is not None
                flushed = self.report.get("route_result", {}).get("trace_write_ok_logged", False)
                self.report["timing"]["trace_tail_confirmed"] = flushed
                self.report["timing"]["trace_tail_qualification"] = "write_ok_logged" if flushed else "report_tail_unconfirmed: renderer did not log successful final flush/close"
            except (OSError, ValueError, TraceError) as error:
                self.report["errors"].append("presentation trace: " + str(error))
        route_result = self.report.get("route_result", {})
        self.report["progression_milestones_complete"] = route_result.get("checkpoints_complete", False)
        self.report["benchmark_coverage_accepted"] = False
        self.persist()
        if not self.report["cleanup_confirmed"] or self.report["errors"]:
            return 1
        complete = (not self.report.get("process_exited_early", False) and
                    route_result.get("checkpoints_complete", False) and not route_result.get("route_failures") and
                    not route_result.get("runtime_errors") and
                    not route_result.get("background_events") and
                    self.report.get("timing", {}).get("trace_tail_confirmed", False) and
                    self.report.get("timing", {}).get("has_20_minute_contiguous_actual_intervals", False))
        self.report["evidence_status"] = "captured_for_review" if complete else "incomplete"
        self.persist()
        return 0 if complete else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, help="explicit device identifier; no implicit device selection")
    parser.add_argument("--output", required=True, type=Path, help="new private local report directory")
    parser.add_argument("--seconds", type=int, default=1500, metavar="1200..1800")
    parser.add_argument("--app", type=Path, help="optional already-signed .app to install while holding this lease")
    parser.add_argument("--voice-input", type=Path, help="optional local 16 kHz mono PCM16 WAV; marked prerecorded, never microphone acceptance")
    parser.add_argument("--under-lease", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.device.strip() or not 1200 <= args.seconds <= 1800:
        parser.error("an explicit device and duration from 1200 to 1800 seconds are required")
    if args.output.exists():
        parser.error("--output must be a new directory")
    args.output = args.output.absolute()
    if args.app and (not args.app.is_dir() or not (args.app / "Info.plist").is_file()):
        parser.error("--app must name a signed iOS application directory")
    if args.voice_input:
        try:
            voice_metadata(args.voice_input)
        except (OSError, ValueError, wave.Error, EOFError) as error:
            parser.error(str(error))
    if not args.under_lease:
        values = list(sys.argv[1:] if argv is None else argv)
        minutes = args.seconds / 60 + 5
        return subprocess.call([sys.executable, str(ROOT / "tools/ipad_command.py"), "--minutes", str(minutes),
                                "--require-cleanup-receipt", str(args.output / "cleanup.json"), "--",
                                sys.executable, str(Path(__file__).resolve()), *values, "--under-lease"])
    capture = Capture(args)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda number, frame: setattr(capture, "cancelled", True))
    return capture.execute()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Device walkthrough refused: {error}")
