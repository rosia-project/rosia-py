from typing import Any, Dict, Generic, TypeVar, TYPE_CHECKING

from rosia.time import Time

if TYPE_CHECKING:
    from rosia.coordinate.Node import NodeRuntime
    from rosia.frontend.Connection import OutputPortConnector

T = TypeVar("T")


# This is called by user code to get the value of the port
class InputPortRuntimeObj(Generic[T]):
    def __init__(self, node_runtime: "NodeRuntime", initial_value: T = None) -> None:
        self.node_runtime = node_runtime
        self.value: T = initial_value

    # This is meant to be called by the coordinator to set the value of the user object
    def _set_value(self, value: T) -> None:
        self.value = value

    # The user should not be able to set the value of the port
    def __set__(self, value: T) -> None:
        raise TypeError("InputPortRuntimeObj is immutable")

    def __get__(self, instance: Any, owner: type) -> T:
        return self.value


# This is called by user code to set the value of the port
class OutputPortRuntimeObj(Generic[T]):
    def __init__(
        self,
        node_runtime: "NodeRuntime",
        output_port_connector: "OutputPortConnector[T]",
    ) -> None:
        self.node_runtime = node_runtime
        self.output_port_connector = output_port_connector
        self.value: T | None = None

    # When the user sets the port, the value is passed to the coordinator to be sent to the downstream ports
    def __set__(self, value: T) -> None:
        raise TypeError("OutputPortRuntimeObj is immutable")

    def __call__(
        self,
        value: T,
    ) -> None:
        if self.value is not None:
            raise ValueError(
                f"Output port {self.output_port_connector.name} written twice at same logical time {self.node_runtime.logical_time}"
            )
        self.value = value

    def _send(self, timestamp: Time, ENTs: Dict[str, Time]) -> None:
        self.output_port_connector.send(self.value, timestamp, ENTs)
        self.value = None
