from rosia.frontend import (
    reaction as reaction,
    Node as Node,
    InputPort as InputPort,
    OutputPort as OutputPort,
)
from rosia.coordinate import Coordinator as Coordinator
from rosia.coordinate import request_shutdown as request_shutdown
from rosia.rerun import RerunManager as RerunManager

rerun_manager = RerunManager()

# Monkey patches
node_runtime_instance = None
