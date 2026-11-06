"""PID replacement must not be merged into the earlier process's thread samples."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_resident_ui_threads import process_history


def sample(seconds, *pids):
    return dict(elapsed_seconds=seconds,
                threads=[dict(name='SpringBoard', pid=pid) for pid in pids])


class ProcessHistoryTest(unittest.TestCase):
    def test_replacement_across_missing_sample(self):
        result = process_history([sample(0, 5, 5), sample(3, 5), sample(6), sample(9, 111)])
        self.assertEqual(len(result['process_lifetimes']), 2)
        self.assertEqual(result['process_replacements'], [dict(
            name='SpringBoard', previous_pids=[5], current_pids=[111],
            last_old_seen_seconds=3, first_new_seen_seconds=9)])
        self.assertFalse(result['process_exit_cause_known'])

    def test_partial_thread_capture_is_not_replacement(self):
        result = process_history([sample(0, 5, 111), sample(2, 111)])
        self.assertEqual(result['process_replacements'], [])

    def test_continuous_process(self):
        result = process_history([sample(0, 5), sample(2, 5)])
        self.assertEqual(result['process_replacements'], [])
        self.assertEqual(result['process_lifetimes'][0]['last_seen_seconds'], 2)


if __name__ == '__main__':
    unittest.main()
