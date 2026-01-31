from typing import Any, Generic, Optional, TypeVar, TYPE_CHECKING

from rosia.time import Time

if TYPE_CHECKING:
    from rosia.coordinate.Coordinator import NodeRuntime
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

    # When the user sets the port, the value is passed to the coordinator to be sent to the downstream ports
    def __set__(self, value: T) -> None:
        raise TypeError("OutputPortRuntimeObj is immutable")

    def set_next_timestamp(self, first_timestamp: Time) -> None:
        self.output_port_connector.set_next_timestamp(first_timestamp)

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
            timestamp = self.node_runtime.current_time
            next_timestamp = self.node_runtime.next_time
        self.output_port_connector._set_value(value, timestamp, next_timestamp)
