import unittest

from scheduler import InstanceError, solve_instance


def make_instance(periods, locations, people, rules):
    return {
        "case_id": "test",
        "periods": periods,
        "locations": [{"id": lid, "capacity": cap} for lid, cap in locations],
        "people": people,
        "rules": rules,
    }


class TieBreakTests(unittest.TestCase):
    def test_no_rules_picks_first_location(self):
        inst = make_instance(["t"], [("a", 1), ("b", 1)], ["x"], [])
        self.assertEqual(solve_instance(inst), "cost,0\nx,t,a\n")

    def test_optimal_tie_keeps_first_in_search_order(self):
        # 两个地点罚分相同，最优解有两个，应保留先搜到的 a
        inst = make_instance(
            ["t"],
            [("a", 1), ("b", 1)],
            ["x"],
            [
                {"kind": "prefer", "person": "x", "period": "t", "location": "a", "weight": 5},
                {"kind": "prefer", "person": "x", "period": "t", "location": "b", "weight": 5},
            ],
        )
        self.assertEqual(solve_instance(inst), "cost,5\nx,t,a\n")


class SoftConstraintTests(unittest.TestCase):
    def test_minimizes_total_weight_not_first_feasible(self):
        # 第一个可行解是坐 a（罚 5），但最优是不排（罚 3）
        inst = make_instance(
            ["t"],
            [("a", 1)],
            ["x"],
            [
                {"kind": "avoid", "person": "x", "period": "t", "weight": 5},
                {"kind": "prefer", "person": "x", "period": "t", "location": "a", "weight": 3},
            ],
        )
        self.assertEqual(solve_instance(inst), "cost,3\nx,t,none\n")

    def test_prefer_counts_none_as_violation(self):
        inst = make_instance(
            ["t"],
            [("a", 1)],
            ["x"],
            [{"kind": "prefer", "person": "x", "period": "t", "location": "a", "weight": 4}],
        )
        self.assertEqual(solve_instance(inst), "cost,0\nx,t,a\n")


class HardConstraintTests(unittest.TestCase):
    def test_no_consecutive_only_adjacent(self):
        # t1、t3 不相邻，都可以排
        inst = make_instance(
            ["t1", "t2", "t3"],
            [("a", 5)],
            ["x"],
            [
                {"kind": "no_consecutive", "id": "R1", "person": "x"},
                {"kind": "prefer", "person": "x", "period": "t1", "location": "a", "weight": 1},
                {"kind": "prefer", "person": "x", "period": "t3", "location": "a", "weight": 1},
            ],
        )
        self.assertEqual(solve_instance(inst), "cost,0\nx,t1,a\nx,t2,none\nx,t3,a\n")

    def test_together_forces_equal_values_including_none(self):
        inst = make_instance(
            ["t"],
            [("a", 2)],
            ["x", "y"],
            [
                {"kind": "together", "id": "R1", "people": ["x", "y"]},
                {"kind": "avoid", "person": "x", "period": "t", "weight": 3},
                {"kind": "avoid", "person": "y", "period": "t", "weight": 3},
            ],
        )
        self.assertEqual(solve_instance(inst), "cost,0\nx,t,none\ny,t,none\n")

    def test_apart_allows_both_none(self):
        inst = make_instance(
            ["t"],
            [("a", 2)],
            ["x", "y"],
            [
                {"kind": "apart", "id": "R1", "people": ["x", "y"]},
                {"kind": "avoid", "person": "x", "period": "t", "weight": 2},
                {"kind": "avoid", "person": "y", "period": "t", "weight": 3},
            ],
        )
        self.assertEqual(solve_instance(inst), "cost,0\nx,t,none\ny,t,none\n")

    def test_apart_forces_different_locations(self):
        inst = make_instance(
            ["t"],
            [("a", 1), ("b", 1)],
            ["x", "y"],
            [
                {"kind": "apart", "id": "R1", "people": ["x", "y"]},
                {"kind": "fixed", "id": "R2", "person": "x", "period": "t", "location": "a"},
                {"kind": "prefer", "person": "y", "period": "t", "location": "a", "weight": 5},
            ],
        )
        self.assertEqual(solve_instance(inst), "cost,5\nx,t,a\ny,t,b\n")

    def test_capacity_rule_limits_people(self):
        inst = make_instance(
            ["t"],
            [("room", 5)],
            ["x", "y"],
            [
                {"kind": "capacity", "id": "R1", "location": "room", "period": "t", "max": 1},
                {"kind": "prefer", "person": "x", "period": "t", "location": "room", "weight": 4},
                {"kind": "prefer", "person": "y", "period": "t", "location": "room", "weight": 4},
            ],
        )
        # 最多坐一个，另一个只能 none（各罚 4），总罚 4
        self.assertEqual(solve_instance(inst), "cost,4\nx,t,room\ny,t,none\n")

    def test_capacity_rule_tightens_location_capacity(self):
        # capacity 规则在 locations[].capacity 基础上收紧：max 5 但容量只有 1
        inst = make_instance(
            ["t"],
            [("room", 1)],
            ["x", "y"],
            [
                {"kind": "capacity", "id": "R1", "location": "room", "period": "t", "max": 5},
                {"kind": "fixed", "id": "R2", "person": "x", "period": "t", "location": "room"},
                {"kind": "fixed", "id": "R3", "person": "y", "period": "t", "location": "room"},
            ],
        )
        self.assertEqual(solve_instance(inst), "unsat,R1,R2,R3\n")


class ConflictSetTests(unittest.TestCase):
    def test_fixed_vs_forbidden(self):
        inst = make_instance(
            ["t"],
            [("a", 1)],
            ["x"],
            [
                {"kind": "fixed", "id": "R1", "person": "x", "period": "t", "location": "a"},
                {"kind": "forbidden", "id": "R2", "location": "a", "period": "t"},
            ],
        )
        self.assertEqual(solve_instance(inst), "unsat,R1,R2\n")

    def test_soft_rules_never_in_conflict_set(self):
        inst = make_instance(
            ["t"],
            [("a", 1)],
            ["x"],
            [
                {"kind": "fixed", "id": "R1", "person": "x", "period": "t", "location": "a"},
                {"kind": "avoid", "person": "x", "period": "t", "weight": 9},
                {"kind": "forbidden", "id": "R2", "location": "a", "period": "t"},
            ],
        )
        self.assertEqual(solve_instance(inst), "unsat,R1,R2\n")

    def test_conflict_set_is_minimal(self):
        # R3 与冲突无关，不应出现在结果里
        inst = make_instance(
            ["t1", "t2"],
            [("a", 1)],
            ["x"],
            [
                {"kind": "fixed", "id": "R1", "person": "x", "period": "t1", "location": "a"},
                {"kind": "forbidden", "id": "R2", "location": "a", "period": "t1"},
                {"kind": "forbidden", "id": "R3", "location": "a", "period": "t2"},
            ],
        )
        self.assertEqual(solve_instance(inst), "unsat,R1,R2\n")

    def test_no_consecutive_chain_conflict(self):
        inst = make_instance(
            ["t1", "t2"],
            [("a", 1)],
            ["x"],
            [
                {"kind": "fixed", "id": "R1", "person": "x", "period": "t1", "location": "a"},
                {"kind": "fixed", "id": "R2", "person": "x", "period": "t2", "location": "a"},
                {"kind": "no_consecutive", "id": "R3", "person": "x"},
            ],
        )
        self.assertEqual(solve_instance(inst), "unsat,R1,R2,R3\n")

    def test_together_apart_conflict(self):
        inst = make_instance(
            ["t"],
            [("a", 2)],
            ["x", "y"],
            [
                {"kind": "fixed", "id": "R1", "person": "x", "period": "t", "location": "a"},
                {"kind": "together", "id": "R2", "people": ["x", "y"]},
                {"kind": "apart", "id": "R3", "people": ["x", "y"]},
            ],
        )
        self.assertEqual(solve_instance(inst), "unsat,R1,R2,R3\n")


class ValidationTests(unittest.TestCase):
    def test_unknown_person_rejected(self):
        inst = make_instance(
            ["t"], [("a", 1)], ["x"],
            [{"kind": "no_consecutive", "id": "R1", "person": "ghost"}],
        )
        with self.assertRaises(InstanceError):
            solve_instance(inst)

    def test_unknown_location_rejected(self):
        inst = make_instance(
            ["t"], [("a", 1)], ["x"],
            [{"kind": "forbidden", "id": "R1", "location": "nowhere", "period": "t"}],
        )
        with self.assertRaises(InstanceError):
            solve_instance(inst)

    def test_unknown_period_rejected(self):
        inst = make_instance(
            ["t"], [("a", 1)], ["x"],
            [{"kind": "avoid", "person": "x", "period": "someday", "weight": 1}],
        )
        with self.assertRaises(InstanceError):
            solve_instance(inst)

    def test_hard_rule_requires_id(self):
        inst = make_instance(
            ["t"], [("a", 1)], ["x"],
            [{"kind": "no_consecutive", "person": "x"}],
        )
        with self.assertRaises(InstanceError):
            solve_instance(inst)

    def test_weight_must_be_positive_int(self):
        for bad in (0, -1, 1.5, "3"):
            with self.subTest(weight=bad):
                inst = make_instance(
                    ["t"], [("a", 1)], ["x"],
                    [{"kind": "avoid", "person": "x", "period": "t", "weight": bad}],
                )
                with self.assertRaises(InstanceError):
                    solve_instance(inst)

    def test_unknown_kind_rejected(self):
        inst = make_instance(
            ["t"], [("a", 1)], ["x"],
            [{"kind": "teleport", "id": "R1", "person": "x"}],
        )
        with self.assertRaises(InstanceError):
            solve_instance(inst)


if __name__ == "__main__":
    unittest.main()
