import json
import unittest
from pathlib import Path

from scheduler import solve_instance

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


class SampleTests(unittest.TestCase):
    def test_samples_match_expected(self):
        for case in ("case-1", "case-2", "case-3"):
            with self.subTest(case=case):
                data = json.loads((SAMPLES / ("%s.json" % case)).read_text(encoding="utf-8"))
                expected = (SAMPLES / ("%s.expected.txt" % case)).read_text(encoding="utf-8")
                self.assertEqual(solve_instance(data), expected)

    def test_deterministic_across_runs(self):
        data = json.loads((SAMPLES / "case-2.json").read_text(encoding="utf-8"))
        first = solve_instance(data)
        second = solve_instance(data)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
