"""Cross-process fake-record races and cancellation; no device commands."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LeaseRaceTests(unittest.TestCase):
    def record(self, root):
        record = root / 'record.json'
        record.write_text(json.dumps({'owner': None, 'deviceUDID': 'fixture', 'allowedOwners': ['pt-native'],
                                      'nextRequestedPhases': [{'owner': 'other'}]}))
        return record

    def test_simultaneous_claim_has_one_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self.record(root)
            gate = root / 'gate'
            code = """import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from device_lease import Lease,LeaseError
while not Path(sys.argv[3]).exists(): time.sleep(.005)
try:
    Lease(sys.argv[2],'pt-native',sys.argv[4],10,'fixture').claim()
except LeaseError: raise SystemExit(3)
"""
            workers = [subprocess.Popen([sys.executable, '-c', code, str(ROOT / 'tools'), str(record), str(gate), f'session-{i}']) for i in range(2)]
            try:
                gate.write_text('go')
                results = [worker.wait(timeout=10) for worker in workers]
                self.assertEqual(sorted(results), [0, 3])
                value = json.loads(record.read_text())
                self.assertEqual(value['nextRequestedPhases'], [{'owner': 'other'}])
                self.assertIn(value['threadId'], ('session-0', 'session-1'))
            finally:
                for worker in workers:
                    if worker.poll() is None:
                        worker.kill()
                        worker.wait()

    def test_pause_stops_owned_child_and_preserves_stop_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self.record(root)
            receipt = root / 'cleanup'
            child_pid = root / 'child-pid'
            code = "import os,time;from pathlib import Path;Path(os.environ['PT_TEST_PID_FILE']).write_text(str(os.getpid()));time.sleep(20)"
            env = dict(os.environ, PT_TEST_PID_FILE=str(child_pid))
            worker = subprocess.Popen([sys.executable, str(ROOT / 'tools/ipad_command.py'), '--record', str(record),
                '--device', 'fixture', '--session-id', 'test', '--minutes', '.2', '--require-cleanup-receipt', str(receipt),
                '--', sys.executable, '-c', code], env=env)
            try:
                deadline = time.monotonic() + 5
                while not child_pid.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(child_pid.exists())
                # Cooperating mutation under the same stable lock.
                sys.path.insert(0, str(ROOT / 'tools'))
                from device_lease import Lease
                lease = Lease(record, 'pt-native', 'test', 10, 'fixture')
                with lease.transaction():
                    value = lease.read()
                    value.update(deviceWorkPaused=True, status='user-stopped')
                    lease.write(value)
                self.assertEqual(worker.wait(timeout=10), 75)
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(child_pid.read_text()), 0)
                value = json.loads(record.read_text())
                self.assertEqual(value['status'], 'user-stopped')
                self.assertEqual(value['owner'], 'pt-native')
                self.assertIn('ptCleanupRequired', value)
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait()


if __name__ == '__main__':
    unittest.main()
