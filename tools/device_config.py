"""Explicit options forwarded unchanged to a lease-supervised child."""
import os
from pathlib import Path
import uuid
from app_identity import bundle_id, DEFAULT_BUNDLE_ID

ROOT = Path(__file__).resolve().parents[1]


def add_options(parser):
    parser.add_argument('--bundle-id', type=bundle_id, default=DEFAULT_BUNDLE_ID)
    parser.add_argument('--developer-dir', type=Path, default=Path('/Applications/Xcode.app/Contents/Developer'))
    parser.add_argument('--lease-record', type=Path, default=Path(os.environ.get('PT_IPAD_LEASE_RECORD', str(ROOT.parent / 'madeira/installation/ipad-access.json'))))
    parser.add_argument('--session-id', default=os.environ.get('PT_IPAD_SESSION_ID') or os.environ.get('CODEX_THREAD_ID'))


def configure(args):
    args.session_id = args.session_id or uuid.uuid4().hex
    os.environ['PT_IPAD_SESSION_ID'] = args.session_id
    os.environ['CODEX_THREAD_ID'] = args.session_id
    os.environ['PT_IPAD_LEASE_RECORD'] = str(args.lease_record.absolute())
    if not args.under_lease:
        return
    import device_walkthrough as walk
    walk.BUNDLE = args.bundle_id
    walk.DEVELOPER = str(args.developer_dir.resolve())
    walk.DEVICECTL = str(args.developer_dir.resolve() / 'usr/bin/devicectl')


def supervisor_options(args):
    return ['--device', args.device, '--record', str(args.lease_record.absolute()), '--session-id', args.session_id]
