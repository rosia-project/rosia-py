from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Tuple


@dataclass
class ExecutorMessage:
    error_message: Optional[str] = None


@dataclass
class ExecutorStartupMessage(ExecutorMessage):
    executor_receive_endpoint: str = ""


@dataclass
class ExecutorExecuteRequestMessage(ExecutorMessage):
    func_name: str = ""
    args: Tuple[Any, ...] = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    no_ret: bool = False


@dataclass
class ExecutorExecuteResponseMessage(ExecutorMessage):
    result: Any = None
