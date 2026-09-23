import json
import unittest
from pathlib import Path

from seatalloc import Instance, solve_instance

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def run_sample(name):
    inst = Instance.from_dict(json.loads((SAMPLES / (name + ".json")).read_text()))
    return solve_instance(inst)


class SampleTests(unittest.TestCase):
    def check(self, name):
        expected = (SAMPLES / (name + ".expected.txt")).read_text()
        self.assertEqual(run_sample(name), expected)

    def test_case_1_zero_cost(self):
        self.check("case-1")

    def test_case_2_optimal_cost_7(self):
        self.check("case-2")

    def test_case_3_unsat_core(self):
        self.check("case-3")

    def test_deterministic(self):
        first = run_sample("case-2")
        second = run_sample("case-2")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
