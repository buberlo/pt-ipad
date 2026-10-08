#!/usr/bin/env python3
"""Run a bounded command with the repository's shared-device coordinator."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid
from device_lease import Lease, run

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', '--lease-record', type=Path, default=Path(os.environ.get('PT_IPAD_LEASE_RECORD', str(ROOT.parent / 'madeira/installation/ipad-access.json'))))
    parser.add_argument('--device', required=True)
    parser.add_argument('--session-id', '--thread-id', default=os.environ.get('PT_IPAD_SESSION_ID') or os.environ.get('CODEX_THREAD_ID') or uuid.uuid4().hex)
    parser.add_argument('--minutes', type=float, default=5)
    parser.add_argument('--require-cleanup-receipt', type=Path)
    parser.add_argument('--create-record', action='store_true', help='explicitly create a new record for your independently owned device')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.create_record:
        if args.command:
            parser.error('--create-record cannot run a command')
        with args.record.open('x') as stream:
            json.dump({'owner': None, 'status': 'available', 'deviceUDID': args.device,
                       'allowedOwners': ['pt-native'], 'deviceWorkPaused': False, 'nextRequestedPhases': []}, stream, indent=2)
        return 0
    if not args.command or args.command[0] != '--' or len(args.command) < 2:
        parser.error('provide -- followed by an explicit command')
    lease = Lease(args.record, 'pt-native', args.session_id, args.minutes * 60, args.device, args.require_cleanup_receipt)
    return run(lease, args.command[1:])


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        raise SystemExit(f'iPad command refused: {error}')
