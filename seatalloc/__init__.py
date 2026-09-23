"""工位与会议室排班求解库。"""

from .model import Instance, InstanceError, Rule
from .solver import is_satisfiable, solve_instance

__all__ = ["Instance", "InstanceError", "Rule", "is_satisfiable", "solve_instance"]
