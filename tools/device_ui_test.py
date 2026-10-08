#!/usr/bin/env python3
"""One bounded physical XCTest retry, with exact-process cleanup and passive input evidence.

Requires a freshly built signed native app and signed XCTest products. Nothing is
launched without the shared lease. A successful test still leaves visual review,
interact/zoom, held-input reset, controller and microphone acceptance open.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import plistlib
import re
import signal
import subprocess
import sys
import time

from device_walkthrough import (BUNDLE, Capture, DEVELOPER, WalkthroughError,
                                copied_destination, local_device_path, owned_process, utc_now)

ROOT = Path(__file__).resolve().parents[1]
HARNESS = "com.konradkern.pt.harness"
RUNNER = "com.konradkern.pt.harness.tests.xctrunner"
EXPECTED_TEST = "PTDeviceTests/NativeInputTests/testTouchAndResume"
EXECUTABLES = {BUNDLE: "pt", HARNESS: "PTHarness", RUNNER: "PTDeviceTests-Runner"}
APP_NAMES = {BUNDLE: "pt.app", HARNESS: "PTHarness.app", RUNNER: "PTDeviceTests-Runner.app"}
XCODEBUILD = str(Path(DEVELOPER) / "usr/bin/xcodebuild")
XCRESULT = str(Path(DEVELOPER) / "usr/bin/xcresulttool")


def target_name(value):
    """Names may reject an existing process; they never authorize termination."""
    try:
        path = local_device_path(value)
        return any(path.name == exe and path.parent.name == APP_NAMES[bundle]
                   for bundle, exe in EXECUTABLES.items())
    except WalkthroughError:
        return False


def install_executable(payload, bundle):
    rows = payload.get("result", {}).get("installedApplications", [])
    selected = [row for row in rows if row.get("bundleID") == bundle]
    if len(selected) != 1:
        raise WalkthroughError("installation did not return the exact requested bundle identity")
    base = local_device_path(selected[0].get("installationURL"))
    if base.name != APP_NAMES[bundle]:
        raise WalkthroughError("unexpected installed application directory")
    return str(base / EXECUTABLES[bundle])


def installed_paths(payload):
    """Accept known CoreDevice app records, and fail closed on unknown schemas."""
    result = payload.get("result", {})
    rows = result.get("apps", result.get("applications"))
    if not isinstance(rows, list):
        raise WalkthroughError("installed-app query has an unsupported schema")
    found = {}
    for row in rows:
        if not isinstance(row, dict):
            raise WalkthroughError("malformed installed-app record")
        bundle = row.get("bundleIdentifier", row.get("bundleID"))
        if bundle not in EXECUTABLES:
            continue
        values = [row[key] for key in ("url", "installationURL") if key in row]
        paths = [local_device_path(value) for value in values]
        if not paths or any(path != paths[0] for path in paths) or paths[0].name != APP_NAMES[bundle] or bundle in found:
            raise WalkthroughError("installed-app record has an ambiguous path or identity")
        found[bundle] = str(paths[0] / EXECUTABLES[bundle])
    return found


class OwnedProcesses:
    def __init__(self, before, paths):
        self.before = set(before)
        self.paths = dict(paths)
        self.owned = {}

    def observe(self, rows, allow_new):
        for row in rows:
            pid, value = row["processIdentifier"], row.get("executable")
            if not value:
                raise WalkthroughError("process snapshot lacks executable identities; absence is unconfirmed")
            path = str(local_device_path(value))
            if pid in self.owned:
                # A changed executable/token means the old PID was reused, not
                # permission to take ownership of the replacement process.
                continue
            if path not in self.paths.values():
                if target_name(value):
                    raise WalkthroughError("test process is not attributable to a verified installed bundle path")
                continue
            if pid in self.before:
                raise WalkthroughError("preexisting test-app process must be preserved")
            if not allow_new:
                raise WalkthroughError("new test-app PID discovered while stopping; explicit recovery required")
            self.owned[pid] = {"pid": pid, "executable": path, "audit_token": row.get("auditToken")}

    def live(self, rows):
        normalized = [dict(row, executable=str(local_device_path(row["executable"]))) for row in rows]
        return [identity for identity in self.owned.values() if owned_process(normalized, identity)]


def exact_test_result(tree, summary):
    matches = []
    def walk(node, in_bundle=False):
        if not isinstance(node, dict):
            return
        in_bundle = in_bundle or (node.get("nodeType") == "UI test bundle" and node.get("name") == "PTDeviceTests")
        identifier = node.get("nodeIdentifier", "")
        identifier = identifier.removesuffix("()") if isinstance(identifier, str) else ""
        if node.get("nodeType") == "Test Case" and in_bundle and identifier in (
                EXPECTED_TEST, "NativeInputTests/testTouchAndResume"):
            matches.append({"identifier": EXPECTED_TEST, "result": node.get("result")})
        for child in node.get("children", []):
            walk(child, in_bundle)
    for node in tree.get("testNodes", []):
        walk(node)
    executed = sum(node["result"] in ("Passed", "Failed", "Expected Failure") for node in matches)
    return {"expected_test": EXPECTED_TEST, "executed_test_methods": executed, "methods": matches,
            "passed": len(matches) == 1 and matches[0]["result"] == "Passed" and
                      summary.get("failedTests") == 0 and summary.get("passedTests") == 1 and
                      summary.get("result") == "Passed",
            "summary_result": summary.get("result")}


def input_evidence(text):
    pattern = re.compile(r"input script frame (\d+): step 15 floor f010 loop \d+ feet "
                         r"\((-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\) yaw (-?[\d.]+)")
    samples = []
    for match in pattern.finditer(text):
        values = tuple(map(float, match.groups()[1:]))
        if all(math.isfinite(value) for value in values):
            samples.append((int(match[1]), *values))
    frames = [sample[0] for sample in samples]
    valid = len(samples) >= 6 and all(b > a for a, b in zip(frames, frames[1:]))
    yaw_delta = distance = 0.0
    if valid:
        for a in samples:
            for b in samples:
                yaw_delta = max(yaw_delta, abs(math.atan2(math.sin(b[4] - a[4]), math.cos(b[4] - a[4]))))
                distance = max(distance, math.hypot(b[1] - a[1], b[3] - a[3]))
    menu = re.search(r"ui: option menu opened \(pause\).*?ui: option menu closed", text, re.S) is not None
    resumed = re.search(r"iPad lifecycle: suspending.*?iPad lifecycle: foreground;", text, re.S) is not None
    errors = [line for line in text.splitlines() if re.search(r"^\[\s*[\d.]+\]\s+error\b", line)]
    gates = {"passive_gameplay_samples_valid": valid, "look_state_changed": yaw_delta >= .15,
             "position_changed": distance >= .25, "pause_closed": menu, "native_background_and_resume": resumed}
    return {"gates": gates, "passed": all(gates.values()) and not errors, "samples": len(samples),
            "yaw_delta_radians": yaw_delta, "horizontal_position_span_m": distance, "runtime_errors": errors,
            "interpretation": "State deltas during controller step15/f010 with a log-only script support the physical look/move exercise; visual review is still required.",
            "interact_verified": False, "zoom_verified": False, "held_input_reset_verified": False, "acceptance": False}


def app_info(path, bundle):
    info = plistlib.loads((path / "Info.plist").read_bytes())
    if (info.get("CFBundleIdentifier") != bundle or info.get("CFBundleExecutable") != EXECUTABLES[bundle]
            or path.name != APP_NAMES[bundle]):
        raise WalkthroughError("local XCTest/native product identity is not the expected bundle")
    return info


def prepare_products(xctestrun, native):
    value = plistlib.loads(xctestrun.read_bytes())
    target = value.get("PTDeviceTests")
    if not isinstance(target, dict) or target.get("TestHostBundleIdentifier") != RUNNER:
        raise WalkthroughError("expected a format1 PTDeviceTests XCTest product file")
    def resolve(key):
        raw = target.get(key, "")
        if not isinstance(raw, str) or not raw.startswith("__TESTROOT__/"):
            raise WalkthroughError("XCTest product must resolve relative to its known product directory")
        path = xctestrun.parent / raw[len("__TESTROOT__/"):]
        if ".." in path.parts:
            raise WalkthroughError("XCTest product path traversal")
        return path.resolve()
    products = {BUNDLE: native.resolve(), HARNESS: resolve("UITargetAppPath"), RUNNER: resolve("TestHostPath")}
    for bundle, path in products.items():
        app_info(path, bundle)
    return value, products


def resolve_testroot(value, root):
    if isinstance(value, dict):
        return {key: resolve_testroot(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_testroot(item, root) for item in value]
    return value.replace("__TESTROOT__", str(root)) if isinstance(value, str) else value


class UiCapture(Capture):
    def __init__(self, args):
        super().__init__(args)
        self.report = {"schema": "pt-ipad-ui-test-v1", "device": args.device, "acceptance": False,
                       "capture_started": utc_now().isoformat(), "lease_deadline": self.report["lease_deadline"],
                       "session_directory": str(self.relative), "errors": [], "cleanup_confirmed": False}
        self.tracker = None
        self.child = None

    def persist(self):
        path = self.args.output / "ui-test.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.report, indent=2) + "\n")
        temporary.replace(path)

    def observe(self, label, allow_new=True, cleanup=False):
        rows = self.processes(label, cleanup=cleanup)
        if allow_new and any(target_name(row.get("executable")) and
                             str(local_device_path(row["executable"])) not in self.tracker.paths.values() for row in rows):
            # Xcode may reinstall its runner after our explicit install. A fresh
            # bundle-ID mapping, not its basename, must identify the new path.
            paths = installed_paths(self.command(label + "-apps", ["info", "apps"]))
            self.tracker.paths.update(paths)
            self.report["installed_executable_paths"] = self.tracker.paths
        self.tracker.observe(rows, allow_new)
        self.report["owned_processes"] = list(self.tracker.owned.values())
        self.persist()
        return rows

    def stop_host(self):
        if self.child and self.child.poll() is None:
            try:
                self.child.terminate()
            except ProcessLookupError:
                pass
            try:
                self.child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    self.child.kill()
                except ProcessLookupError:
                    pass
                self.child.wait(timeout=2)

    def cleanup_apps(self):
        if not self.child:
            self.report["cleanup_confirmed"] = True
            return
        self.teardown = True
        self.cleanup_deadline = time.monotonic() + 85
        rows = self.observe("cleanup-before", allow_new=False, cleanup=True)
        for identity in self.tracker.live(rows):
            try:
                self.command(f"terminate-{identity['pid']}", ["process", "terminate"], ["--pid", identity["pid"]], cleanup=True, timeout=8)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                self.report["errors"].append("terminate request: " + str(error))
        for attempt in range(4):
            rows = self.observe(f"cleanup-confirm-{attempt}", allow_new=False, cleanup=True)
            alive = self.tracker.live(rows)
            if not alive:
                self.report["cleanup_confirmed"] = True
                return
            if attempt == 1:
                for identity in alive:
                    try:
                        self.command(f"kill-{identity['pid']}", ["process", "terminate"],
                                     ["--pid", identity["pid"], "--kill"], cleanup=True, timeout=5)
                    except (OSError, ValueError, subprocess.SubprocessError) as error:
                        self.report["errors"].append("kill request: " + str(error))
            time.sleep(.25)
        raise WalkthroughError("not all invocation-owned test processes were confirmed gone")

    def finish_cleanup(self):
        self.report["cleanup_confirmed"] = False
        try:
            self.stop_host()
        except (Exception, KeyboardInterrupt) as error:
            self.report["errors"].append("host cleanup: " + (str(error) or type(error).__name__))
        # A failed host wait must not prevent trying to stop already attributed
        # device processes. It also must not let an app-free snapshot release
        # the lease while a live xcodebuild could launch another process later.
        try:
            self.cleanup_apps()
        except (Exception, KeyboardInterrupt) as error:
            self.report["cleanup_confirmed"] = False
            self.report["errors"].append("device cleanup: " + (str(error) or type(error).__name__))
        host_stopped = False
        try:
            host_stopped = self.child is None or self.child.poll() is not None
        except (Exception, KeyboardInterrupt) as error:
            self.report["errors"].append("host status: " + (str(error) or type(error).__name__))
        self.report["host_cleanup_confirmed"] = host_stopped
        if not host_stopped:
            self.report["cleanup_confirmed"] = False
            self.report["errors"].append("host xcodebuild exit is unconfirmed; reservation must remain")
        if self.report["cleanup_confirmed"]:
            self.cleanup_receipt()

    def execute_ui(self):
        self.args.output.mkdir(parents=True, exist_ok=False)
        self.persist()
        staged = False
        try:
            configuration, products = prepare_products(self.args.xctestrun, self.args.app)
            before = self.processes("before")
            if any(not row.get("executable") or target_name(row.get("executable")) for row in before):
                raise WalkthroughError("preexisting PT/harness/runner or incomplete process identities; preserve current sessions")
            paths = {}
            for bundle, product in products.items():
                result = self.command("install-" + EXECUTABLES[bundle], ["install", "app"], [product], timeout=60)
                paths[bundle] = install_executable(result, bundle)
            self.report["installed_executable_paths"] = paths
            self.report["product_sha256"] = {bundle: hashlib.sha256((path / EXECUTABLES[bundle]).read_bytes()).hexdigest()
                                             for bundle, path in products.items()}
            local = self.args.output / "session-input"
            local.mkdir()
            (local / "session.txt").write_text("Isolated physical UI test diagnostics; no game data.\n")
            copied = self.command("stage-session", ["copy", "to"],
                                  ["--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                                   "--source", local, "--destination", self.relative])
            device_dir = copied_destination(copied, self.relative)
            staged = True
            config = resolve_testroot(configuration, self.args.xctestrun.parent.resolve())
            target = config["PTDeviceTests"]
            target.setdefault("EnvironmentVariables", {})["PT_TEST_SESSION"] = str(device_dir)
            target.setdefault("TestingEnvironmentVariables", {})["PT_TEST_SESSION"] = str(device_dir)
            target["TestTimeoutsEnabled"] = True
            target["DefaultTestExecutionTimeAllowance"] = min(self.args.seconds, 180)
            target["MaximumTestExecutionTimeAllowance"] = min(self.args.seconds, 240)
            configured = self.args.output / "session.xctestrun"
            configured.write_bytes(plistlib.dumps(config))
            before = self.processes("before-xctest")
            if any(not row.get("executable") or target_name(row.get("executable")) for row in before):
                raise WalkthroughError("a test application started during setup; preserve it")
            self.tracker = OwnedProcesses([row["processIdentifier"] for row in before], paths)
            if self.remaining() < self.args.seconds + 130:
                raise WalkthroughError("insufficient lease time for the bounded XCTest retry and cleanup")
            command = [XCODEBUILD, "test-without-building", "-xctestrun", str(configured), "-destination", "id=" + self.args.device,
                       "-only-testing:" + EXPECTED_TEST, "-parallel-testing-enabled", "NO",
                       "-resultBundlePath", str(self.args.output / "test.xcresult")]
            self.report["xcodebuild_arguments"] = command
            self.persist()
            with (self.args.output / "xcodebuild.log").open("w") as log:
                # Inherit the supervisor's process group so its hard deadline
                # also stops xcodebuild if this Python child cannot finish.
                self.child = subprocess.Popen(command, env=self.env, stdout=log, stderr=subprocess.STDOUT)
                started = time.monotonic()
                while self.child.poll() is None:
                    if self.cancelled:
                        raise KeyboardInterrupt("UI test interrupted")
                    if time.monotonic() - started >= self.args.seconds or self.remaining() < 125:
                        raise WalkthroughError("bounded XCTest retry timed out")
                    self.observe("running-" + str(int(time.monotonic() - started)))
                    time.sleep(1)
                self.report["xcodebuild_exit"] = self.child.returncode
                self.observe("after-xctest")
                if self.child.returncode:
                    self.report["errors"].append("xcodebuild did not complete successfully")
        except (Exception, KeyboardInterrupt) as error:
            self.report["errors"].append(str(error) or type(error).__name__)
        finally:
            try:
                self.finish_cleanup()
            except (Exception, KeyboardInterrupt) as error:
                self.report["errors"].append("cleanup: " + (str(error) or type(error).__name__))
            self.cleanup_deadline = None
            self.teardown = False
            if staged and not self.cancelled:
                try:
                    self.copy_from("runtime-log", self.relative / "pt.log", self.args.output / "pt.log", cleanup=True, timeout=20)
                except (Exception, KeyboardInterrupt) as error:
                    self.report["errors"].append("runtime log: " + str(error))
            elif staged:
                self.report["collection_skipped"] = "Interrupted; only exact-owned process teardown was allowed."
            self.persist()
        result = self.args.output / "test.xcresult"
        try:
            reports = {}
            for kind in ("tests", "summary"):
                raw = subprocess.check_output([XCRESULT, "get", "test-results", kind, "--path", str(result), "--compact"],
                                              env=self.env, stderr=subprocess.STDOUT, text=True, timeout=30)
                reports[kind] = json.loads(raw)
                (self.args.output / ("xcresult-" + kind + ".json")).write_text(raw + "\n")
            self.report["test_result"] = exact_test_result(reports["tests"], reports["summary"])
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self.report["errors"].append("XCTest result unavailable: " + str(error))
        log = self.args.output / "pt.log"
        if log.is_file():
            self.report["input_evidence"] = input_evidence(log.read_text(errors="replace"))
        self.report["capture_finished"] = utc_now().isoformat()
        passed = (self.report["cleanup_confirmed"] and not self.report["errors"] and
                  self.report.get("test_result", {}).get("passed", False) and
                  self.report.get("input_evidence", {}).get("passed", False))
        self.report["evidence_status"] = "captured_for_visual_review" if passed else "incomplete"
        self.persist()
        return 0 if passed else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--app", type=Path, required=True, help="intended signed PT native bundle")
    parser.add_argument("--xctestrun", type=Path, required=True, help="freshly built signed XCTest products")
    parser.add_argument("--output", type=Path, required=True, help="new private report directory")
    parser.add_argument("--seconds", type=int, default=240, help="one XCTest run timeout, 180..600 seconds")
    parser.add_argument("--under-lease", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.device.strip() or not 180 <= args.seconds <= 600:
        parser.error("an explicit device and timeout from180 to600 seconds are required")
    if args.output.exists() or args.output.is_symlink():
        parser.error("output must be a new directory")
    args.output = args.output.absolute()
    args.xctestrun = args.xctestrun.resolve()
    prepare_products(args.xctestrun, args.app)
    if not args.under_lease:
        values = list(sys.argv[1:] if argv is None else argv)
        return subprocess.call([sys.executable, str(ROOT / "tools/ipad_command.py"), "--minutes", str(args.seconds / 60 + 5),
                                "--require-cleanup-receipt", str(args.output / "cleanup.json"), "--",
                                sys.executable, str(Path(__file__).resolve()), *values, "--under-lease"])
    capture = UiCapture(args)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda number, frame: setattr(capture, "cancelled", True))
    return capture.execute_ui()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f"UI test refused: {error}")
