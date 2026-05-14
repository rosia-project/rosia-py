from rosia.frontend import (
    reaction as reaction,
    trigger as trigger,
    Node as Node,
    InputPort as InputPort,
    OutputPort as OutputPort,
)
from rosia.coordinate import Application as Application
from rosia.coordinate import request_shutdown as request_shutdown
from rosia.coordinate import logical_time as logical_time

from rosia.rerun import RerunManager as RerunManager
from rosia.logging import Logger as Logger
from rosia.utils import ObjectProxy as ObjectProxy
from typing import TYPE_CHECKING

rerun_manager = RerunManager()
log = logger = ObjectProxy(Logger(), module="rosia", attr="logger")

if TYPE_CHECKING:
    log = logger = Logger()


# Monkey patches
node_runtime_instance = None  # type: ignore

if TYPE_CHECKING:
    from rosia.coordinate.Node import NodeRuntime

    node_runtime_instance: "NodeRuntime"
