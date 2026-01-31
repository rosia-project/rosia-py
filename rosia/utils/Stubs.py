from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class NodeInitArgs:
    args: Any
    kwargs: Dict[str, Any]


def empty_function(*args, **kwargs):
    pass


def record_init_args(self, *args, **kwargs):
    setattr(self, "_NodeInitArgs", NodeInitArgs(args, kwargs))
