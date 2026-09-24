"""求解器：约束传播 + 固定顺序分支限界。

值用位掩码表示：bit i 对应 locations[i]，bit n_locations 对应 none。
变量顺序固定为 people × periods，取值顺序固定为 locations 顺序、最后 none，
搜索按这个顺序做深度优先，只在严格更优时替换最优解，从而与 README
的多解规则逐字节对齐。
"""


class _Capacity:
    """某 (地点, 时段) 的人数上限。按「已定（值域收缩为单值）」计数：

    已定数超限即失败；已定数达到上限时把该地点从其他人的值域里删掉。
    """

    __slots__ = ("vars", "bit", "limit")

    def __init__(self, vars_, bit, limit):
        self.vars = vars_
        self.bit = bit
        self.limit = limit

    def apply(self, domains):
        bit = self.bit
        definite = 0
        for v in self.vars:
            if domains[v] == bit:
                definite += 1
                if definite > self.limit:
                    return False
        if definite == self.limit:
            changed = []
            for v in self.vars:
                d = domains[v]
                if d != bit and d & bit:
                    domains[v] = d & ~bit
                    if domains[v] == 0:
                        return False
                    changed.append(v)
            return changed
        return ()


class _NoConsecutive:
    """同一人相邻两个时段不能都排：一方值域里没有 none（必须排）时，
    另一方必须取 none。"""

    __slots__ = ("vars", "none_bit")

    def __init__(self, vars_, none_bit):
        self.vars = vars_
        self.none_bit = none_bit

    def apply(self, domains):
        vs = self.vars
        nb = self.none_bit
        changed = []
        for i in range(len(vs) - 1):
            a, b = vs[i], vs[i + 1]
            da, db = domains[a], domains[b]
            if not da & nb and db & ~nb:
                db &= nb
                domains[b] = db
                if db == 0:
                    return False
                changed.append(b)
            if not db & nb and da & ~nb:
                da &= nb
                domains[a] = da
                if da == 0:
                    return False
                changed.append(a)
        return changed


class _Together:
    """一组人每个时段取值完全相同：值域取交集。"""

    __slots__ = ("period_vars", "full_mask")

    def __init__(self, period_vars, full_mask):
        self.period_vars = period_vars
        self.full_mask = full_mask

    def apply(self, domains):
        changed = []
        for group in self.period_vars:
            common = self.full_mask
            for v in group:
                common &= domains[v]
            if common == 0:
                return False
            for v in group:
                if domains[v] != common:
                    domains[v] = common
                    changed.append(v)
        return changed


class _Apart:
    """一组人每个时段不能同地点：已定为某地点的人，把该地点从组内
    其他人值域里删掉（none 不算地点）。"""

    __slots__ = ("period_vars", "none_bit")

    def __init__(self, period_vars, none_bit):
        self.period_vars = period_vars
        self.none_bit = none_bit

    def apply(self, domains):
        nb = self.none_bit
        changed = []
        for group in self.period_vars:
            taken = 0
            for v in group:
                d = domains[v]
                if d and not d & (d - 1) and d != nb:
                    taken |= d
            if taken:
                for v in group:
                    d = domains[v]
                    if d and not d & (d - 1) and d != nb:
                        continue
                    new = d & ~taken
                    if new != d:
                        if new == 0:
                            return False
                        domains[v] = new
                        changed.append(v)
        return changed


class Problem:
    """把实例（或其硬约束子集）编译成值域、传播器与罚分表。"""

    def __init__(self, instance, hard_rules):
        self.instance = instance
        n_loc = instance.n_locations
        self.none_value = n_loc
        self.n_values = n_loc + 1
        self.full_mask = (1 << self.n_values) - 1
        self.none_bit = 1 << n_loc
        n_vars = instance.n_vars
        self.n_vars = n_vars

        domains = [self.full_mask] * n_vars
        constraints = []
        cap_limits = {}

        for rule in hard_rules:
            f = rule.fields
            if rule.kind == "fixed":
                v = instance.var(f["person"], f["period"])
                domains[v] &= 1 << f["location"]
            elif rule.kind == "forbidden":
                bit = 1 << f["location"]
                for p in range(instance.n_people):
                    v = instance.var(p, f["period"])
                    domains[v] &= self.full_mask & ~bit
            elif rule.kind == "capacity":
                # 在 locations[].capacity 的基础上进一步收紧
                limit = min(f["max"], instance.loc_capacity[f["location"]])
                key = (f["location"], f["period"])
                if limit < cap_limits.get(key, limit + 1):
                    cap_limits[key] = limit
            elif rule.kind == "no_consecutive":
                vs = [instance.var(f["person"], t) for t in range(instance.n_periods)]
                constraints.append(_NoConsecutive(vs, self.none_bit))
            elif rule.kind == "together":
                pvars = [
                    [instance.var(p, t) for p in f["people"]]
                    for t in range(instance.n_periods)
                ]
                constraints.append(_Together(pvars, self.full_mask))
            elif rule.kind == "apart":
                pvars = [
                    [instance.var(p, t) for p in f["people"]]
                    for t in range(instance.n_periods)
                ]
                constraints.append(_Apart(pvars, self.none_bit))

        for (loc, t), limit in cap_limits.items():
            vs = [instance.var(p, t) for p in range(instance.n_people)]
            constraints.append(_Capacity(vs, 1 << loc, limit))

        self.penalty = [[0] * self.n_values for _ in range(n_vars)]
        for rule in instance.soft_rules:
            f = rule.fields
            v = instance.var(f["person"], f["period"])
            weight = f["weight"]
            if rule.kind == "prefer":
                keep = f["location"]
                for value in range(self.n_values):
                    if value != keep:
                        self.penalty[v][value] += weight
            else:  # avoid
                for value in range(self.n_values):
                    if value != self.none_value:
                        self.penalty[v][value] += weight

        self.constraints = constraints
        self.watchers = [[] for _ in range(n_vars)]
        for ci, con in enumerate(constraints):
            seen = set()
            for v in self._constraint_vars(con):
                if v not in seen:
                    seen.add(v)
                    self.watchers[v].append(ci)
        self.initial_domains = domains

    @staticmethod
    def _constraint_vars(con):
        if isinstance(con, (_Capacity, _NoConsecutive)):
            return con.vars
        return [v for group in con.period_vars for v in group]


class Solver:
    def __init__(self, problem):
        self.problem = problem
        self._min_pen_cache = [dict() for _ in range(problem.n_vars)]

    def _propagate(self, domains, queue):
        """把队列里的传播器跑到不动点；任一变量值域为空则失败。"""
        constraints = self.problem.constraints
        watchers = self.problem.watchers
        queue = list(queue)
        in_queue = set(queue)
        while queue:
            ci = queue.pop()
            in_queue.discard(ci)
            changed = constraints[ci].apply(domains)
            if changed is False:
                return False
            for v in changed:
                if domains[v] == 0:
                    return False
                for cj in watchers[v]:
                    if cj not in in_queue:
                        in_queue.add(cj)
                        queue.append(cj)
        return True

    def _min_penalty(self, var, mask):
        """该变量在当前值域下能拿到的最小罚分（下界的基本单元）。"""
        cache = self._min_pen_cache[var]
        hit = cache.get(mask)
        if hit is None:
            pen = self.problem.penalty[var]
            best = None
            for value in range(self.problem.n_values):
                if mask >> value & 1:
                    p = pen[value]
                    if best is None or p < best:
                        best = p
            cache[mask] = best
            return best
        return hit

    def optimize(self):
        """返回 (最小总罚分, 取值数组)；硬约束不可满足时返回 None。"""
        problem = self.problem
        domains = list(problem.initial_domains)
        if not self._propagate(domains, range(len(problem.constraints))):
            return None
        n_vars = problem.n_vars
        n_values = problem.n_values
        penalty = problem.penalty
        watchers = problem.watchers
        best_cost = [None]
        best_assign = [None]
        assignment = [0] * n_vars

        def rec(idx, domains, cost):
            if idx == n_vars:
                if best_cost[0] is None or cost < best_cost[0]:
                    best_cost[0] = cost
                    best_assign[0] = assignment[:]
                return
            bc = best_cost[0]
            if bc is not None:
                # 下界：已累积罚分 + 每个未定变量在当前值域下的最小罚分；
                # 下界不严格小于当前最优时，该分支不可能产生更优解，剪掉。
                lb = cost
                for i in range(idx, n_vars):
                    lb += self._min_penalty(i, domains[i])
                    if lb >= bc:
                        return
            d = domains[idx]
            for value in range(n_values):
                if not (d >> value) & 1:
                    continue
                nd = list(domains)
                nd[idx] = 1 << value
                assignment[idx] = value
                if self._propagate(nd, watchers[idx]):
                    rec(idx + 1, nd, cost + penalty[idx][value])

        rec(0, domains, 0)
        if best_cost[0] is None:
            return None
        return best_cost[0], best_assign[0]

    def feasible(self):
        """只判可满足性（忽略软约束），找到第一个可行解即停。"""
        problem = self.problem
        domains = list(problem.initial_domains)
        if not self._propagate(domains, range(len(problem.constraints))):
            return False
        n_vars = problem.n_vars
        n_values = problem.n_values
        watchers = problem.watchers
        found = [False]

        def rec(idx, domains):
            if found[0]:
                return
            if idx == n_vars:
                found[0] = True
                return
            d = domains[idx]
            for value in range(n_values):
                if not (d >> value) & 1:
                    continue
                nd = list(domains)
                nd[idx] = 1 << value
                if self._propagate(nd, watchers[idx]):
                    rec(idx + 1, nd)
                    if found[0]:
                        return

        rec(0, domains)
        return found[0]
