from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    TypeVar,
    TYPE_CHECKING,
)

from rosia.comms.Types import ClientType
from rosia.comms.transports import TransportBase
from rosia.coordinate.messages.base import Message
from rosia.time import Time, forever

if TYPE_CHECKING:
    from rosia.coordinate.Node import NodeRuntime
    from rosia.coordinate.Port import InputPortRuntimeObj

T = TypeVar("T")


class PortConnector(Generic[T]):
    def _set_endpoint(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def _get_endpoint(self) -> str:
        return self.endpoint


# This is used to connect the input port to the output port
class InputPortConnector(PortConnector[T]):
    def __init__(
        self,
        owner: "NodeRuntime",
        name: Optional[str],
        input_port_runtime_object: "InputPortRuntimeObj[T]",
        trigger_functions: List[Callable],
        affected_output_ports: "List[OutputPortConnector[T]]",
    ) -> None:
        self.upstream_ports: List[OutputPortConnector[T]] = []
        self.trigger_functions: List[Callable] = trigger_functions
        self.value: Optional[T] = None
        self.owner = owner
        self.name = f"{owner.node_name}.{name}"
        self.input_port_runtime_object = input_port_runtime_object
        self.safe_to_advance_to: Time = forever

        self.port_type: ClientType
        self.transport: Optional[TransportBase] = (
            None  # Only set for SENDER ports (downstream ports of output ports)
        )
        self.affected_output_ports: List[OutputPortConnector[T]] = affected_output_ports
        self.active_upstream_count: int = 0  # Set during coordinator setup

    def __set__(self, args: List[Any], kwargs: Dict[str, Any]) -> None:
        raise TypeError("InputPort is immutable")

    def update_safe_to_advance_to(self) -> None:
        min_safe_to_advance_to = forever
        for upstream_port in self.upstream_ports:
            min_safe_to_advance_to = min(
                min_safe_to_advance_to, upstream_port.safe_to_advance_to
            )
        self.safe_to_advance_to = min_safe_to_advance_to

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
            self.input_port_runtime_object._set_value(msg.data)

    def set_value_from_event(self, value: T) -> None:
        self.value = value
        self.input_port_runtime_object._set_value(value)

    def _trigger(self) -> None:
        for function in self.trigger_functions:
            function(self.owner.node_instance)

    def __str__(self) -> str:
        return f"<InputPort {self.owner.node_cls.__name__}.{self.name}>"


# This is used to connect the output port to the input port
class OutputPortConnector(PortConnector[T]):
    def __init__(self, owner: "NodeRuntime", name: Optional[str]) -> None:
        self.downstream_ports: List[Tuple[InputPortConnector[T], bool]] = []
        self.owner = owner
        self.name = f"{owner.node_name}.{name}"
        self.endpoint = None
        self.safe_to_advance_to: Time = forever

    def set_DSTAT(self, first_timestamp: Time) -> None:
        self.safe_to_advance_to = first_timestamp

    def set_value(self, value: T) -> None:
        self._set_value(value)

    def _set_value(
        self,
        value: T,
        timestamp: Optional[Time] = None,
        DSTAT: Optional[Time] = None,
    ) -> None:
        for downstream_port, is_physical in self.downstream_ports:
            if not is_physical:
                downstream_port.set_value(
                    Message(
                        data=value,
                        timestamp=timestamp,
                        DSTAT=DSTAT,
                        from_port=self.name,
                        to_port=downstream_port.name,
                    )
                )
            else:
                downstream_port.set_value(
                    Message(
                        data=value,
                        timestamp=None,
                        DSTAT=None,
                        from_port=self.name,
                        to_port=downstream_port.name,
                    )
                )

    def connect(self, other: InputPortConnector[T], physical: bool = False) -> None:
        if not isinstance(other, InputPortConnector):
            raise TypeError("Can only connect OutputPort to InputPort")
        if (other, True) in self.downstream_ports or (
            other,
            False,
        ) in self.downstream_ports:
            raise ValueError(f"Port {other.name} is already connected to {self.name}")
        self.downstream_ports.append((other, physical))
        other.upstream_ports.append(self)

    # >> shorthand for connect
    def __rshift__(self, other: InputPortConnector[T]) -> "OutputPortConnector[T]":
        self.connect(other)
        return self

    # >>= shorthand for connect
    def __irshift__(self, other: InputPortConnector[T]) -> "OutputPortConnector[T]":
        self.connect(other)
        return self

    # >>= shorthand for physical connection
    def __ifloordiv__(self, other: InputPortConnector[T]) -> "OutputPortConnector[T]":
        self.connect(other, physical=True)
        return self

    def __str__(self) -> str:
        return f"<OutputPort {self.owner.node_cls.__name__}.{self.name}>"
