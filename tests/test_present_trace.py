import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import summarize_present_trace as trace


def row(segment, present, timestamp, interval=0, reason="swapchain", gap=0):
    return dict(zip(trace.FIELDS, [1, segment, reason, present, timestamp, interval,
                                 0, timestamp - 1, 1, timestamp + 100, 2732, 2048, gap]))


class PresentTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "present.csv"

    def summarize(self, rows, **kwargs):
        with self.path.open("w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=trace.FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return trace.summarize(self.path, **kwargs)

    def test_actual_timing_not_poll_or_desired_timing(self):
        rows = [row(1, 1, 1_000_000_000), row(1, 2, 1_040_000_000, 40_000_000),
                row(1, 3, 1_080_000_000, 40_000_000)]
        for entry in rows:
            entry["poll_monotonic_ns"] = 8_000_000_000
            entry["desired_present_ns"] = 7_000_000_000
        result = self.summarize(rows)
        self.assertEqual(result["summary"]["actual_display_fps"], 25)
        self.assertEqual(result["summary"]["overshoot_count"], 2)

    def test_resets_exclude_background_pause_and_allow_id_wrap(self):
        result = self.summarize([row(1, 2**32-2, 1_000_000_000), row(1, 2**32-1, 1_050_000_000, 50_000_000),
                                 row(2, 1, 100_000_000_000, reason="present_id_wrap"),
                                 row(2, 2, 100_050_000_000, 50_000_000, reason="present_id_wrap")])
        self.assertEqual(result["summary"]["observed_interval_seconds"], .1)
        self.assertEqual(result["summary"]["actual_display_fps"], 20)
        self.assertFalse(result["trace_discontinuity"])

    def test_identical_duplicate_does_not_add_frame(self):
        a, b = row(1, 1, 100), row(1, 2, 200, 100)
        result = self.summarize([a, a, b, b])
        self.assertEqual(result["observations"], 2)
        self.assertEqual(result["duplicate_rows_skipped"], 2)
        self.assertEqual(result["summary"]["intervals"], 1)

    def test_missing_ids_mark_discontinuity_without_interpolation(self):
        result = self.summarize([row(1, 1, 100), row(2, 4, 400, reason="unobserved_present_ids", gap=2),
                                row(2, 5, 500, 100, reason="unobserved_present_ids")])
        self.assertTrue(result["trace_discontinuity"])
        self.assertEqual(result["unobserved_present_ids"], 2)
        self.assertEqual(result["summary"]["intervals"], 1)

    def test_window_boundary_and_overshoot_equality(self):
        # 10 FPS + 5 ms tolerance: equality is not an overshoot; 1 ns over is.
        result = self.summarize([row(1, 1, 1_000_000_000), row(1, 2, 1_105_000_000, 105_000_000),
                                row(1, 3, 1_210_000_001, 105_000_001)],
                               target_fps=10, tolerance_ms=5, window_seconds=.105)
        self.assertEqual(result["summary"]["overshoot_count"], 1)
        self.assertEqual([x["window_index"] for x in result["windows"]], [1, 2])
        self.assertEqual([x["overshoot_count"] for x in result["windows"]], [0, 1])
        self.assertTrue(result["windows"][-1]["partial_end"])

    def test_warmup_excludes_crossing_interval_each_segment(self):
        result = self.summarize([row(1, 1, 1_000_000_000), row(1, 2, 1_100_000_000, 100_000_000),
                                row(1, 3, 1_200_000_000, 100_000_000), row(2, 4, 5_000_000_000),
                                row(2, 5, 5_100_000_000, 100_000_000)], warmup_seconds=.1)
        self.assertEqual(result["summary"]["intervals"], 1)
        self.assertEqual(result["warmup_intervals_excluded"], 2)

    def test_long_stall_is_included_and_percentile_nearest_rank(self):
        result = self.summarize([row(1, 1, 100), row(1, 2, 33_333_433, 33_333_333),
                                row(1, 3, 1_033_333_433, 1_000_000_000)])
        self.assertEqual(result["summary"]["max_ms"], 1000)
        self.assertEqual(result["summary"]["p99_ms"], 1000)
        self.assertEqual(result["summary"]["over_100ms_count"], 1)
        self.assertEqual(result["summary"]["at_least_two_periods_count"], 1)

    def test_empty_or_single_observation_is_unavailable(self):
        for rows in ([], [row(1, 1, 100)]):
            result = self.summarize(rows)
            self.assertFalse(result["measurement_available"])
            self.assertIsNone(result["summary"]["actual_display_fps"])

    def test_invalid_discontinuities_and_corruption_fail_closed(self):
        bad_rows = [row(1, 3, 300, 200), row(1, 2, 99, 1), row(1, 2, 200, 99),
                    row(2, 2, 200, 100), row(1, 1, 101), row(1, 2**32, 200, 100),
                    row(1, 2, -200, 100)]
        for bad in bad_rows:
            with self.subTest(bad=bad), self.assertRaises(trace.TraceError):
                self.summarize([row(1, 1, 100), bad])

    def test_truncated_csv_fails_closed(self):
        self.path.write_text(",".join(trace.FIELDS) + "\n1,2,swapchain,5\n")
        with self.assertRaises(trace.TraceError):
            trace.summarize(self.path)

    def test_twenty_minute_trace_keeps_all_observed_intervals(self):
        period = 33_333_333
        result = self.summarize([row(1, i + 1, 1_000_000_000 + i * period, period if i else 0)
                                 for i in range(36_001)])
        self.assertEqual(result["summary"]["intervals"], 36_000)
        self.assertAlmostEqual(result["summary"]["observed_interval_seconds"], 1199.999988)
        self.assertEqual(sum(w["intervals"] for w in result["windows"]), 36_000)
        self.assertEqual(result["summary"]["overshoot_count"], 0)

    def test_parameter_boundaries(self):
        for kwargs in ({"target_fps": 0}, {"window_seconds": 0}, {"warmup_seconds": -1},
                       {"tolerance_ms": -1}, {"target_fps": float("nan")}, {"window_seconds": 1e-12}):
            with self.subTest(kwargs=kwargs), self.assertRaises(trace.TraceError):
                self.summarize([], **kwargs)


if __name__ == "__main__":
    unittest.main()
