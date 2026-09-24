"""规模测试：200 个变量、几百条规则，围绕一个已知可行解生成，
验证传播 + 剪枝能在时限内给出确定的最优解。"""

import time
import unittest

from scheduler import solve_instance


def _build_large_instance():
    periods = ["p%02d" % i for i in range(10)]
    locations = [("desk-%d" % i, 1) for i in range(6)] + [("room-a", 7), ("room-b", 8)]
    people = ["w%02d" % i for i in range(20)]
    pairs = [(i, i + 1) for i in range(0, 10, 2)]  # together 单元，只进会议室
    singles = [(i,) for i in range(10, 20)]  # 单人单元，优先进工位
    units = pairs + singles

    assignment = {}  # (person_idx, period_idx) -> location id
    for t in range(len(periods)):
        room_seats = {"room-a": 7, "room-b": 8}
        desk_seats = {"desk-%d" % i: 1 for i in range(6)}

        def take(loc):
            if loc.startswith("desk"):
                desk_seats[loc] -= 1
            else:
                room_seats[loc] -= 1

        seated = [u for u in range(len(units)) if (u + t) % 2 == 0]
        for u in seated:
            members = units[u]
            if len(members) == 2:
                loc = "room-a" if room_seats["room-a"] >= 2 else "room-b"
                for p in members:
                    assignment[(p, t)] = loc
                room_seats[loc] -= 2
            else:
                free_desks = [d for d, n in desk_seats.items() if n > 0]
                if free_desks:
                    loc = free_desks[0]
                    desk_seats[loc] -= 1
                else:
                    loc = "room-a" if room_seats["room-a"] > 0 else "room-b"
                    room_seats[loc] -= 1
                assignment[(members[0], t)] = loc

    rules = []
    counter = [0]

    def add(kind, **kw):
        counter[0] += 1
        rules.append(dict(kind=kind, id="R%04d" % counter[0], **kw))

    for person in people:
        add("no_consecutive", person=person)
    for pair in pairs:
        add("together", people=[people[pair[0]], people[pair[1]]])
    # apart：单人单元两两永不同桌（工位容量 1），可放心加
    for i in range(0, 8, 2):
        add("apart", people=[people[10 + i], people[10 + i + 1]])
    # capacity 规则：把每个 (地点, 时段) 收紧到真实容量
    for loc, cap in locations:
        for period in periods:
            add("capacity", location=loc, period=period, max=cap)
    # fixed：挑几个与目标解一致的
    for p, t in [(0, 0), (3, 1), (12, 2), (17, 3)]:
        loc = assignment.get((p, t))
        if loc is not None:
            add("fixed", person=people[p], period=periods[t], location=loc)
    # 软约束：大部分与目标解一致，少部分故意冲突（最优代价 > 0）
    for p, person in enumerate(people):
        for t, period in enumerate(periods):
            loc = assignment.get((p, t))
            if loc is None:
                if (p + t) % 3 == 0:
                    rules.append({"kind": "avoid", "person": person, "period": period,
                                  "weight": (p * 7 + t * 3) % 9 + 1})
            elif (p * 13 + t * 7) % 11 == 0:
                rules.append({"kind": "prefer", "person": person, "period": period,
                              "location": "room-b", "weight": (p + t) % 9 + 1})
            else:
                rules.append({"kind": "prefer", "person": person, "period": period,
                              "location": loc, "weight": (p * 5 + t) % 9 + 1})
    return {
        "case_id": "large",
        "periods": periods,
        "locations": [{"id": lid, "capacity": cap} for lid, cap in locations],
        "people": people,
        "rules": rules,
    }


class ScaleTests(unittest.TestCase):
    def test_large_instance_solves_quickly_and_deterministically(self):
        instance = _build_large_instance()
        n_vars = len(instance["people"]) * len(instance["periods"])
        self.assertEqual(n_vars, 200)
        self.assertGreater(len(instance["rules"]), 200)

        start = time.time()
        first = solve_instance(instance)
        elapsed = time.time() - start
        self.assertTrue(first.startswith("cost,"), first[:200])
        self.assertLess(elapsed, 30, "求解 200 变量实例超时: %.1fs" % elapsed)

        second = solve_instance(instance)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
