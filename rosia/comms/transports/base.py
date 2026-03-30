from abc import ABC, abstractmethod
from typing import Any, Type

from rosia.comms.Types import ClientType

from ..serializers.base import SerializerBase


class TransportBase(ABC):
    def __init__(
        self,
        type: ClientType,
        serializer: Type[SerializerBase],
        *args,
        **kwargs,
    ):
        self.endpoint: str

    @abstractmethod
    def send(self, msg: Any):
        """Send a message through the transport."""

    @abstractmethod
    def receive(self) -> Any:
        """Receive an already available message from the transport. Returns None if no message is available."""

    @abstractmethod
    def receive_blocking(self, timeout: int = -1) -> Any:
        """Blocking receive. Waits until a message is available and returns it. Returns None if timed out."""

    @abstractmethod
    def wait_for_message(self, timeout: int = -1) -> bool:
        """Wait for a message to be available on the transport. Does not consume the message."""

    @abstractmethod
    def close(self):
        """Close the transport."""
