#!/usr/bin/env python3
"""Bounded foreground smoke run of the installed PT app, under the shared lease."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "com.konradkern.pt.native"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--device", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--seconds", type=int, default=45, choices=range(10, 181))
    p.add_argument("--under-lease", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    if not args.under_lease:
        return subprocess.call([sys.executable, str(ROOT / "tools/ipad_command.py"), "--minutes", "6", "--",
                                sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--under-lease"])
    record = Path(os.environ.get("PT_IPAD_LEASE_RECORD", str(ROOT.parent / "madeira/installation/ipad-access.json")))
    lease = json.loads(record.read_text())
    if lease.get("owner") != "pt-native" or lease.get("threadId") != os.environ.get("CODEX_THREAD_ID") or not lease.get("commandLease"):
        raise RuntimeError("a live PT command lease is required")
    args.output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer")

    def command(name, operation, extra=(), timeout=40, check=True):
        path = args.output / (name + ".json")
        cmd = ["xcrun", "devicectl", "device", *operation, "--device", args.device,
               "--timeout", str(timeout), "--json-output", str(path), *extra]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout + 5)
        (args.output / (name + ".log")).write_text(result.stdout + result.stderr)
        print(f"{name}: exit {result.returncode}", flush=True)
        if check and result.returncode:
            raise RuntimeError(f"{name} failed; see {path.with_suffix('.log')}")
        return json.loads(path.read_text()) if path.exists() else {}

    def processes(name):
        return command(name, ["info", "processes"])["result"]["runningProcesses"]

    pid = None
    def interrupted(number, frame):
        raise KeyboardInterrupt(f"signal {number}")
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        if any("/pt.app/pt" in x.get("executable", "") for x in processes("processes-before")):
            raise RuntimeError("PT is already running; preserve the existing session")
        launched = command("launch", ["process", "launch"], ["--activate", BUNDLE, "--no-save", "--no-mods", "--start-floor", "f010"])
        pid = launched["result"]["process"]["processIdentifier"]
        start = time.monotonic()
        for target in (10, args.seconds):
            while time.monotonic() < start + target:
                time.sleep(min(0.25, start + target - time.monotonic()))
            running = processes(f"processes-{target}")
            if not any(x.get("processIdentifier") == pid for x in running):
                print("PT exited before capture", flush=True)
                break
            command(f"screenshot-{target}", ["capture", "screenshot"],
                    ["--destination", str(args.output / f"screen-{target}.png")])
    finally:
        if pid is not None:
            # Terminate only the PID created by this invocation, if it still belongs to PT.
            current = processes("processes-cleanup")
            if any(x.get("processIdentifier") == pid and "/pt.app/pt" in x.get("executable", "") for x in current):
                command("terminate", ["process", "terminate"], ["--pid", str(pid)])
            command("runtime-log", ["copy", "from"], ["--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                    "--source", "Library/Application Support/pt-port/pt/pt.log", "--destination", str(args.output / "pt.log")], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
