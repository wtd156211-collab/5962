import unittest

from seatalloc import Instance, InstanceError, is_satisfiable, solve_instance
from seatalloc.conflict import minimal_conflict_ids


def solve(obj):
    return solve_instance(Instance.from_dict(obj))


def base(people=("alice", "bob"), periods=("t0", "t1"), locations=("la", "lb")):
    return {
        "case_id": "t",
        "periods": list(periods),
        "locations": [{"id": loc, "capacity": 5} for loc in locations],
        "people": list(people),
        "rules": [],
    }


def prefer(rid, person, period, location, weight):
    return {"id": rid, "kind": "prefer", "person": person, "period": period,
            "location": location, "weight": weight}


def avoid(rid, person, period, weight):
    return {"id": rid, "kind": "avoid", "person": person, "period": period,
            "weight": weight}


class TieBreakTests(unittest.TestCase):
    def test_first_optimum_in_fixed_value_order(self):
        # la / lb 罚分相同且并列最优，按取值顺序取先搜到的 la
        obj = base(people=("alice",), periods=("t0",))
        obj["rules"] = [prefer("S1", "alice", "t0", "la", 1),
                        prefer("S2", "alice", "t0", "lb", 1)]
        self.assertEqual(solve(obj), "cost,1\nalice,t0,la\n")

    def test_locations_come_before_none(self):
        # 取值顺序是 locations 在前、none 最后
        obj = base(people=("alice",), periods=("t0",))
        self.assertEqual(solve(obj), "cost,0\nalice,t0,la\n")

    def test_tie_between_location_and_none_prefers_location(self):
        # la 被禁后 lb 与 none 罚分相同，取先搜到的 lb
        obj = base(people=("alice",), periods=("t0",))
        obj["rules"] = [
            {"id": "R1", "kind": "forbidden", "location": "la", "period": "t0"},
            prefer("S1", "alice", "t0", "la", 5),
        ]
        self.assertEqual(solve(obj), "cost,5\nalice,t0,lb\n")


class SoftConstraintTests(unittest.TestCase):
    def test_prefer_counts_none_as_violation(self):
        obj = base(people=("alice",), periods=("t0",))
        obj["rules"] = [prefer("S1", "alice", "t0", "la", 5)]
        self.assertEqual(solve(obj), "cost,0\nalice,t0,la\n")

    def test_avoid_pushes_to_none(self):
        obj = base(people=("alice",), periods=("t0",))
        obj["rules"] = [avoid("S1", "alice", "t0", 3)]
        self.assertEqual(solve(obj), "cost,0\nalice,t0,none\n")

    def test_soft_tradeoff_picks_cheaper_violation(self):
        # 排 la 罚 avoid 的 5，不排罚 prefer 的 2，最优是不排
        obj = base(people=("alice",), periods=("t0",))
        obj["rules"] = [prefer("S1", "alice", "t0", "la", 2),
                        avoid("S2", "alice", "t0", 5)]
        self.assertEqual(solve(obj), "cost,2\nalice,t0,none\n")

    def test_weights_accumulate(self):
        obj = base(people=("alice",), periods=("t0",))
        obj["rules"] = [avoid("S1", "alice", "t0", 3), avoid("S2", "alice", "t0", 4)]
        self.assertEqual(solve(obj), "cost,0\nalice,t0,none\n")


class HardConstraintTests(unittest.TestCase):
    def test_together_forces_same_value(self):
        obj = base()
        obj["rules"] = [
            {"id": "R1", "kind": "fixed", "person": "alice", "period": "t0",
             "location": "la"},
            {"id": "R2", "kind": "together", "people": ["alice", "bob"]},
        ]
        out = solve(obj).splitlines()
        self.assertIn("bob,t0,la", out)

    def test_apart_allows_both_none(self):
        obj = base()
        obj["rules"] = [
            {"id": "R1", "kind": "apart", "people": ["alice", "bob"]},
            avoid("S1", "alice", "t0", 1),
            avoid("S2", "bob", "t0", 1),
        ]
        out = solve(obj).splitlines()
        self.assertIn("alice,t0,none", out)
        self.assertIn("bob,t0,none", out)

    def test_apart_forces_different_locations(self):
        obj = base()
        obj["rules"] = [
            {"id": "R1", "kind": "fixed", "person": "alice", "period": "t0",
             "location": "la"},
            {"id": "R2", "kind": "apart", "people": ["alice", "bob"]},
            prefer("S1", "bob", "t0", "la", 4),
        ]
        out = solve(obj).splitlines()
        self.assertEqual(out[0], "cost,4")
        self.assertIn("bob,t0,lb", out)

    def test_no_consecutive_forces_none_next_period(self):
        obj = base(people=("alice",))
        obj["rules"] = [
            {"id": "R1", "kind": "fixed", "person": "alice", "period": "t0",
             "location": "la"},
            {"id": "R2", "kind": "no_consecutive", "person": "alice"},
        ]
        out = solve(obj).splitlines()
        self.assertIn("alice,t1,none", out)

    def test_capacity_rule_is_enforced(self):
        obj = base()
        obj["rules"] = [
            {"id": "R1", "kind": "fixed", "person": "alice", "period": "t0",
             "location": "la"},
            {"id": "R2", "kind": "capacity", "location": "la", "period": "t0",
             "max": 1},
            prefer("S1", "bob", "t0", "la", 9),
        ]
        out = solve(obj).splitlines()
        self.assertEqual(out[0], "cost,9")
        self.assertIn("bob,t0,lb", out)

    def test_base_location_capacity_is_not_a_people_cap(self):
        # 与 samples 对齐：locations[].capacity 不作为人数上限，
        # 否则 case-1 里 desk-1(cap 1) 坐不下 alice+carol，会与期望解矛盾
        obj = base(periods=("t0",))
        obj["locations"] = [{"id": "la", "capacity": 1},
                            {"id": "lb", "capacity": 1}]
        out = solve(obj).splitlines()
        self.assertIn("alice,t0,la", out)
        self.assertIn("bob,t0,la", out)


class UnsatTests(unittest.TestCase):
    def test_fixed_vs_forbidden(self):
        obj = base(people=("alice",), periods=("t0",))
        obj["rules"] = [
            {"id": "R1", "kind": "fixed", "person": "alice", "period": "t0",
             "location": "la"},
            {"id": "R2", "kind": "forbidden", "location": "la", "period": "t0"},
        ]
        self.assertEqual(solve(obj), "unsat,R1,R2\n")

    def test_core_is_minimal_and_in_declaration_order(self):
        # R3 与冲突无关，不能出现在冲突集里
        obj = base(people=("alice",), periods=("t0",))
        obj["rules"] = [
            {"id": "R1", "kind": "fixed", "person": "alice", "period": "t0",
             "location": "la"},
            {"id": "R2", "kind": "forbidden", "location": "la", "period": "t0"},
            {"id": "R3", "kind": "forbidden", "location": "lb", "period": "t0"},
        ]
        self.assertEqual(solve(obj), "unsat,R1,R2\n")

    def test_capacity_conflict_core(self):
        obj = base(periods=("t0",))
        obj["rules"] = [
            {"id": "R1", "kind": "fixed", "person": "alice", "period": "t0",
             "location": "la"},
            {"id": "R2", "kind": "fixed", "person": "bob", "period": "t0",
             "location": "la"},
            {"id": "R3", "kind": "capacity", "location": "la", "period": "t0",
             "max": 1},
        ]
        self.assertEqual(solve(obj), "unsat,R1,R2,R3\n")

    def test_soft_rules_never_cause_unsat(self):
        obj = base(people=("alice",), periods=("t0",))
        obj["rules"] = [prefer("S1", "alice", "t0", "la", 5)]
        inst = Instance.from_dict(obj)
        self.assertTrue(is_satisfiable(inst))
        self.assertNotIn("S1", minimal_conflict_ids(inst) or [])


class ValidationTests(unittest.TestCase):
    def assert_invalid(self, obj):
        with self.assertRaises(InstanceError):
            Instance.from_dict(obj)

    def test_unknown_person(self):
        obj = base()
        obj["rules"] = [{"id": "R1", "kind": "no_consecutive", "person": "nobody"}]
        self.assert_invalid(obj)

    def test_unknown_location(self):
        obj = base()
        obj["rules"] = [{"id": "R1", "kind": "forbidden", "location": "nowhere",
                         "period": "t0"}]
        self.assert_invalid(obj)

    def test_unknown_period(self):
        obj = base()
        obj["rules"] = [{"id": "R1", "kind": "forbidden", "location": "la",
                         "period": "someday"}]
        self.assert_invalid(obj)

    def test_hard_rule_requires_id(self):
        obj = base()
        obj["rules"] = [{"kind": "no_consecutive", "person": "alice"}]
        self.assert_invalid(obj)

    def test_weight_must_be_positive_int(self):
        obj = base()
        obj["rules"] = [prefer("S1", "alice", "t0", "la", 0)]
        self.assert_invalid(obj)
        obj["rules"] = [prefer("S1", "alice", "t0", "la", 1.5)]
        self.assert_invalid(obj)

    def test_unknown_kind(self):
        obj = base()
        obj["rules"] = [{"id": "R1", "kind": "whatever"}]
        self.assert_invalid(obj)

    def test_duplicate_rule_id(self):
        obj = base()
        rule = {"id": "R1", "kind": "no_consecutive", "person": "alice"}
        obj["rules"] = [rule, dict(rule)]
        self.assert_invalid(obj)


if __name__ == "__main__":
    unittest.main()
