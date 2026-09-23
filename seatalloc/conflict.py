"""极小冲突集（unsat core）：按声明顺序做删除式极小化。

从全部硬约束出发，按声明顺序逐条尝试去掉：去掉后仍不可满足就真的去掉，
否则保留。结束后剩下的就是一组极小冲突集——再去掉任何一条都可满足，
且结果与顺序都是确定的。若一条都不剩仍不可满足，说明冲突出在模型自带
的地点容量上（当前模型里全 none 恒可行，正常不会走到这条分支）。
"""

from .solver import is_satisfiable


def minimal_conflict_ids(inst):
    """返回一组互相矛盾的硬约束 id（按声明顺序）；空列表表示 base-model 冲突。"""
    hard_ids = [rule.rid for rule in inst.rules if rule.is_hard]
    core = list(hard_ids)
    for rid in hard_ids:
        trial = [x for x in core if x != rid]
        if not is_satisfiable(inst, trial):
            core = trial
    return core
