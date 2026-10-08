"""Synthetic parsing and evidence-classification checks; never call device tools."""
import copy
import csv
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import wave

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("device_walkthrough", TOOLS / "device_walkthrough.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
from summarize_present_trace import FIELDS


class DeviceWalkthroughParsing(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 8, tzinfo=timezone.utc)
        self.record = {"owner": "pt-native", "threadId": "test-thread", "status": "command-lease-active",
                       "allowedOwners": ["pt-native"], "deviceWorkPaused": False,
                       "reservedUntil": (self.now + timedelta(seconds=2105)).isoformat(),
                       "commandLease": {"token": "one-command", "wrapperPid": 456,
                                        "timeoutSeconds": 2100, "claimedAt": self.now.isoformat()}}

    def test_live_lease_uses_wrapper_timeout_before_reservation_grace(self):
        identity, deadline = runner.lease_identity(self.record, "test-thread", 456, self.now)
        self.assertEqual(identity[0], "one-command")
        self.assertEqual(deadline, self.now.timestamp() + 2100)

    def test_foreign_expired_unbounded_and_paused_leases_refused(self):
        variants = []
        for key, value in [("owner", "another-project"), ("threadId", "another-thread"),
                           ("deviceWorkPaused", True), ("status", "user-stopped-all"),
                           ("allowedOwners", [])]:
            altered = copy.deepcopy(self.record); altered[key] = value; variants.append(altered)
        for key, value in [("wrapperPid", 123), ("timeoutSeconds", 2101), ("timeoutSeconds", True),
                           ("token", ""), ("claimedAt", (self.now + timedelta(seconds=1)).isoformat())]:
            altered = copy.deepcopy(self.record); altered["commandLease"][key] = value; variants.append(altered)
        expired = copy.deepcopy(self.record); expired["reservedUntil"] = self.now.isoformat(); variants.append(expired)
        for altered in variants:
            with self.subTest(altered=altered), self.assertRaises(runner.WalkthroughError):
                runner.lease_identity(altered, "test-thread", 456, self.now)

    def test_teardown_can_finish_own_paused_lease_but_cannot_take_over(self):
        self.record["deviceWorkPaused"] = True
        runner.lease_identity(self.record, "test-thread", 456, self.now, teardown=True)
        self.record["owner"] = "other-project"
        with self.assertRaises(runner.WalkthroughError):
            runner.lease_identity(self.record, "test-thread", 456, self.now, teardown=True)

    def copy_payload(self, path):
        return {"result": {"destination": path, "domain": "appDataContainer", "domainIdentifier": runner.BUNDLE}}

    def test_device_path_comes_from_copy_and_preserves_actual_container(self):
        relative = "Documents/PTDiagnostics/pt-session/sessionroute.txt"
        payload = self.copy_payload("file:///private/var/mobile/Containers/Data/Application/actual-container/" + relative)
        result = runner.copied_destination(payload, relative)
        self.assertEqual(str(result), "/private/var/mobile/Containers/Data/Application/actual-container/" + relative)

    def test_wrong_container_scope_traversal_and_remote_urls_refused(self):
        relative = "Documents/PTDiagnostics/pt-session/sessionroute.txt"
        for path in ["file://remote/" + relative, "/tmp/another/sessionroute.txt", "/root/../" + relative,
                     "file:///root/%2e%2e/" + relative, "/root/" + relative + "\x00", "relative/path"]:
            with self.subTest(path=path), self.assertRaises(runner.WalkthroughError):
                runner.copied_destination(self.copy_payload(path), relative)
        payload = self.copy_payload("/root/" + relative); payload["result"]["domainIdentifier"] = "another.app"
        with self.assertRaises(runner.WalkthroughError):
            runner.copied_destination(payload, relative)

    def test_conflicting_copy_fields_are_not_guessed(self):
        payload = self.copy_payload("/container/Documents/PTDiagnostics/a")
        payload["result"]["path"] = "/other/Documents/PTDiagnostics/a"
        with self.assertRaises(runner.WalkthroughError):
            runner.copied_destination(payload, "Documents/PTDiagnostics/a")

    def launch_payload(self):
        return {"info": {"arguments": ["devicectl", "device", "process", "launch", runner.BUNDLE]},
                "result": {"launchOptions": {"arguments": ["--no-save"], "activatedWhenStarted": True,
                                               "terminateExistingInstances": False},
                           "process": {"processIdentifier": 123, "executable": "file:///apps/unique/pt.app/pt",
                                       "auditToken": [1, 2, 3]}}}

    def test_launch_result_supplies_exact_identity(self):
        identity = runner.launched_identity(self.launch_payload(), ["--no-save"], {1, 2, 3})
        self.assertEqual(identity["pid"], 123)
        rows = [{"processIdentifier": 123, "executable": "file:///apps/unique/pt.app/pt"}]
        self.assertTrue(runner.owned_process(rows, identity))
        rows[0]["executable"] = "file:///apps/other/pt.app/pt"
        self.assertFalse(runner.owned_process(rows, identity))

    def test_failed_or_mismatched_launch_cannot_authorize_termination(self):
        variants = [{}, self.launch_payload(), self.launch_payload(), self.launch_payload(), self.launch_payload()]
        variants[1]["result"]["launchOptions"]["arguments"] = ["--different-session"]
        variants[2]["result"]["launchOptions"]["terminateExistingInstances"] = True
        variants[3]["info"]["arguments"] = ["another.bundle"]
        variants[4]["result"]["process"]["executable"] = "file:///apps/another.app/another"
        for payload in variants:
            with self.subTest(payload=payload), self.assertRaises(runner.WalkthroughError):
                runner.launched_identity(payload, ["--no-save"], set())
        with self.assertRaises(runner.WalkthroughError):
            runner.launched_identity(self.launch_payload(), ["--no-save"], {123})

    def test_audit_token_mismatch_is_not_the_owned_process(self):
        identity = runner.launched_identity(self.launch_payload(), ["--no-save"], set())
        row = self.launch_payload()["result"]["process"]
        row["auditToken"] = [4, 5, 6]
        self.assertFalse(runner.owned_process([row], identity))

    def test_missing_executable_for_matching_pid_does_not_confirm_exit(self):
        identity = runner.launched_identity(self.launch_payload(), ["--no-save"], set())
        for executable in (None, "", "relative/path"):
            with self.assertRaises(runner.WalkthroughError):
                runner.owned_process([{"processIdentifier": 123, "executable": executable}], identity)

    def test_bad_process_response_is_not_treated_as_no_processes(self):
        for payload in [{}, {"result": {"runningProcesses": None}}, {"result": {"runningProcesses": [{"processIdentifier": True}]}}]:
            with self.assertRaises(runner.WalkthroughError):
                runner.running_processes(payload)

    def test_checkpoints_order_failures_and_background_are_separate(self):
        log = "\n".join(["floor: NextFloor f000 -> f010", "milestone two", "milestone one",
                         "input script: gave up on (1 2 3)", "iPad lifecycle: suspending GPU, audio and input"])
        result = runner.inspect_route_log(log, ["milestone one", "milestone two"])
        self.assertFalse(result["checkpoints_complete"])
        self.assertEqual(result["latest_floor"], "f010")
        self.assertEqual(len(result["route_failures"]), 1)
        self.assertEqual(len(result["background_events"]), 1)

    def test_real_lua_error_and_script_failure_cannot_be_hidden_by_milestones(self):
        log = "\n".join(["milestone one", "milestone two",
                         "[    6.340] error lua: trapLightEnable.lua:27: bad argument #1 to 'pairs' (table expected, got nil)",
                         "[    6.340] warn  script: trapLightEnable.Exec failed or missing"])
        result = runner.inspect_route_log(log, ["milestone one", "milestone two"])
        self.assertTrue(result["checkpoints_complete"])
        self.assertEqual(len(result["runtime_errors"]), 2)

    def test_foreground_route_only_inserts_readonly_demo_synchronization(self):
        module, metadata = runner.load_pinned_route()
        shots = "/private/test-container/Documents/PTDiagnostics/session/shots"
        baseline = module.load_route(module.FULL, shots)
        script, variant = runner.foreground_variant(module, shots)
        restored = script.replace(runner.F120_WAIT, "", 1).replace(runner.F160_WAIT, "", 1)
        self.assertTrue(restored.endswith(baseline))
        prefix = restored[:-len(baseline)]
        # The menu wait must happen before the injected key, and the controller
        # must reach actual gameplay before any navigation enters the FULL tail.
        self.assertEqual(prefix.splitlines(), ["700 smenu 1", "700 swait 30", "700 sktap Escape",
                                               "700 swait 30", "700 smenu 0", "700 sexpect menu 0", "700 sstep 15"])
        self.assertEqual(script.count("svoice jack"), baseline.count("svoice jack"))
        self.assertNotIn("sgamestep", prefix)
        self.assertNotIn("teleport", prefix)
        self.assertEqual(metadata["route"], module.FULL)
        self.assertIn("tests/walkthrough/speedrun_boot.txt", metadata["input_sha256"])
        self.assertFalse(metadata["foreground_preface"]["physical_input_verified"])
        self.assertEqual(variant["expected_sequential_log_commands"], 41)
        self.assertFalse(variant["inserted_commands_change_game_flags_or_progression"])
        self.assertEqual(len(variant["insertions"]), 2)
        self.assertIn("700 swait 400\n" + runner.F160_WAIT + "700 sfree", script)
        self.assertIn(runner.F120_WAIT + module.load_route(["start"], shots), script)
        for mutation in variant["insertions"]:
            for line in mutation["commands"]:
                self.assertIn(line.split()[1], {"sdemo", "swait", "sstep"})

    def test_changed_sync_anchor_is_refused(self):
        module, _ = runner.load_pinned_route()
        original = module.load_route
        module.load_route = lambda names, shots=None: original(names, shots).replace("700 swait 400\n", "700 swait 401\n")
        with self.assertRaisesRegex(runner.WalkthroughError, "synchronization anchor"):
            runner.foreground_route(module)

    def test_finished_route_without_ending_stops_after_grace_not_endless_idle(self):
        log = "\n".join(["[ 1.0] info input script seq frame 10: step 15 floor f160 loop 1",
                         "[ 2.0] info input script seq frame 20: step 15 floor f160 loop 2",
                         "[ 31.9] info display: observing actual presentations"])
        observed = runner.inspect_route_log(log, ["ending milestone"], expected_log_commands=2)
        self.assertEqual(observed["route_commands_exhausted_log_seconds"], 2)
        self.assertIsNone(runner.route_stop_reason(observed))
        observed = runner.inspect_route_log(log + "\n[ 32.0] info status: idle", ["ending milestone"], expected_log_commands=2)
        self.assertEqual(runner.route_stop_reason(observed), "route_commands_exhausted_without_complete_ending")
        self.assertFalse(observed["checkpoints_complete"])

    def test_complete_milestones_stop_promptly_without_claiming_clean_route(self):
        observed = runner.inspect_route_log("ending milestone\ninput script: stuck at (1 2 3)", ["ending milestone"])
        self.assertEqual(runner.route_stop_reason(observed), "full_route_milestones_observed")
        self.assertEqual(len(observed["route_failures"]), 1)

    def test_trace_close_confirmation_requires_positive_renderer_write_ok(self):
        for text in ("", "[ 50.0] info display trace: rows=20 write_ok=false"):
            self.assertFalse(runner.inspect_route_log(text, [])["trace_write_ok_logged"])
        self.assertTrue(runner.inspect_route_log("[ 50.0] info display trace: rows=20 write_ok=true", [])["trace_write_ok_logged"])

    def test_menu_fps_and_script_activity_do_not_satisfy_startup_deadline(self):
        menu_log = "\n".join([
            "[    6.975] info #4 ui: option menu opened (first boot), selector 4, brightness 5",
            "[   32.184] warn #760 input script: stuck at (0.00 0.00 9.53) going to (0.00 0.00 12.50)",
            "[   89.9] info #2400 display: 29.999 FPS",
            "[   89.9] info #2400 floor f000 menu open"])
        observed = runner.inspect_route_log(menu_log, [])
        self.assertIsNone(runner.startup_failure(observed, 89.999))
        self.assertIn("StartGame", runner.startup_failure(observed, 90))
        self.assertIn("StartGame", runner.startup_failure(observed, 1500))
        observed = runner.inspect_route_log(menu_log + "\n[ 53.5] info #1300 controller: ChangeGameStep(StartGame)", [])
        self.assertIsNone(runner.startup_failure(observed, 90))
        # A slow log-copy reply must not allow a late StartGame to evade the limit.
        observed = runner.inspect_route_log(menu_log + "\n[ 90.001] info #2600 controller: ChangeGameStep(StartGame)", [])
        self.assertIn("after", runner.startup_failure(observed, 110))

    def test_ending_time_is_separate_from_scripted_gameplay(self):
        result = runner.inspect_route_log("\n".join([
            "[ 20.0] info controller: ChangeGameStep(StartGame)",
            "[ 900.0] info floor: NextFloor f160 -> ending",
            "[ 1500.0] info game: stopped"]), [])
        self.assertEqual(result["pre_ending_log_span_seconds"], 880)
        self.assertEqual(result["after_ending_transition_log_span_seconds"], 600)

    def test_voice_wav_is_explicit_and_truncated_or_wrong_format_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "voice.wav"
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
                output.writeframes(b"\0\0" * 1600)
            report = runner.voice_metadata(path)
            self.assertEqual(report["seconds"], .1)
            self.assertFalse(report["physical_microphone"])
            self.assertEqual(len(report["sha256"]), 64)
            path.write_bytes(path.read_bytes()[:-2])
            with self.assertRaises(runner.WalkthroughError):
                runner.voice_metadata(path)

    def write_trace(self, path, lengths):
        with path.open("w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=FIELDS); writer.writeheader()
            for segment, count in enumerate(lengths, 1):
                # Integer one-second actual timestamps simplify duration boundary assertions.
                for index in range(count + 1):
                    values = dict.fromkeys(FIELDS, 0)
                    values.update(schema_version=1, segment=segment, segment_reason="swapchain", present_id=index + 1,
                                  actual_present_ns=(segment * 10000 + index) * 1_000_000_000,
                                  interval_ns=1_000_000_000 if index else 0, surface_width=1920, surface_height=1080)
                    writer.writerow(values)

    def test_short_or_split_trace_does_not_become_twenty_continuous_minutes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "present.csv"
            self.write_trace(path, [1200])
            result = runner.trace_evidence(path)
            self.assertEqual(result["longest_retained_segment_seconds"], 1170)
            self.assertFalse(result["has_20_minute_contiguous_actual_intervals"])
            self.write_trace(path, [700, 700])
            result = runner.trace_evidence(path)
            self.assertFalse(result["has_20_minute_contiguous_actual_intervals"])
            self.assertGreater(result["summary"]["summary"]["observed_interval_seconds"], 1200)

    def test_timing_duration_never_implies_acceptance_or_target_fps(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "present.csv"
            self.write_trace(path, [1230])
            result = runner.trace_evidence(path)
            self.assertTrue(result["has_20_minute_contiguous_actual_intervals"])
            self.assertEqual(result["summary"]["summary"]["actual_display_fps"], 1)
            self.assertFalse(result["acceptance"])


if __name__ == "__main__":
    unittest.main()
