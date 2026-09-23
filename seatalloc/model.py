"""实例模型：JSON 解析与格式校验。

实例里引用的 people / periods / locations 必须都声明过，否则算实例格式错误，
抛出 InstanceError。
"""

HARD_KINDS = ("fixed", "forbidden", "capacity", "no_consecutive", "together", "apart")
SOFT_KINDS = ("prefer", "avoid")

_RULE_FIELDS = {
    "fixed": ("person", "period", "location"),
    "forbidden": ("location", "period"),
    "capacity": ("location", "period", "max"),
    "no_consecutive": ("person",),
    "together": ("people",),
    "apart": ("people",),
    "prefer": ("person", "period", "location", "weight"),
    "avoid": ("person", "period", "weight"),
}


class InstanceError(ValueError):
    """实例格式错误（缺字段、类型不对、引用了不存在的名字等）。"""


def _err(msg):
    raise InstanceError(msg)


class Rule:
    """一条规则；fields 里是按 kind 校验过的原始字段。"""

    __slots__ = ("rid", "kind", "fields", "order")

    def __init__(self, rid, kind, fields, order):
        self.rid = rid
        self.kind = kind
        self.fields = fields
        self.order = order

    @property
    def is_hard(self):
        return self.kind in HARD_KINDS


class Instance:
    def __init__(self, case_id, periods, locations, people, rules):
        self.case_id = case_id
        self.periods = periods            # [str]，数组顺序即变量顺序
        self.locations = locations        # [(id, capacity)]，数组顺序即取值顺序
        self.people = people              # [str]
        self.rules = rules                # [Rule]，声明顺序
        self.period_index = {name: i for i, name in enumerate(periods)}
        self.location_index = {name: i for i, (name, _) in enumerate(locations)}
        self.person_index = {name: i for i, name in enumerate(people)}

    @classmethod
    def from_dict(cls, obj):
        if not isinstance(obj, dict):
            _err("实例必须是一个 JSON 对象")
        case_id = obj.get("case_id")
        periods = _str_list(obj.get("periods"), "periods")
        people = _str_list(obj.get("people"), "people")
        locations = _parse_locations(obj.get("locations"))
        rules_obj = obj.get("rules", [])
        if not isinstance(rules_obj, list):
            _err("rules 必须是数组")
        known = {
            "periods": set(periods),
            "people": set(people),
            "locations": {name for name, _ in locations},
        }
        rules = []
        seen_ids = set()
        for order, raw in enumerate(rules_obj):
            rules.append(_parse_rule(raw, order, known, seen_ids))
        return cls(case_id, periods, locations, people, rules)


def _str_list(value, name):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        _err("%s 必须是字符串数组" % name)
    if len(set(value)) != len(value):
        _err("%s 里有重复名字" % name)
    return list(value)


def _nonneg_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _err("%s 必须是非负整数" % name)
    return value


def _parse_locations(value):
    if not isinstance(value, list):
        _err("locations 必须是数组")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            _err("locations 里每项都要有字符串 id")
        lid = item["id"]
        if lid in seen:
            _err("locations 里有重复 id: %s" % lid)
        seen.add(lid)
        cap = _nonneg_int(item.get("capacity"), "location %s 的 capacity" % lid)
        result.append((lid, cap))
    return result


def _parse_rule(raw, order, known, seen_ids):
    if not isinstance(raw, dict):
        _err("第 %d 条规则必须是对象" % (order + 1))
    kind = raw.get("kind")
    if kind not in _RULE_FIELDS:
        _err("第 %d 条规则 kind 非法: %r" % (order + 1, kind))
    rid = raw.get("id")
    if kind in HARD_KINDS:
        if not isinstance(rid, str) or not rid:
            _err("硬约束必须有字符串 id（第 %d 条规则）" % (order + 1))
    elif rid is not None and not isinstance(rid, str):
        _err("规则 id 必须是字符串（第 %d 条规则）" % (order + 1))
    if rid is not None:
        if rid in seen_ids:
            _err("规则 id 重复: %s" % rid)
        seen_ids.add(rid)
    fields = {}
    for name in _RULE_FIELDS[kind]:
        if name not in raw:
            _err("规则 %s 缺少字段 %s" % (rid or ("#%d" % (order + 1)), name))
        fields[name] = raw[name]

    def check_name(value, pool, what):
        if not isinstance(value, str) or value not in known[pool]:
            _err("规则 %s 引用了不存在的%s: %r" % (rid, what, value))

    if "person" in fields:
        check_name(fields["person"], "people", "人员")
    if "period" in fields:
        check_name(fields["period"], "periods", "时段")
    if "location" in fields:
        check_name(fields["location"], "locations", "地点")
    if "people" in fields:
        group = fields["people"]
        if not isinstance(group, list) or not group:
            _err("规则 %s 的 people 必须是非空数组" % rid)
        for name in group:
            check_name(name, "people", "人员")
    if "max" in fields:
        fields["max"] = _nonneg_int(fields["max"], "规则 %s 的 max" % rid)
    if "weight" in fields:
        weight = fields["weight"]
        if isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0:
            _err("规则 %s 的 weight 必须是正整数" % rid)
    return Rule(rid, kind, fields, order)
