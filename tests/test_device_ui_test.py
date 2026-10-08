"""UI evidence/ownership state-machine checks; no device operation is executed."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("device_ui_test", TOOLS / "device_ui_test.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class UiEvidenceTests(unittest.TestCase):
    def tree(self, result="Passed", bundle="PTDeviceTests"):
        return {"testNodes": [{"name": bundle, "nodeType": "UI test bundle", "children": [
            {"nodeType": "Test Case", "nodeIdentifier": "NativeInputTests/testTouchAndResume()", "result": result}]}]}

    def summary(self):
        return {"result": "Passed", "failedTests": 0, "passedTests": 1}

    def test_only_exact_method_in_exact_bundle_can_pass(self):
        self.assertTrue(ui.exact_test_result(self.tree(), self.summary())["passed"])
        self.assertFalse(ui.exact_test_result(self.tree(bundle="OtherTests"), self.summary())["passed"])
        duplicate = self.tree()
        duplicate["testNodes"][0]["children"] *= 2
        self.assertFalse(ui.exact_test_result(duplicate, self.summary())["passed"])

    def test_bootstrap_failure_and_skipped_method_are_zero_executed(self):
        tree = self.tree("Failed")
        tree["testNodes"][0]["children"][0]["nodeIdentifier"] = "PTDeviceTests-Runner (123) encountered an error"
        result = ui.exact_test_result(tree, {"failedTests": 1, "passedTests": 0, "result": "Failed"})
        self.assertEqual(result["executed_test_methods"], 0)
        self.assertFalse(result["passed"])
        result = ui.exact_test_result(self.tree("Skipped"), self.summary())
        self.assertEqual(result["executed_test_methods"], 0)
        self.assertFalse(result["passed"])

    def passive_log(self, moving=True):
        rows = []
        for i in range(8):
            x, yaw = (i * .1, i * .1) if moving else (0, 0)
            rows.append(f"[ {i}.0] info #1 input script frame {100 + i * 15}: step 15 floor f010 loop 1 feet ({x:.2f} 0.00 1.00) yaw {yaw:.2f}")
        return "\n".join(rows + ["ui: option menu opened (pause), selector 4", "ui: option menu closed",
                                 "iPad lifecycle: suspending GPU, audio and input", "iPad lifecycle: foreground; presentation timing and held input reset"])

    def test_foreground_or_screenshots_without_pose_delta_do_not_pass(self):
        result = ui.input_evidence(self.passive_log(False))
        self.assertFalse(result["passed"])
        self.assertFalse(result["gates"]["position_changed"])
        self.assertFalse(result["gates"]["look_state_changed"])

    def test_original_opening_demo_motion_cannot_prove_touch(self):
        text = self.passive_log().replace("step 15", "step 13")
        self.assertFalse(ui.input_evidence(text)["passed"])

    def test_actual_play_state_and_lifecycle_deltas_remain_partial_evidence(self):
        result = ui.input_evidence(self.passive_log())
        self.assertTrue(result["passed"])
        self.assertFalse(result["acceptance"])
        self.assertFalse(result["zoom_verified"])
        self.assertFalse(ui.input_evidence(self.passive_log() + "\n[ 12.5] error #99 lua: failed")["passed"])

    def test_out_of_order_samples_and_missing_resume_fail(self):
        self.assertFalse(ui.input_evidence(self.passive_log().replace("frame 205", "frame 1"))["passed"])
        self.assertFalse(ui.input_evidence(self.passive_log().replace("iPad lifecycle: foreground;", "unrelated message"))["passed"])


class UiOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.path = "/private/apps/exact/pt.app/pt"
        self.rows = [{"processIdentifier": 20, "executable": "file://" + self.path, "auditToken": [20, 1]}]
        self.tracker = ui.OwnedProcesses({1, 2}, {ui.BUNDLE: self.path})

    def test_fresh_verified_path_owned_but_same_basename_is_not(self):
        self.tracker.observe(self.rows, True)
        self.assertEqual(len(self.tracker.live(self.rows)), 1)
        impostor = [{"processIdentifier": 21, "executable": "/private/other/pt.app/pt"}]
        with self.assertRaises(ui.WalkthroughError):
            self.tracker.observe(impostor, True)
        self.assertNotIn(21, self.tracker.owned)

    def test_preexisting_pid_and_new_pid_after_stop_are_never_adopted(self):
        self.tracker.before.add(20)
        with self.assertRaises(ui.WalkthroughError): self.tracker.observe(self.rows, True)
        self.tracker.before.remove(20)
        with self.assertRaises(ui.WalkthroughError): self.tracker.observe(self.rows, False)

    def test_pid_reuse_is_not_a_target_and_missing_identity_is_not_exit(self):
        self.tracker.observe(self.rows, True)
        reused = copy.deepcopy(self.rows); reused[0]["auditToken"] = [20, 2]
        self.assertEqual(self.tracker.live(reused), [])
        with self.assertRaises(ui.WalkthroughError):
            self.tracker.observe([{"processIdentifier": 20}], False)

    def test_app_mapping_requires_bundle_identity_and_unambiguous_device_path(self):
        payload = {"result": {"apps": [{"bundleIdentifier": ui.BUNDLE, "url": "file:///private/apps/exact/pt.app/"}]}}
        self.assertEqual(ui.installed_paths(payload)[ui.BUNDLE], self.path)
        payload["result"]["apps"][0]["installationURL"] = "file:///private/apps/another/pt.app/"
        with self.assertRaises(ui.WalkthroughError): ui.installed_paths(payload)
        with self.assertRaises(ui.WalkthroughError): ui.installed_paths({"result": {}})

    def test_termination_timeout_still_checks_for_remote_exit(self):
        self.tracker.observe(self.rows, True)
        capture = ui.UiCapture.__new__(ui.UiCapture)
        capture.child = object()
        capture.tracker = self.tracker
        capture.report = {"errors": [], "cleanup_confirmed": False}
        capture.observe = Mock(side_effect=[self.rows, []])
        capture.command = Mock(side_effect=ui.WalkthroughError("host reply timed out"))
        capture.cleanup_apps()
        self.assertTrue(capture.report["cleanup_confirmed"])
        self.assertEqual(capture.command.call_args.args[2], ["--pid", 20])

    def test_sigkill_escalation_only_targets_reconfirmed_owned_pid(self):
        self.tracker.observe(self.rows, True)
        capture = ui.UiCapture.__new__(ui.UiCapture)
        capture.child = object(); capture.tracker = self.tracker
        capture.report = {"errors": [], "cleanup_confirmed": False}
        capture.observe = Mock(side_effect=[self.rows, self.rows, self.rows, []])
        capture.command = Mock()
        with patch.object(ui.time, "sleep"):
            capture.cleanup_apps()
        self.assertTrue(capture.report["cleanup_confirmed"])
        self.assertEqual(capture.command.call_args_list[-1].args[2], ["--pid", 20, "--kill"])

    def test_host_stop_failure_still_cleans_device_but_cannot_release_live_host(self):
        capture = ui.UiCapture.__new__(ui.UiCapture)
        capture.child = Mock(); capture.child.poll.return_value = None
        capture.report = {"errors": [], "cleanup_confirmed": False}
        capture.stop_host = Mock(side_effect=TimeoutError("host did not exit after kill"))
        capture.cleanup_apps = Mock(side_effect=lambda: capture.report.update(cleanup_confirmed=True))
        capture.cleanup_receipt = Mock()
        capture.finish_cleanup()
        capture.cleanup_apps.assert_called_once()
        capture.cleanup_receipt.assert_not_called()
        self.assertFalse(capture.report["cleanup_confirmed"])
        self.assertFalse(capture.report["host_cleanup_confirmed"])

    def test_late_confirmed_host_exit_and_app_cleanup_can_write_receipt(self):
        capture = ui.UiCapture.__new__(ui.UiCapture)
        capture.child = Mock(); capture.child.poll.return_value = -9
        capture.report = {"errors": [], "cleanup_confirmed": False}
        capture.stop_host = Mock(side_effect=TimeoutError("host wait reply timed out"))
        capture.cleanup_apps = Mock(side_effect=lambda: capture.report.update(cleanup_confirmed=True))
        capture.cleanup_receipt = Mock()
        capture.finish_cleanup()
        capture.cleanup_receipt.assert_called_once()
        self.assertTrue(capture.report["cleanup_confirmed"])
        self.assertTrue(capture.report["host_cleanup_confirmed"])


if __name__ == "__main__":
    unittest.main()
