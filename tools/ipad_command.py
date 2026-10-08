#!/usr/bin/env python3
"""Run a bounded iPad command through the existing shared-device lease guard."""
import argparse
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import json
import stat

ROOT = Path(__file__).resolve().parents[1]
OWNER = "pt-native"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, default=Path(os.environ.get("PT_IPAD_LEASE_RECORD", str(ROOT.parent / "madeira/installation/ipad-access.json"))))
    parser.add_argument("--lease-wrapper", type=Path, default=ROOT.parent / "anyps5-ipad/scripts/with-ipad-lease.py")
    parser.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID"))
    parser.add_argument("--minutes", type=float, default=5)
    parser.add_argument("--register-owner", action="store_true", help="record this explicitly authorized PT implementation in the existing allowlist")
    parser.add_argument("--require-cleanup-receipt", type=Path,
                        help="retain the device reservation unless the child confirms its launched processes are gone")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.thread_id or not 0 < args.minutes <= 60:
        parser.error("a thread ID and a duration greater than zero and at most 60 minutes are required")
    if not args.command or args.command[0] != "--" or len(args.command) < 2:
        parser.error("provide -- followed by an explicit command")
    if not args.record.is_file() or not args.lease_wrapper.is_file():
        parser.error("the shared record and existing lease wrapper must exist; no fallback device access")
    if args.require_cleanup_receipt and args.require_cleanup_receipt.exists():
        parser.error("cleanup receipt must be a fresh path")
    if args.register_owner or args.require_cleanup_receipt:
        spec = importlib.util.spec_from_file_location("pt_shared_lease", args.lease_wrapper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    if args.register_owner:
        lease = module.Lease(args.record, OWNER, args.thread_id, args.minutes * 60)
        with lease.transaction():
            record = lease.read()
            module.validate(record)
            allowed = record.get("allowedOwners")
            if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
                raise ValueError("shared record lacks an explicit valid allowlist; registration refused")
            if OWNER not in allowed:
                allowed.append(OWNER)
            record["ptAuthorization"] = {
                "instruction": "PLEASE IMPLEMENT THIS PLAN: Native P.T. for iPad, including signed device installation and validation",
                "threadId": args.thread_id,
                "recordedAt": datetime.now(timezone.utc).isoformat(),
            }
            # Preserve other owners, reservations, stop state and queued phases verbatim.
            lease.write(record)
    if args.require_cleanup_receipt:
        receipt_path = args.require_cleanup_receipt.absolute()

        class CleanupLease(module.Lease):
            def release(self):
                confirmed = False
                try:
                    info = receipt_path.lstat()
                    if stat.S_ISREG(info.st_mode) and info.st_size <= 65536 and info.st_nlink == 1:
                        receipt = json.loads(receipt_path.read_text())
                        confirmed = receipt.get("lease_token") == self.token and receipt.get("cleanup_confirmed") is True
                except (OSError, ValueError, AttributeError):
                    pass
                if confirmed:
                    return super().release()
                self.cleanup_unconfirmed = True
                # The external guard's short process-group termination grace may
                # prevent device cleanup. Preserve ownership until explicit recovery.
                with self.transaction():
                    record = self.read()
                    if self.matches(record):
                        if record.get("status") == "command-lease-active":
                            record["status"] = "pt-device-cleanup-required"
                        record["ptCleanupRequired"] = {"receipt": str(receipt_path), "leaseToken": self.token,
                                                       "reason": "Launched-device-process cleanup was not confirmed"}
                        self.write(record)
                print("PT device reservation retained: confirm launched-process cleanup before recovery", file=sys.stderr)
                return False

        lease = CleanupLease(args.record, OWNER, args.thread_id, args.minutes * 60)
        command = ["/usr/bin/env", f"PT_DEVICE_LEASE_TOKEN={lease.token}", *args.command[1:]]
        try:
            result = module.run(lease, command)
            return 75 if result == 0 and getattr(lease, "cleanup_unconfirmed", False) else result
        except module.LeaseError as error:
            raise ValueError(str(error)) from error
    return subprocess.call([sys.executable, str(args.lease_wrapper), "--record", str(args.record),
                            "--owner", OWNER, "--thread-id", args.thread_id, "--minutes", str(args.minutes),
                            *args.command])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        raise SystemExit(f"iPad command refused: {error}")
