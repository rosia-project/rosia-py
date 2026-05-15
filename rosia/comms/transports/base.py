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
    def wait_for_message(self, timeout: int = -1) -> bool:
        """Wait for a message to be available on the transport.

        This method does not return or consume the message. Use receive() to get the message.

        Args:
            timeout: Timeout in milliseconds. -1 means wait forever.

        Returns:
            True if a message is available, False if timed out.
        """

    def wait_for_message_or_wake(self, wake_socket: Any, timeout: int = -1) -> bool:
        """Optional: wait for either a message or a wake-source readable.

        Transports that support multi-source waiting override this; the
        default falls back to a plain ``wait_for_message`` and ignores the
        wake source. Returns True iff a transport message is available."""
        return self.wait_for_message(timeout=timeout)

    @abstractmethod
    def close(self):
        """Close the transport."""
