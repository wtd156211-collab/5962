"""对外入口：给定实例 dict，返回完整输出文本。"""

from .conflict import minimal_conflict_ids
from .model import Instance, NONE_VALUE
from .solver import Problem, Solver


def solve_instance(data):
    """求解实例，返回输出文本（末尾带 LF）。

    可满足时输出 ``cost,<总罚分>`` 及逐变量取值；不可满足时输出
    ``unsat,<规则id>,...`` 或 ``unsat,base-model``。
    """
    instance = Instance(data)
    problem = Problem(instance, instance.hard_rules)
    result = Solver(problem).optimize()
    if result is None:
        ids = minimal_conflict_ids(instance)
        if ids:
            return "unsat," + ",".join(ids) + "\n"
        return "unsat,base-model\n"
    cost, assignment = result
    lines = ["cost,%d" % cost]
    n_periods = instance.n_periods
    none_value = instance.n_locations
    for p, person in enumerate(instance.people):
        for t, period in enumerate(instance.periods):
            value = assignment[p * n_periods + t]
            name = NONE_VALUE if value == none_value else instance.locations[value]
            lines.append("%s,%s,%s" % (person, period, name))
    return "\n".join(lines) + "\n"
