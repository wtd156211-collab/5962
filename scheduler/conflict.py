"""无解时的极小冲突集：按声明顺序逐条尝试删除硬约束，
去掉后仍不可满足就真的去掉，直到不能再去掉为止。"""

from .solver import Problem, Solver


def minimal_conflict_ids(instance):
    """返回一组互相矛盾的硬约束 id（按声明顺序）。

    结果满足极小性：去掉其中任何一条，剩余硬约束都可满足。
    若返回空列表，说明不依赖任何规则、模型本身（地点容量）就不可满足。
    """
    hard = instance.hard_rules
    kept = list(range(len(hard)))

    def still_unsat(ids):
        problem = Problem(instance, [hard[i] for i in ids])
        return not Solver(problem).feasible()

    for i in list(kept):
        trial = [j for j in kept if j != i]
        if still_unsat(trial):
            kept = trial
    return [hard[i].id for i in kept]
