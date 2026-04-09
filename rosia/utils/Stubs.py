from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class NodeInitArgs:
    args: Any
    kwargs: Dict[str, Any]


def empty_function(*args, **kwargs):
    pass


def record_init_args(self, *args, **kwargs):
    if hasattr(self, "_rosia_annotations"):
        self._rosia_annotations["init_args"] = NodeInitArgs(args, kwargs)
    else:
        raise RuntimeError("Node has no _rosia_annotations attribute. This is a bug within the Rosia framework.")
