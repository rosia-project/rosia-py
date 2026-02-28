from rosia.comms.Types import ClientType
from rosia.comms.transports import Transport, TransportBase
from rosia.comms.serializers import Serializer, SerializerBase
from rosia.coordinate.Port import (
    InputPortRuntimeObj,
    OutputPortRuntimeObj,
)
from rosia.frontend.Connection import InputPortConnector, OutputPortConnector
from rosia.coordinate.messages.base import Message, MessageBase
from rosia.frontend.Port import InputPort, OutputPort
from rosia.utils import clone_class_detached, empty_function
from rosia.frontend.Annotators import RosiaAnnotations, check_rosia_annotations
from typing import Any, Dict, Optional, Type, TypeVar, List
import traceback
import sys
from rosia.time import Time, forever
import rosia
from rosia.coordinate.messages.base import (
    ShutdownMessage,
    CoordinatorShutdownRequestMessage,
)
from rosia.time import s
import inspect
from rosia.time.utils import get_physical_time
from rosia.config import ExecutionConfig

T = TypeVar("T")


class NodeRuntime:
    def __init__(
        self,
        rosia_annotations: RosiaAnnotations,
        node_name: str,
        coordinator_receiver_endpoint: str,
        transport_cls: Type[TransportBase] = Transport,
        serializer_cls: Type[SerializerBase] = Serializer,
    ) -> None:
        check_rosia_annotations(rosia_annotations)
        node_cls = rosia_annotations["original_cls"]
        self.coordinator_receiver_endpoint = coordinator_receiver_endpoint

        self.node_cls = clone_class_detached(
            node_cls, f"{node_cls.__name__}NodeRuntime"
        )
        self.node_original_init = rosia_annotations["original_init"]
        self.node_init_args = rosia_annotations["init_args"]
        self.node_name = node_name
        self.start_logical_time: Time = Time(0)
        self.serializer_cls: Type[SerializerBase] = serializer_cls
        self.transport_cls: Type[TransportBase] = transport_cls

        self.transport: TransportBase
        self.input_port_connectors: Dict[str, InputPortConnector[Any]] = {}
        self.output_port_connectors: Dict[str, OutputPortConnector[Any]] = {}

        self.current_time: Time = Time(0)
        self.next_time: Time = Time(0)
        self.safe_to_advance_time: Time = Time(
            0
        )  # Safe to advance time to any current_time < safe_to_advance_time
        self.message_queue: Dict[Time, List[MessageBase[Any]]] = {}

        for name, value in self.node_cls.__dict__.items():
            if isinstance(value, OutputPort):
                output_port = OutputPortConnector(
                    owner=self,
                    name=value.name,
                )
                output_port_runtime_object = OutputPortRuntimeObj(self, output_port)
                port_name = f"{self.node_name}.{name}"
                self.output_port_connectors[port_name] = output_port

                self.__setattr__(name, output_port)
                setattr(self.node_cls, name, output_port_runtime_object)

        for name, value in self.node_cls.__dict__.items():
            if isinstance(value, InputPort):
                trigger_functions = value.trigger_functions
                input_port_runtime_object = InputPortRuntimeObj(self)
                affected_output_port_names = list(set(value.affected_output_port_names))
                affected_output_ports = []
                for port_name in affected_output_port_names:
                    output_port_name = f"{self.node_name}.{port_name}"
                    if output_port_name in self.output_port_connectors:
                        affected_output_ports.append(
                            self.output_port_connectors[output_port_name]
                        )

                input_port = InputPortConnector(
                    owner=self,
                    name=value.name,
                    trigger_functions=trigger_functions,
                    input_port_runtime_object=input_port_runtime_object,
                    affected_output_ports=affected_output_ports,
                )
                port_name = f"{self.node_name}.{name}"
                self.input_port_connectors[port_name] = input_port

                self.__setattr__(name, input_port)
                setattr(self.node_cls, name, input_port_runtime_object)

        setattr(
            self.node_cls, "__init__", empty_function
        )  # Replace the record_init_args function with empty_function
        self.node_instance = self.node_cls()

    def init_remote(self, execution_config: ExecutionConfig) -> Dict[str, str]:
        self.execution_config = execution_config
        self.transport = self.transport_cls(ClientType.RECEIVER, self.serializer_cls)
        for _, input_port in self.input_port_connectors.items():
            input_port.port_type = ClientType.RECEIVER
        return {self.node_name: self.transport.endpoint}

    def init_output_transports(self, node_endpoints: Dict[str, str]) -> None:
        downstream_nodes: Dict[str, List[InputPortConnector[Any]]] = {}
        for name, output_port in self.output_port_connectors.items():
            for downstream_port in output_port.downstream_ports:
                downstream_node_name = downstream_port.owner.node_name
                if downstream_node_name not in downstream_nodes:
                    downstream_nodes[downstream_node_name] = []
                downstream_nodes[downstream_node_name].append(downstream_port)

        for node_name, ports_list in downstream_nodes.items():
            if node_name not in node_endpoints:
                raise ValueError(f"Node endpoint for {node_name} not found")
            node_endpoint = node_endpoints[node_name]
            sender_transport = self.transport_cls(
                ClientType.SENDER,
                self.serializer_cls,
                node_endpoint,
            )
            for downstream_port in ports_list:
                downstream_port.port_type = ClientType.SENDER
                downstream_port.transport = sender_transport

    def init_node_instance(self) -> None:
        setattr(self.node_instance, "__init__", self.node_original_init)
        if self.node_init_args is None:
            raise RuntimeError(
                f"Node init args are not set for node {self.node_name}. This is a bug within the Rosia framework."
            )
        rosia.node_runtime_instance = self
        self.coordinator_receiver_transport = Transport(
            ClientType.SENDER, Serializer, self.coordinator_receiver_endpoint
        )
        self.node_instance.__init__(
            self.node_instance, *self.node_init_args.args, **self.node_init_args.kwargs
        )

    def get_output_port_ENT(self) -> Dict[str, Time]:
        output_port_safe_to_advance_time = {}
        for output_port in self.output_port_connectors.values():
            output_port_safe_to_advance_time[output_port.name] = (
                output_port.safe_to_advance_time
            )
        return output_port_safe_to_advance_time

    def set_output_port_ENT(self, output_port_to_sta: Dict[str, Time]) -> None:
        for input_port in self.input_port_connectors.values():
            for output_port in input_port.upstream_ports:
                if output_port.name in output_port_to_sta.keys():
                    output_port.set_next_timestamp(output_port_to_sta[output_port.name])
            input_port.update_safe_to_advance_time()

    def update_safe_to_advance_time(self) -> None:
        min_safe_to_advance_time = forever
        for input_port in self.input_port_connectors.values():
            min_safe_to_advance_time = min(
                min_safe_to_advance_time, input_port.safe_to_advance_time
            )
        self.safe_to_advance_time = min_safe_to_advance_time

    def receive_messages(self) -> None:
        while True:  # Empty the message queue
            message: Optional[Message[Any]] = self.transport.receive()
            if message is None:
                break

            if isinstance(message, ShutdownMessage):
                shutdown_timestamp = message.timestamp
                self.message_queue[shutdown_timestamp] = [message]  # type: ignore
                continue
            elif isinstance(message, Message):
                # Demux message to the correct input port based on to_port
                if message.to_port is None:
                    raise ValueError(f"Message missing to_port field: {message}")
                if message.to_port not in self.input_port_connectors:
                    raise ValueError(
                        f"Message to_port {message.to_port} not found in node {self.node_name}"
                    )
                input_port = self.input_port_connectors[message.to_port]
                if message.timestamp is None and message.next_timestamp is None:
                    # This is untimestamped message, we process it immediately
                    input_port.set_value(message)
                    input_port._trigger()
                if message.next_timestamp is not None:
                    from_output_port_name = message.from_port
                    if from_output_port_name is not None:
                        # Coordinator.set_value will have from_port set to None
                        from_output_port = input_port.get_upstream_port_by_name(
                            from_output_port_name
                        )
                        from_output_port.safe_to_advance_time = max(
                            from_output_port.safe_to_advance_time,
                            message.next_timestamp,
                        )
                        input_port.update_safe_to_advance_time()
                if message.timestamp is not None:
                    if message.timestamp not in self.message_queue:
                        self.message_queue[message.timestamp] = [message]
                    else:
                        self.message_queue[message.timestamp].append(message)
                else:
                    # it is simply a coordination message to update the STA
                    pass
            else:
                raise ValueError(
                    f"Unexpected message type: [{type(message)}] {message}"
                )

    def log_trace(self) -> None:
        if self.execution_config.trace:
            physical_time_val = (
                get_physical_time().to_unix_time()
                - self.start_logical_time.to_unix_time()
            )
            lag = physical_time_val - self.current_time.to_unix_time()
            rosia.rerun_manager.trace(
                self.node_name,
                self.current_time,
                Time.from_unix_time(physical_time_val),
                f"Lag: {lag}",
            )

    def advance_time(self, advance_until: Time = forever) -> None:
        ready_timestamps = [
            timestamp
            for timestamp in self.message_queue.keys()
            if timestamp < self.safe_to_advance_time and timestamp <= advance_until
        ]
        ready_timestamps.sort()
        for i in range(len(ready_timestamps)):
            timestamp = ready_timestamps[i]
            self.current_time = timestamp
            self.next_time = (
                ready_timestamps[i + 1]
                if i < len(ready_timestamps) - 1
                else self.safe_to_advance_time
            )
            messages = self.message_queue[timestamp]
            trigger_functions = set()
            # Sort messages by from_port to avoid nondeterministic behavior
            sorted_messages = sorted(
                messages,
                key=lambda x: x.timestamp if x.timestamp is not None else forever,
            )
            affected_output_ports: List[OutputPortConnector[Any]] = []
            for msg in sorted_messages:
                if isinstance(msg, ShutdownMessage):
                    if hasattr(self.node_instance, "shutdown"):
                        self.node_instance.shutdown()
                        sys.exit(0)
                    else:
                        sys.exit(0)
            for msg in sorted_messages:
                if not isinstance(msg, Message):
                    raise ValueError(f"Unexpected message type: [{type(msg)}] {msg}")
                input_port = self.input_port_connectors[msg.to_port]
                input_port.set_value(msg)
                affected_output_ports.extend(input_port.affected_output_ports)
                trigger_functions.update(input_port.trigger_functions)
            del self.message_queue[timestamp]

            for trigger_function in trigger_functions:
                try:
                    self.log_trace()
                    trigger_function(self.node_instance)
                except Exception as e:
                    print(f"Exception in trigger function {trigger_function}: {e}")
                    traceback.print_exc()
                    self.request_shutdown(0 * s, status_code=1)
                    sys.exit(1)
            for output_port in affected_output_ports:
                # The output may not be set by the user code, but we need to update the downstream STA
                output_port._set_value(None, None, self.next_time)

    def event_loop(self) -> None:
        while True:
            self.receive_messages()
            self.update_safe_to_advance_time()
            self.advance_time()
            # Blocking wait for messages on the single node transport
            self.transport.wait_for_message()

    def execute(self, start_logical_time: Time) -> None:
        self.start_logical_time = start_logical_time
        try:
            if hasattr(self.node_instance, "start"):
                if not inspect.signature(self.node_instance.start).parameters:
                    self.node_instance.start()
                elif (
                    "start_logical_time"
                    in inspect.signature(self.node_instance.start).parameters
                ):
                    self.node_instance.start(start_logical_time=start_logical_time)
                else:
                    raise ValueError(
                        f"Node {self.node_name} has a start method with an unexpected signature: {inspect.signature(self.node_instance.start)}"
                    )
            self.event_loop()
        except KeyboardInterrupt:
            print("KeyboardInterrupt received, shutting down")
            sys.exit(0)
        except Exception as e:
            print(f"Exception in {self.node_name}: {e}")
            traceback.print_exc()
            sys.exit(1)

    def request_shutdown(self, delay: Time = Time(0), status_code: int = 0) -> None:
        self.coordinator_receiver_transport.send(
            CoordinatorShutdownRequestMessage(timestamp=delay, status_code=status_code)
        )
