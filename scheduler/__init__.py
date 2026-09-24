"""工位与会议室排班求解库。"""

from .api import solve_instance
from .model import Instance, InstanceError

__all__ = ["solve_instance", "Instance", "InstanceError"]
