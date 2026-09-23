"""命令行入口：python -m seatalloc <instance.json>，结果打到 stdout。"""

import json
import sys

from .model import Instance, InstanceError
from .solver import solve_instance


def main(argv=None):
    argv = sys.argv if argv is None else argv
    if len(argv) != 2:
        print("usage: python -m seatalloc <instance.json>", file=sys.stderr)
        return 2
    try:
        with open(argv[1], "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        inst = Instance.from_dict(obj)
    except (OSError, json.JSONDecodeError, InstanceError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    sys.stdout.write(solve_instance(inst))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
