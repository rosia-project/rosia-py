from dataclasses import dataclass
from typing import Dict, Generic, Optional, TypeVar

from rosia.time import Time


T = TypeVar("T")


@dataclass
class MessageBase(Generic[T]):
    timestamp: Optional[Time]
    pass


@dataclass
class Message(MessageBase[T]):
    data: Optional[T]  # None means no updates, keep the current value
    from_port: str
    to_port: str
    ENTs: Optional[Dict[str, Time]]  # None means physical message

    def __str__(self) -> str:
        return f"Message(timestamp={self.timestamp}, ENTs={self.ENTs}, data={self.data}, from_port={self.from_port}, to_port={self.to_port})"


@dataclass
class NodeRequestShutdownMessage(MessageBase):
    status_code: int


@dataclass
class NodeForceShutdownRequest(MessageBase):
    status_code: int


@dataclass
class ApplicationRequestShutdownMessage(MessageBase):
    pass


@dataclass
class ApplicationShutdownResponseMessage(MessageBase):
    pass


@dataclass
class ShutdownMessage(MessageBase):
    pass


@dataclass
class ExitMessage(MessageBase):
    node_name: str


@dataclass
class NoMoreMessage(MessageBase):
    from_port: str
    to_port: str
