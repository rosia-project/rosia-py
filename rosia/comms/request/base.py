from abc import ABC, abstractmethod
from typing import Any, Callable, Type

from rosia.comms.Types import ClientType

from ..serializers.base import SerializerBase


class ClientBase(ABC):
    def __init__(
        self,
        type: ClientType,
        serializer: Type[SerializerBase],
        *args,
        **kwargs,
    ):
        self.endpoint: str

    @abstractmethod
    async def request(self, msg: Any):
        """Send a message through the transport."""

    @abstractmethod
    def close(self):
        """Close the transport."""


class ServerBase(ABC):
    def __init__(
        self,
        type: ClientType,
        serializer: Type[SerializerBase],
        *args,
        **kwargs,
    ):
        self.endpoint: str

    @abstractmethod
    def register_callback(self, callback: Callable[[Any], Any]):
        """Register a callback to be called when a message is received."""

    @abstractmethod
    def close(self):
        """Close the server."""
