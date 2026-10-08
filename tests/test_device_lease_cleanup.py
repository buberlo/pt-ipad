"""Local fake-record tests; these never contact an iPad."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT.parent / "anyps5-ipad/scripts/with-ipad-lease.py"


@unittest.skipUnless(GUARD.is_file(), "external shared-device guard is unavailable")
class CleanupLeaseTests(unittest.TestCase):
    def exercise(self, code, minutes="0.1"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = root / "record.json"
            receipt = root / "cleanup.json"
            queue = [{"owner": "other-project", "phase": "preserve"}]
            record.write_text(json.dumps({"owner": None, "allowedOwners": ["pt-native"], "nextRequestedPhases": queue}))
            result = subprocess.run([sys.executable, str(ROOT / "tools/ipad_command.py"),
                "--record", str(record), "--lease-wrapper", str(GUARD), "--thread-id", "local-test",
                "--minutes", minutes, "--require-cleanup-receipt", str(receipt), "--",
                sys.executable, "-c", code, str(receipt)], capture_output=True, text=True, timeout=10)
            state = json.loads(record.read_text())
            self.assertEqual(state["nextRequestedPhases"], queue)
            return result, state

    def test_confirmed_cleanup_releases(self):
        result, state = self.exercise("import sys,os,json;from pathlib import Path;Path(sys.argv[1]).write_text(json.dumps({'lease_token':os.environ['PT_DEVICE_LEASE_TOKEN'],'cleanup_confirmed':True}))")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(state["owner"])
        self.assertNotIn("commandLease", state)

    def test_exit_without_cleanup_retains(self):
        result, state = self.exercise("raise SystemExit(9)")
        self.assertEqual(result.returncode, 9)
        self.assertEqual(state["owner"], "pt-native")
        self.assertEqual(state["status"], "pt-device-cleanup-required")

    def test_wrong_token_does_not_release(self):
        result, state = self.exercise("import sys,json;from pathlib import Path;Path(sys.argv[1]).write_text(json.dumps({'lease_token':'old-run','cleanup_confirmed':True}))")
        self.assertEqual(result.returncode, 75)
        self.assertEqual(state["owner"], "pt-native")

    def test_timeout_retains_reservation(self):
        result, state = self.exercise("import time;time.sleep(10)", minutes="0.01")
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertEqual(state["owner"], "pt-native")


if __name__ == "__main__":
    unittest.main()
