"""命令行入口：python -m scheduler <instance.json>，结果写到标准输出。"""

import json
import sys

from .api import solve_instance
from .model import InstanceError


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("用法: python -m scheduler <instance.json>\n")
        return 2
    try:
        with open(argv[1], "r", encoding="utf-8") as fh:
            data = json.load(fh)
        output = solve_instance(data)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("读实例失败: %s\n" % exc)
        return 2
    except InstanceError as exc:
        sys.stderr.write("实例格式错误: %s\n" % exc)
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.setrecursionlimit(100000)
    sys.exit(main(sys.argv))
