"""求解器：硬约束传播 + 分支限界。

- 变量 = (人, 时段)，下标按 people 顺序 × periods 顺序排列；
- 取值 = 地点下标，最后一个取值是 none；值域用位掩码表示；
- 传播：fixed/forbidden 直接收缩初始值域；together 对同组同时段的值域取交集；
  apart、no_consecutive、capacity 在某个变量被定成某个地点后向相关变量收缩；
  容量按「已定人数」检查上限，定满后把该地点从同时段其他人的值域里删掉；
- 下界：每个变量当前值域上的最小软约束罚分之和，用于分支限界；
- 搜索：先用 MRV 顺序求出最优代价，再按 README 规定的固定变量/取值顺序
  找出第一个达到该代价的可行解，保证输出与多解规则逐字节一致。
"""

from .model import Instance  # noqa: F401  (re-export 给类型标注用)

_INF = float("inf")


class _Problem:
    """把实例编译成传播结构；active_hard 非 None 时只启用这些硬约束（求冲突集用）。"""

    def __init__(self, inst, active_hard=None, with_soft=True):
        self.inst = inst
        self.n_people = len(inst.people)
        self.n_periods = len(inst.periods)
        self.n_locations = len(inst.locations)
        self.n_values = self.n_locations + 1  # 最后一个取值是 none
        self.none_bit = 1 << self.n_locations
        self.full_domain = (1 << self.n_values) - 1
        self.n_vars = self.n_people * self.n_periods

        # cap[t][l]：capacity 规则给出的 (时段, 地点) 人数上限；None 表示不限
        self.cap = [[None] * self.n_locations for _ in range(self.n_periods)]
        self.together = [[] for _ in range(self.n_people)]   # person -> [group]
        self.apart = [[] for _ in range(self.n_people)]      # person -> [group]
        self.no_consecutive = [False] * self.n_people
        self.penalty = [[0] * self.n_values for _ in range(self.n_vars)]
        self._lb_cache = [dict() for _ in range(self.n_vars)]
        self.domains0 = [self.full_domain] * self.n_vars
        self.period_vars = [
            [p * self.n_periods + t for p in range(self.n_people)]
            for t in range(self.n_periods)
        ]

        for rule in inst.rules:
            if rule.is_hard:
                if active_hard is not None and rule.rid not in active_hard:
                    continue
                self._add_hard(rule)
            elif with_soft:
                self._add_soft(rule)

    def _var(self, person, period):
        return (
            self.inst.person_index[person] * self.n_periods
            + self.inst.period_index[period]
        )

    def _add_hard(self, rule):
        f = rule.fields
        kind = rule.kind
        if kind == "fixed":
            bit = 1 << self.inst.location_index[f["location"]]
            self.domains0[self._var(f["person"], f["period"])] &= bit
        elif kind == "forbidden":
            t = self.inst.period_index[f["period"]]
            mask = ~(1 << self.inst.location_index[f["location"]])
            for v in self.period_vars[t]:
                self.domains0[v] &= mask
        elif kind == "capacity":
            t = self.inst.period_index[f["period"]]
            loc = self.inst.location_index[f["location"]]
            cur = self.cap[t][loc]
            self.cap[t][loc] = f["max"] if cur is None else min(cur, f["max"])
        elif kind == "no_consecutive":
            self.no_consecutive[self.inst.person_index[f["person"]]] = True
        elif kind == "together":
            group = [self.inst.person_index[x] for x in f["people"]]
            for p in group:
                self.together[p].append(group)
        elif kind == "apart":
            group = [self.inst.person_index[x] for x in f["people"]]
            for p in group:
                self.apart[p].append(group)

    def _add_soft(self, rule):
        f = rule.fields
        pen = self.penalty[self._var(f["person"], f["period"])]
        weight = f["weight"]
        if rule.kind == "prefer":
            loc = self.inst.location_index[f["location"]]
            for val in range(self.n_values):
                if val != loc:
                    pen[val] += weight
        else:  # avoid：有排（非 none）就罚
            for val in range(self.n_locations):
                pen[val] += weight

    # ------------------------------------------------------------------
    # 传播
    # ------------------------------------------------------------------

    def _propagate(self, domains, counts, seated, queue):
        """把 queue 里值域被收缩的变量传播到不动点；返回 False 表示冲突。

        domains[v] 是值域位掩码；counts[t][l] 是 (时段, 地点) 已定人数；
        seated[v] 标记变量是否已按「定为某地点」处理过，保证容量只计一次。
        """
        head = 0
        while head < len(queue):
            v = queue[head]
            head += 1
            d = domains[v]
            if d == 0:
                return False
            p, t = divmod(v, self.n_periods)

            # together：同组的人同一时段取值必须相同，值域取交集
            for group in self.together[p]:
                common = self.full_domain
                for pm in group:
                    common &= domains[pm * self.n_periods + t]
                if common == 0:
                    return False
                for pm in group:
                    u = pm * self.n_periods + t
                    if domains[u] != common:
                        domains[u] = common
                        queue.append(u)

            d = domains[v]
            if seated[v] or d == self.none_bit or d & (d - 1):
                continue
            # d 是某个地点的单例：触发 apart / no_consecutive / capacity
            seated[v] = 1
            bit = d
            loc = bit.bit_length() - 1

            cap = self.cap[t][loc]
            if cap is not None:
                cnt = counts[t][loc] + 1
                counts[t][loc] = cnt
                if cnt > cap:
                    return False
                if cnt == cap:
                    # 已定人数达到上限：该地点从同时段其他人值域里删掉
                    for u in self.period_vars[t]:
                        du = domains[u]
                        if du != bit and du & bit:
                            du &= ~bit
                            if du == 0:
                                return False
                            domains[u] = du
                            queue.append(u)

            # apart：同组其他人同一时段不能坐这个地点（none 不受影响）
            for group in self.apart[p]:
                for pm in group:
                    if pm == p:
                        continue
                    u = pm * self.n_periods + t
                    du = domains[u]
                    if du & bit:
                        du &= ~bit
                        if du == 0:
                            return False
                        domains[u] = du
                        queue.append(u)

            # no_consecutive：相邻两个时段不能都排，邻时段只剩 none
            if self.no_consecutive[p]:
                for t2 in (t - 1, t + 1):
                    if 0 <= t2 < self.n_periods:
                        u = p * self.n_periods + t2
                        du = domains[u]
                        du2 = du & self.none_bit
                        if du2 != du:
                            if du2 == 0:
                                return False
                            domains[u] = du2
                            queue.append(u)
        return True

    def _initial_state(self):
        domains = list(self.domains0)
        counts = [[0] * self.n_locations for _ in range(self.n_periods)]
        seated = bytearray(self.n_vars)
        if not self._propagate(domains, counts, seated, list(range(self.n_vars))):
            return None
        return domains, counts, seated

    # ------------------------------------------------------------------
    # 下界
    # ------------------------------------------------------------------

    def _min_penalty(self, v, mask):
        """变量 v 在值域 mask 上的最小罚分，按 (v, mask) 缓存。"""
        cache = self._lb_cache[v]
        hit = cache.get(mask)
        if hit is not None:
            return hit
        pen = self.penalty[v]
        best = _INF
        bits = mask
        val = 0
        while bits:
            if bits & 1 and pen[val] < best:
                best = pen[val]
            bits >>= 1
            val += 1
        cache[mask] = best
        return best

    def _lower_bound(self, domains, limit):
        """每个变量当前值域上的最小罚分之和；达到 limit 就提前返回。"""
        total = 0
        for v in range(self.n_vars):
            total += self._min_penalty(v, domains[v])
            if total >= limit:
                return total
        return total

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def solve(self):
        """返回 (最优代价, 固定顺序下第一个最优解的值域)；不可行返回 None。"""
        state = self._initial_state()
        if state is None:
            return None
        domains, counts, seated = state
        best = [None]
        self._optimize(list(domains), [r[:] for r in counts], bytearray(seated), best)
        if best[0] is None:
            return None
        final = self._canonical(
            list(domains), [r[:] for r in counts], bytearray(seated), best[0], 0
        )
        return best[0], final

    def _branch(self, domains, counts, seated, v, bit):
        nd = list(domains)
        nd[v] = bit
        nc = [row[:] for row in counts]
        ns = bytearray(seated)
        if not self._propagate(nd, nc, ns, [v]):
            return None
        return nd, nc, ns

    def _most_constrained(self, domains):
        pick = -1
        pick_size = self.n_values + 1
        for v in range(self.n_vars):
            d = domains[v]
            if d & (d - 1):  # 非单例才算未定
                size = bin(d).count("1")
                if size < pick_size:
                    pick = v
                    pick_size = size
        return pick

    def _optimize(self, domains, counts, seated, best):
        """MRV 顺序的分支限界，只求最优代价（存入 best[0]）。"""
        pick = self._most_constrained(domains)
        if pick < 0:
            cost = 0
            for v in range(self.n_vars):
                cost += self.penalty[v][domains[v].bit_length() - 1]
            if best[0] is None or cost < best[0]:
                best[0] = cost
            return
        d = domains[pick]
        pen = self.penalty[pick]
        values = [val for val in range(self.n_values) if d >> val & 1]
        values.sort(key=lambda val: pen[val])
        for val in values:
            state = self._branch(domains, counts, seated, pick, 1 << val)
            if state is None:
                continue
            nd, nc, ns = state
            if best[0] is not None and self._lower_bound(nd, best[0]) >= best[0]:
                continue
            self._optimize(nd, nc, ns, best)

    def _canonical(self, domains, counts, seated, target, idx):
        """按固定变量/取值顺序，找第一个总罚分等于 target 的可行解。"""
        if idx == self.n_vars:
            return list(domains)
        d = domains[idx]
        for val in range(self.n_values):
            bit = 1 << val
            if not d & bit:
                continue
            state = self._branch(domains, counts, seated, idx, bit)
            if state is None:
                continue
            nd, nc, ns = state
            if self._lower_bound(nd, target + 1) > target:
                continue
            result = self._canonical(nd, nc, ns, target, idx + 1)
            if result is not None:
                return result
        return None

    def feasible(self):
        """只判断硬约束是否可满足（软约束在编译期已关掉）。"""
        state = self._initial_state()
        if state is None:
            return False
        return self._feasible_dfs(*state)

    def _feasible_dfs(self, domains, counts, seated):
        pick = self._most_constrained(domains)
        if pick < 0:
            return True
        d = domains[pick]
        for val in range(self.n_values):
            bit = 1 << val
            if d & bit:
                state = self._branch(domains, counts, seated, pick, bit)
                if state is not None and self._feasible_dfs(*state):
                    return True
        return False


def is_satisfiable(inst, hard_ids=None):
    """只考虑硬约束是否可满足；hard_ids 为 None 表示启用全部硬约束。"""
    active = None if hard_ids is None else set(hard_ids)
    return _Problem(inst, active_hard=active, with_soft=False).feasible()


def solve_instance(inst):
    """求解实例，返回 README 规定的输出文本（每行以 LF 结尾）。"""
    result = _Problem(inst).solve()
    if result is None:
        from .conflict import minimal_conflict_ids

        core = minimal_conflict_ids(inst)
        if not core:
            return "unsat,base-model\n"
        return "unsat," + ",".join(core) + "\n"
    cost, domains = result
    n_periods = len(inst.periods)
    n_locations = len(inst.locations)
    lines = ["cost,%d" % cost]
    for p, person in enumerate(inst.people):
        for t, period in enumerate(inst.periods):
            val = domains[p * n_periods + t].bit_length() - 1
            name = inst.locations[val][0] if val < n_locations else "none"
            lines.append("%s,%s,%s" % (person, period, name))
    return "\n".join(lines) + "\n"
