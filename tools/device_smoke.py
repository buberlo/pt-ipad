#!/usr/bin/env python3
"""Bounded foreground smoke run of the installed PT app, under the shared lease."""
import argparse
import json
import math
import os
from pathlib import Path, PurePosixPath
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import unquote, urlparse
from device_config import add_options, configure, supervisor_options
from device_walkthrough import copied_destination, lease_identity, read_lease, running_processes

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "com.konradkern.pt.native"


def is_pt_executable(value):
    return isinstance(value, str) and unquote(urlparse(value).path).endswith("/pt.app/pt")


def launched_process(path, before):
    """Recover ownership only from this invocation's fresh launch response."""
    try:
        process = json.loads(path.read_text())["result"]["process"]
        pid, executable = process["processIdentifier"], process["executable"]
        if type(pid) is not int or pid <= 0 or pid in before or not is_pt_executable(executable):
            return None
        return pid, executable
    except (OSError, ValueError, KeyError, TypeError):
        return None


def owned_present(rows, owned):
    pid, executable = owned
    match = next((row for row in rows if row["processIdentifier"] == pid), None)
    if match is None:
        return False
    if not isinstance(match.get("executable"), str) or not match["executable"]:
        raise RuntimeError("owned PID exists but its executable identity is unavailable")
    return match["executable"] == executable


def write_receipt(path, token):
    # The lease supervisor only accepts its own token and confirmed device cleanup.
    with tempfile.NamedTemporaryFile(mode="w", prefix=".cleanup-", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump({"lease_token": token, "cleanup_confirmed": True}, handle)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--device", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--seconds", type=int, default=45, choices=range(10, 181))
    p.add_argument("--natural-startup", action="store_true", help="test fresh startup and original intro without forcing a floor")
    p.add_argument("--under-lease", action="store_true", help=argparse.SUPPRESS)
    add_options(p)
    args = p.parse_args()
    configure(args)
    global BUNDLE
    BUNDLE = args.bundle_id
    args.output = args.output.absolute()
    receipt = args.output / "cleanup.json"
    if not args.under_lease:
        minutes = str(max(6, math.ceil((args.seconds + 300) / 60)))
        return subprocess.call([sys.executable, str(ROOT / "tools/ipad_command.py"), *supervisor_options(args), "--minutes", minutes,
                                "--require-cleanup-receipt", str(receipt), "--",
                                sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--under-lease"])
    record = Path(os.environ.get("PT_IPAD_LEASE_RECORD", str(ROOT.parent / "madeira/installation/ipad-access.json")))
    thread, parent = os.environ.get("CODEX_THREAD_ID"), os.getppid()
    identity, deadline = lease_identity(read_lease(record), thread, parent)
    lease = read_lease(record)
    if lease.get("deviceUDID") != args.device:
        raise RuntimeError("requested device differs from lease record")
    token = os.environ.get("PT_DEVICE_LEASE_TOKEN")
    if (lease.get("owner") != "pt-native" or lease.get("threadId") != os.environ.get("CODEX_THREAD_ID") or
            not token or lease.get("commandLease", {}).get("token") != token):
        raise RuntimeError("a live PT command lease with a cleanup token is required")
    args.output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, DEVELOPER_DIR=str(args.developer_dir.resolve()))

    def command(name, operation, extra=(), timeout=20, check=True, teardown=False):
        current, current_deadline = lease_identity(read_lease(record), thread, parent, teardown=teardown)
        if current != identity or current_deadline != deadline:
            raise RuntimeError("lease identity changed; device operations refused")
        if teardown and operation not in (["info", "processes"], ["process", "terminate"]):
            raise RuntimeError("only owned-process teardown is permitted while stopping")
        timeout = min(timeout, math.floor(deadline - time.time() - 6))
        if timeout < 1:
            raise RuntimeError("lease deadline reached; device operation refused")
        path = args.output / (name + ".json")
        cmd = ["xcrun", "devicectl", "device", *operation, "--device", args.device,
               "--timeout", str(timeout), "--json-output", str(path), *extra]
        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout + 5)
        except subprocess.TimeoutExpired as error:
            def decoded(value):
                return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
            (args.output / (name + ".log")).write_text(decoded(error.stdout) + decoded(error.stderr) + "\nHost timeout\n")
            raise
        (args.output / (name + ".log")).write_text(result.stdout + result.stderr)
        print(f"{name}: exit {result.returncode}", flush=True)
        if check and result.returncode:
            raise RuntimeError(f"{name} failed; see {path.with_suffix('.log')}")
        return json.loads(path.read_text()) if path.exists() else {}

    def processes(name, teardown=False):
        return running_processes(command(name, ["info", "processes"], teardown=teardown))

    attempted = False
    owned = None
    before = set()
    exit_code = 0
    cleanup_confirmed = False
    session = PurePosixPath("Documents/PTDiagnostics") / ("smoke-" + uuid.uuid4().hex)

    def interrupted(number, frame):
        raise KeyboardInterrupt(f"signal {number}")
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        running = processes("processes-before")
        before = {x.get("processIdentifier") for x in running}
        if any(is_pt_executable(x.get("executable")) for x in running):
            raise RuntimeError("PT is already running; preserve the existing session")
        local = args.output / "session-input"
        local.mkdir()
        (local / "session.txt").write_text("Private P.T. smoke diagnostics; settings and logs stay in this session.\n")
        copied = command("stage-session", ["copy", "to"],
                         ["--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                          "--source", str(local), "--destination", str(session)])
        device_dir = copied_destination(copied, session)
        running = processes("processes-before-launch")
        before = {x.get("processIdentifier") for x in running}
        if any(is_pt_executable(x.get("executable")) for x in running):
            raise RuntimeError("PT started during staging; preserve the existing session")
        attempted = True
        arguments = ["--activate", BUNDLE, "--no-save", "--no-mods"]
        if not args.natural_startup:
            arguments.extend(["--start-floor", "f010"])
        arguments.extend(["--settings", str(device_dir / "session.ini"), "--log", str(device_dir / "pt.log")])
        command("launch", ["process", "launch"],
                arguments, timeout=30)
        owned = launched_process(args.output / "launch.json", before)
        if owned is None:
            raise RuntimeError("launch ownership is ambiguous; the device lease must remain reserved")
        pid, executable = owned
        start = time.monotonic()
        for target in sorted({10, args.seconds}):
            while time.monotonic() < start + target:
                time.sleep(min(0.25, start + target - time.monotonic()))
            running = processes(f"processes-{target}")
            if not owned_present(running, owned):
                raise RuntimeError("PT exited before the requested capture interval completed")
            command(f"screenshot-{target}", ["capture", "screenshot"],
                    ["--destination", str(args.output / f"screen-{target}.png")])
    except KeyboardInterrupt as error:
        print(f"Smoke run interrupted: {error}", file=sys.stderr, flush=True)
        exit_code = 130
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Smoke run failed: {error}", file=sys.stderr, flush=True)
        exit_code = 1
    finally:
        # A repeated signal must not interrupt device cleanup. The supervisor may
        # still kill this process; without a receipt it retains the reservation.
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda number, frame: None)
        if not attempted:
            cleanup_confirmed = True  # No device launch was attempted by us.
        else:
            owned = owned or launched_process(args.output / "launch.json", before)
            if owned is not None:
                pid, executable = owned
                try:
                    current = processes("processes-cleanup", teardown=True)
                    if not owned_present(current, owned):
                        cleanup_confirmed = True  # Original process is gone; never terminate a reused PID.
                    else:
                        try:
                            command("terminate", ["process", "terminate"], ["--pid", str(pid)], teardown=True)
                        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                            print(f"Termination request failed; checking device state: {error}", file=sys.stderr, flush=True)
                        for attempt in range(4):
                            current = processes(f"processes-after-terminate-{attempt}", teardown=True)
                            if not owned_present(current, owned):
                                cleanup_confirmed = True
                                break
                            if attempt == 1:
                                command("kill", ["process", "terminate"], ["--pid", str(pid), "--kill"], teardown=True)
                            time.sleep(0.25)
                except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
                    print(f"Device cleanup unconfirmed: {error}", file=sys.stderr, flush=True)
            if cleanup_confirmed:
                write_receipt(receipt, token)
            try:
                command("runtime-log", ["copy", "from"], ["--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                        "--source", str(session / "pt.log"), "--destination", str(args.output / "pt.log")],
                        timeout=15, check=False)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                print(f"Runtime log unavailable: {error}", file=sys.stderr, flush=True)
        if cleanup_confirmed and not receipt.exists():
            write_receipt(receipt, token)
        if not cleanup_confirmed:
            print("Device cleanup not confirmed; no cleanup receipt written. Keep the iPad reservation for recovery.", file=sys.stderr, flush=True)
            exit_code = exit_code or 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
