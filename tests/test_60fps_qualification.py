import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from qualify_60fps import statistics, qualify
from test_present_trace import row
from summarize_present_trace import FIELDS
import csv
import tempfile

class TimingGateTests(unittest.TestCase):
    def test_60hz_passes_30hz_does_not(self):
        self.assertTrue(statistics([16_666_667]*1200)['timing_passed'])
        self.assertFalse(statistics([33_333_333]*1200)['timing_passed'])
    def test_slow_fraction_rejects_hidden_stalls(self):
        # p95/p99 still look good; average and rare stalls must also pass.
        values=[16_666_667]*10000
        values[:11]=[33_333_334]*11
        self.assertFalse(statistics(values)['timing_passed'])
    def test_empty_and_insufficient_rate_fail(self):
        self.assertFalse(statistics([])['timing_passed'])
        self.assertFalse(statistics([17_200_000]*1200)['timing_passed'])
    def test_p99_detects_pacing_with_good_mean(self):
        values=[16_500_000]*1000
        values[:20]=[24_000_000]*20
        self.assertLess(statistics(values)['p95_ms'],17.2)
        self.assertFalse(statistics(values)['timing_passed'])


class WindowQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'present.csv'
        # Synthetic timing evidence only: never a device or visual acceptance.
        with self.path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(row(1, 1, 1_000_000_000))
            writer.writerows(row(1, i, 1_000_000_000 + (i-1)*16_666_667, 16_666_667)
                             for i in range(2, 72002))
        self.windows = {'schema': 1, 'windows': [
            self.window('all', 'gameplay', 1, 72001),
            self.window('last-five-minutes', 'tail', 54001, 72001),
            *[self.window(name, 'scene', 1+index*7200, 7201+index*7200)
              for index, name in enumerate(sorted(__import__('qualify_60fps').SCENES))]]}

    @staticmethod
    def window(name, role, first, last):
        return dict(name=name, role=role, segment=1, first_present_id=first, last_present_id=last)

    def test_complete_timing_does_not_claim_acceptance(self):
        result = qualify(self.path, self.windows)
        self.assertTrue(result['timing_passed'])
        self.assertFalse(result['accepted'])
        self.assertTrue(result['remaining_evidence'])

    def test_missing_scene_cannot_pass(self):
        self.windows['windows'].pop()
        self.assertFalse(qualify(self.path, self.windows)['timing_passed'])

    def test_tail_must_reach_end(self):
        self.windows['windows'][1]['last_present_id'] -= 1
        self.assertFalse(qualify(self.path, self.windows)['coverage_complete'])

    def test_scene_must_fit_gameplay(self):
        self.windows['windows'][0]['first_present_id'] = 2
        self.assertFalse(qualify(self.path, self.windows)['coverage_complete'])

    def test_absent_endpoint_fails(self):
        self.windows['windows'][0]['last_present_id'] = 2**32 - 1
        with self.assertRaises(ValueError):
            qualify(self.path, self.windows)
