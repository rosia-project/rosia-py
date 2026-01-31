from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar, TYPE_CHECKING

from rosia.comms.Types import ClientType
from rosia.comms.transports import TransportBase
from rosia.coordinate.messages.base import Message
from rosia.time import Time, forever

if TYPE_CHECKING:
    from rosia.coordinate.Coordinator import Node

T = TypeVar("T")


class Port(Generic[T]):
    def _set_endpoint(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def _get_endpoint(self) -> str:
        return self.endpoint


# This is used to connect the input port to the output port
class InputPortConnector(Port[T]):
    def __init__(
        self,
        owner: "Node",
        name: Optional[str],
        input_port_user_object: "InputPortRuntimeObj[T]",
        trigger_functions: List[Callable],
        affected_output_ports: "List[OutputPortConnector[T]]",
    ) -> None:
        self.upstream_ports: List[OutputPortConnector[T]] = []
        self.trigger_functions: List[Callable] = trigger_functions
        self.value: Optional[T] = None
        self.owner = owner
        self.name = f"{owner.node_name}.{name}"
        self.input_port_user_object = input_port_user_object
        self.safe_to_advance_time: Time = forever

        self.port_type: ClientType
        self.transport: Optional[TransportBase] = (
            None  # Only set for SENDER ports (downstream ports of output ports)
        )
        self.affected_output_ports: List[OutputPortConnector[T]] = affected_output_ports

    def __set__(self, args: List[Any], kwargs: Dict[str, Any]) -> None:
        raise TypeError("InputPort is immutable")

    def update_safe_to_advance_time(self) -> None:
        min_safe_to_advance_time = forever
        for upstream_port in self.upstream_ports:
            min_safe_to_advance_time = min(
                min_safe_to_advance_time, upstream_port.safe_to_advance_time
            )
        self.safe_to_advance_time = min_safe_to_advance_time

    def get_upstream_port_by_name(self, name: str) -> "OutputPortConnector[T]":
        for upstream_port in self.upstream_ports:
            if upstream_port.name == name:
                return upstream_port
        raise ValueError(f"Upstream port {name} not found")

    def _get_endpoint(self) -> str:
        # Get endpoint from parent node's transport
        if self.owner.transport is None:
            raise RuntimeError(
                f"Transport not initialized for node {self.owner.node_name}"
            )
        return self.owner.transport.endpoint

    def set_value(self, msg: Message[T]) -> None:
        if self.port_type == ClientType.SENDER:
            # This is the downstream of an output port, we send the value to the corresponding input port
            # Ensure to_port is set to this input port's name
            if msg.to_port is None:
                msg.to_port = self.name
            if self.transport is None:
                raise RuntimeError(f"Transport not set for sender port {self.name}")
            self.transport.send(msg)
        else:
            self.value = msg.data
            self.input_port_user_object._set_value(msg.data)

    def _trigger(self) -> None:
        for function in self.trigger_functions:
            function(self.owner.node_instance)

    def __str__(self) -> str:
        return f"<InputPort {self.owner.node_cls.__name__}.{self.name}>"


# This is called by user code to get the value of the port
class InputPortRuntimeObj(Generic[T]):
    def __init__(self, parent: "Node", initial_value: T = None) -> None:
        self.parent = parent
        self.value: T = initial_value

    # This is meant to be called by the coordinator to set the value of the user object
    def _set_value(self, value: T) -> None:
        self.value = value

    # The user should not be able to set the value of the port
    def __set__(self, value: T) -> None:
        raise TypeError("InputPortRuntimeObj is immutable")

    def __get__(self, instance: Any, owner: type) -> T:
        return self.value


# This is used to connect the output port to the input port
class OutputPortConnector(Port[T]):
    def __init__(self, owner: "Node", name: Optional[str]) -> None:
        self.downstream_ports: List[InputPortConnector[T]] = []
        self.owner = owner
        self.name = f"{owner.node_name}.{name}"
        self.endpoint = None
        self.safe_to_advance_time: Time = forever

    def set_next_timestamp(self, first_timestamp: Time) -> None:
        self.safe_to_advance_time = first_timestamp

    def set_value(self, value: T) -> None:
        self._set_value(value)

    def _set_value(
        self,
        value: T,
        timestamp: Optional[Time] = None,
        next_timestamp: Optional[Time] = None,
    ) -> None:
        for downstream_port in self.downstream_ports:
            downstream_port.set_value(
                Message(
                    data=value,
                    timestamp=timestamp,
                    next_timestamp=next_timestamp,
                    from_port=self.name,
                    to_port=downstream_port.name,
                )
            )

    def connect(self, other: InputPortConnector[T]) -> None:
        if not isinstance(other, InputPortConnector):
            raise TypeError("Can only connect OutputPort to InputPort")
        if other in self.downstream_ports:
            raise ValueError(f"Port {other.name} is already connected to {self.name}")
        self.downstream_ports.append(other)
        other.upstream_ports.append(self)

    # >> shorthand for connect
    def __rshift__(self, other: InputPortConnector[T]) -> "OutputPortConnector[T]":
        self.connect(other)
        return self

    # >>= shorthand for connect
    def __irshift__(self, other: InputPortConnector[T]) -> "OutputPortConnector[T]":
        self.connect(other)
        return self

    def __str__(self) -> str:
        return f"<OutputPort {self.owner.node_cls.__name__}.{self.name}>"


# This is called by user code to set the value of the port
class OutputPortRuntimeObj(Generic[T]):
    def __init__(self, parent: "Node", output_port: OutputPortConnector[T]) -> None:
        self.parent = parent
        self.output_port = output_port

    # When the user sets the port, the value is passed to the coordinator to be sent to the downstream ports
    def __set__(self, value: T) -> None:
        raise TypeError("OutputPortRuntimeObj is immutable")

    def set_next_timestamp(self, first_timestamp: Time) -> None:
        self.output_port.set_next_timestamp(first_timestamp)

    def __call__(
        self,
        value: T,
        timestamp: Optional[Time] = None,
        next_timestamp: Optional[Time] = None,
    ) -> None:
        if timestamp is not None:
            if next_timestamp is None:
                raise ValueError(
                    "next_timestamp must be provided if timestamp is provided"
                )
            if timestamp > next_timestamp:
                raise ValueError(
                    f"Timestamp {timestamp} is greater than next_timestamp {next_timestamp}"
                )
        else:
            assert next_timestamp is None, (
                "If timestamp is not provided, next_timestamp must be None"
            )
            timestamp = self.parent.current_time
            next_timestamp = self.parent.next_time
        self.output_port._set_value(value, timestamp, next_timestamp)
