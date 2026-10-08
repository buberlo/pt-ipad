"""Independent bounded command coordinator for the shared iPad record.

Preserves unknown fields and queues. An expired foreign owner is never stolen.
Only the claimed process group is supervised; device cleanup requires a receipt.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import time
import uuid


class LeaseError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc)


def bounded_json(path, limit=1024 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise LeaseError('expected a bounded, single-link regular JSON file')
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise LeaseError('JSON file grew beyond its size limit')
        return json.loads(data)


def validate(record):
    if not isinstance(record, dict):
        raise LeaseError('lease record must be an object')
    allowed = record.get('allowedOwners')
    if not isinstance(allowed, list) or not allowed or any(not isinstance(x, str) or not x for x in allowed):
        raise LeaseError('an explicit owner allowlist is required')
    if not isinstance(record.get('deviceUDID'), str) or not record['deviceUDID']:
        raise LeaseError('record must identify its physical device')


def paused(record):
    state = record.get('status', '')
    return (record.get('deviceWorkPaused', False) is not False or not isinstance(state, str) or
            'paused' in state.lower() or state.lower().startswith('user-stopped') or state.lower() == 'stopped')


class Lease:
    def __init__(self, record, owner, session, seconds, device, receipt=None):
        if not session or not device or isinstance(seconds, bool) or not math.isfinite(seconds) or not 0 < seconds <= 3600:
            raise LeaseError('explicit session, device and finite duration up to 60 minutes required')
        self.record = Path(record).absolute()
        self.owner, self.session, self.seconds, self.device = owner, session, seconds, device
        self.receipt = Path(receipt).absolute() if receipt else None
        self.token = uuid.uuid4().hex
        self.cleanup_unconfirmed = False

    @contextmanager
    def transaction(self):
        fd = os.open(self.record.with_suffix('.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise LeaseError('unsafe lease lock file')
            deadline = time.monotonic() + 5
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise LeaseError('shared lease lock is busy')
                    time.sleep(.05)
            yield
        finally:
            os.close(fd)

    def read(self):
        return bounded_json(self.record)

    def write(self, value):
        original = self.record.lstat()
        if not stat.S_ISREG(original.st_mode) or original.st_nlink != 1:
            raise LeaseError('unsafe lease record')
        fd, name = tempfile.mkstemp(prefix='.pt-lease-', dir=self.record.parent)
        try:
            os.fchmod(fd, stat.S_IMODE(original.st_mode))
            with os.fdopen(fd, 'w') as stream:
                json.dump(value, stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.record)
            directory = os.open(self.record.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(name).unlink(missing_ok=True)

    def matches(self, record):
        if not isinstance(record, dict) or not isinstance(record.get('commandLease'), dict):
            return False
        return (record.get('owner') == self.owner and record.get('threadId') == self.session and
                record.get('commandLease', {}).get('token') == self.token and
                record.get('commandLease', {}).get('wrapperPid') == os.getpid())

    def claim(self):
        if self.receipt and (self.receipt.exists() or self.receipt.is_symlink()):
            raise LeaseError('cleanup receipt must be a fresh path')
        with self.transaction():
            record = self.read()
            validate(record)
            if record['deviceUDID'] != self.device:
                raise LeaseError('requested device differs from shared record')
            if paused(record) or self.owner not in record['allowedOwners']:
                raise LeaseError('device work is paused or owner is not allowed')
            if record.get('commandLease') is not None:
                raise LeaseError('an existing command lease requires explicit recovery')
            owner = record.get('owner')
            if owner is not None:
                if owner != self.owner or record.get('threadId') != self.session:
                    raise LeaseError('another owner or session holds the device, even if expired')
                try:
                    until = datetime.fromisoformat(record['reservedUntil'].replace('Z', '+00:00'))
                    if until.tzinfo is None or until > now():
                        raise LeaseError('this session already has an active reservation')
                except (KeyError, TypeError, ValueError) as error:
                    raise LeaseError('existing reservation cannot be safely renewed') from error
            claimed = now()
            record.update(owner=self.owner, threadId=self.session, status='command-lease-active',
                          reservedUntil=(claimed + timedelta(seconds=self.seconds)).isoformat(),
                          updatedAt=claimed.isoformat(), commandLease={'token': self.token,
                          'wrapperPid': os.getpid(), 'timeoutSeconds': self.seconds, 'claimedAt': claimed.isoformat()})
            self.write(record)

    def check(self):
        with self.transaction():
            record = self.read()
            validate(record)
            if not self.matches(record) or paused(record) or self.owner not in record['allowedOwners'] or record['deviceUDID'] != self.device:
                raise LeaseError('lease ownership or device authorization changed')

    def release(self, host_cleanup=True):
        confirmed = host_cleanup and self.receipt is None
        if host_cleanup and self.receipt:
            try:
                value = bounded_json(self.receipt, 65536)
                confirmed = value.get('lease_token') == self.token and value.get('cleanup_confirmed') is True
            except (OSError, ValueError, AttributeError):
                confirmed = False
        with self.transaction():
            record = self.read()
            if not self.matches(record):
                return False  # Preserve a newer reservation verbatim.
            if not confirmed:
                self.cleanup_unconfirmed = True
                if not paused(record):
                    record['status'] = 'pt-device-cleanup-required'
                record['ptCleanupRequired'] = {'leaseToken': self.token, 'receipt': str(self.receipt),
                                               'reason': 'Host or launched-device cleanup not confirmed'}
            else:
                record.pop('commandLease', None)
                record.pop('ptCleanupRequired', None)
                record.update(owner=None, lastOwner=self.owner, reservedUntil=now().isoformat(), updatedAt=now().isoformat())
                if not paused(record):
                    record['status'] = 'command-lease-released'
            self.write(record)
        return confirmed


def run(lease, command):
    lease.claim()
    process = None
    cancelled = [False]
    previous = {}
    code = 1
    clean = False
    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.signal(sig, lambda *_: cancelled.__setitem__(0, True))
        env = dict(os.environ, PT_DEVICE_LEASE_TOKEN=lease.token, PT_IPAD_LEASE_RECORD=str(lease.record),
                   PT_IPAD_SESSION_ID=lease.session, CODEX_THREAD_ID=lease.session)
        process = subprocess.Popen(command, env=env, start_new_session=True)
        deadline = time.monotonic() + lease.seconds
        while process.poll() is None:
            if cancelled[0] or time.monotonic() >= deadline:
                code = 130 if cancelled[0] else 124
                break
            try:
                lease.check()
            except LeaseError:
                code = 75
                break
            time.sleep(.1)
        else:
            code = process.returncode
    finally:
        if process is not None:
            # Stop surviving descendants even when the command leader exited.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            stop = time.monotonic() + 2
            while time.monotonic() < stop:
                process.poll()
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    clean = True
                    break
                time.sleep(.05)
            if not clean:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    clean = True
        else:
            clean = True
        lease.release(clean)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return 75 if code == 0 and lease.cleanup_unconfirmed else code
