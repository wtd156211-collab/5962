"""实例模型：解析并校验 JSON 实例，把人/时段/地点解析为下标。"""

HARD_KINDS = ("fixed", "forbidden", "capacity", "no_consecutive", "together", "apart")
SOFT_KINDS = ("prefer", "avoid")
NONE_VALUE = "none"


class InstanceError(ValueError):
    """实例格式错误（引用不存在的名字、缺字段、权重非法等）。"""


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


class Rule:
    """一条校验过的规则；字段里的人/时段/地点都已解析为下标。"""

    __slots__ = ("index", "id", "kind", "fields")

    def __init__(self, index, rule_id, kind, fields):
        self.index = index
        self.id = rule_id
        self.kind = kind
        self.fields = fields


class Instance:
    def __init__(self, data):
        if not isinstance(data, dict):
            raise InstanceError("实例必须是 JSON 对象")
        self.case_id = data.get("case_id", "")
        self.periods = self._names(data.get("periods"), "periods")
        self.people = self._names(data.get("people"), "people")

        locations = data.get("locations")
        if not isinstance(locations, list) or not locations:
            raise InstanceError("locations 必须是非空数组")
        self.locations = []
        self.loc_capacity = []
        for loc in locations:
            if not isinstance(loc, dict) or not isinstance(loc.get("id"), str):
                raise InstanceError("每个地点必须有字符串 id")
            cap = loc.get("capacity")
            if not _is_int(cap) or cap < 0:
                raise InstanceError("地点 %s 的 capacity 必须是非负整数" % loc.get("id"))
            self.locations.append(loc["id"])
            self.loc_capacity.append(cap)

        self._check_dupes(self.periods, "periods")
        self._check_dupes(self.people, "people")
        self._check_dupes(self.locations, "locations")

        self.period_index = {name: i for i, name in enumerate(self.periods)}
        self.person_index = {name: i for i, name in enumerate(self.people)}
        self.location_index = {name: i for i, name in enumerate(self.locations)}

        rules = data.get("rules", [])
        if not isinstance(rules, list):
            raise InstanceError("rules 必须是数组")
        self.rules = [self._rule(i, raw) for i, raw in enumerate(rules)]
        self.hard_rules = [r for r in self.rules if r.kind in HARD_KINDS]
        self.soft_rules = [r for r in self.rules if r.kind in SOFT_KINDS]

        self.n_periods = len(self.periods)
        self.n_people = len(self.people)
        self.n_locations = len(self.locations)
        self.n_vars = self.n_people * self.n_periods

    def var(self, person_idx, period_idx):
        """变量下标：people 顺序 × periods 顺序（人为主序）。"""
        return person_idx * self.n_periods + period_idx

    @staticmethod
    def _names(value, field):
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise InstanceError("%s 必须是字符串数组" % field)
        return list(value)

    @staticmethod
    def _check_dupes(names, field):
        if len(set(names)) != len(names):
            raise InstanceError("%s 里有重复的名字" % field)

    def _person(self, raw, index):
        name = raw.get("person")
        if name not in self.person_index:
            raise InstanceError("rules[%d] 引用了不存在的人: %r" % (index, name))
        return self.person_index[name]

    def _period(self, raw, index):
        name = raw.get("period")
        if name not in self.period_index:
            raise InstanceError("rules[%d] 引用了不存在的时段: %r" % (index, name))
        return self.period_index[name]

    def _location(self, raw, index):
        name = raw.get("location")
        if name not in self.location_index:
            raise InstanceError("rules[%d] 引用了不存在的地点: %r" % (index, name))
        return self.location_index[name]

    def _people_list(self, raw, index):
        names = raw.get("people")
        if not isinstance(names, list) or not names:
            raise InstanceError("rules[%d] 的 people 必须是非空数组" % index)
        result = []
        for name in names:
            if name not in self.person_index:
                raise InstanceError("rules[%d] 引用了不存在的人: %r" % (index, name))
            result.append(self.person_index[name])
        return result

    @staticmethod
    def _weight(raw, index):
        weight = raw.get("weight")
        if not _is_int(weight) or weight <= 0:
            raise InstanceError("rules[%d] 的 weight 必须是正整数" % index)
        return weight

    def _rule(self, index, raw):
        if not isinstance(raw, dict):
            raise InstanceError("rules[%d] 必须是对象" % index)
        kind = raw.get("kind")
        if kind not in HARD_KINDS + SOFT_KINDS:
            raise InstanceError("rules[%d] 未知的 kind: %r" % (index, kind))
        rule_id = raw.get("id")
        if kind in HARD_KINDS and not (isinstance(rule_id, str) and rule_id):
            raise InstanceError("rules[%d] 硬约束必须有非空字符串 id" % index)

        if kind == "fixed":
            fields = {
                "person": self._person(raw, index),
                "period": self._period(raw, index),
                "location": self._location(raw, index),
            }
        elif kind == "forbidden":
            fields = {
                "location": self._location(raw, index),
                "period": self._period(raw, index),
            }
        elif kind == "capacity":
            limit = raw.get("max")
            if not _is_int(limit) or limit < 0:
                raise InstanceError("rules[%d] 的 max 必须是非负整数" % index)
            fields = {
                "location": self._location(raw, index),
                "period": self._period(raw, index),
                "max": limit,
            }
        elif kind == "no_consecutive":
            fields = {"person": self._person(raw, index)}
        elif kind in ("together", "apart"):
            fields = {"people": self._people_list(raw, index)}
        elif kind == "prefer":
            fields = {
                "person": self._person(raw, index),
                "period": self._period(raw, index),
                "location": self._location(raw, index),
                "weight": self._weight(raw, index),
            }
        else:  # avoid
            fields = {
                "person": self._person(raw, index),
                "period": self._period(raw, index),
                "weight": self._weight(raw, index),
            }
        return Rule(index, rule_id, kind, fields)
