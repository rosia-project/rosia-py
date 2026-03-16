from rosia.comms.Types import ClientType
from rosia.comms.transports import Transport, TransportBase
from rosia.comms.serializers import Serializer, SerializerBase
from rosia.coordinate.Port import (
    InputPortRuntimeObj,
    OutputPortRuntimeObj,
)
from rosia.frontend.Connection import InputPortConnector, OutputPortConnector
from rosia.coordinate.messages.base import Message
from rosia.frontend.Port import InputPort, OutputPort
from rosia.utils import clone_class_detached, empty_function
from rosia.frontend.Annotators import RosiaAnnotations, check_rosia_annotations
from typing import Any, Dict, Optional, Type, TypeVar, List
import traceback
import sys
from rosia.time import Time, forever
import rosia
from rosia.coordinate.messages.base import (
    MessageBase,
    ShutdownMessage,
    CoordinatorShutdownRequestMessage,
    NoMoreMessage,
)
from rosia.coordinate.Events import InputPortEvent, ShutdownEvent, EventQueue
from rosia.time import s
import inspect
from rosia.time.utils import get_physical_time
from rosia.config import ExecutionConfig
from rosia.logging import Logger
from rosia.config import RerunConfig
import rerun as rr

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

        self.logical_time: Time = Time(0)
        self.STAT: Time = forever
        self.shutdown_requested: bool = False

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
        self.logger = Logger(self.node_name)
        self.event_queue = EventQueue(self.logger)

    def init_remote(
        self, execution_config: ExecutionConfig, rerun_config: RerunConfig
    ) -> Dict[str, str]:
        self.execution_config = execution_config
        rosia.logger.set_target(self.logger)  # type: ignore # overwrite the global logger
        self.logger.set_level(execution_config.log_level)
        self.logger.set_trace(trace=execution_config.trace, rerun_config=rerun_config)
        self.transport = self.transport_cls(ClientType.RECEIVER, self.serializer_cls)
        for _, input_port in self.input_port_connectors.items():
            input_port.port_type = ClientType.RECEIVER
            input_port.active_upstream_count = len(input_port.upstream_ports)
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
                    output_port.set_ENT(output_port_to_sta[output_port.name])
            input_port.update_safe_to_advance_time()

    def update_STAT(self) -> None:
        min_safe_to_advance_time = forever
        for input_port in self.input_port_connectors.values():
            min_safe_to_advance_time = min(
                min_safe_to_advance_time, input_port.safe_to_advance_time
            )
        self.logger.debug(
            f"STAT updated: {self.node_name} {self.STAT} -> {min_safe_to_advance_time}"
        )
        self.STAT = min_safe_to_advance_time

    def drain_message_queue(self) -> None:
        while True:
            message: Optional[MessageBase[Any]] = self.transport.receive()
            if message is None:
                break

            if isinstance(message, ShutdownMessage):
                self.logger.debug(
                    f"Received shutdown message to shutdown at time {message.timestamp}"
                )
                if message.timestamp is None:
                    raise ValueError("Shutdown message timestamp is None")
                self.event_queue.push_shutdown_event(message.timestamp)
            elif isinstance(message, NoMoreMessage):
                if message.to_port not in self.input_port_connectors:
                    raise ValueError(
                        f"NoMoreMessage to_port {message.to_port} not found in node {self.node_name}"
                    )
                input_port = self.input_port_connectors[message.to_port]
                input_port.active_upstream_count -= 1
                # Set upstream port ENT to forever so STAT can advance
                from_output_port = input_port.get_upstream_port_by_name(
                    message.from_port
                )
                from_output_port.safe_to_advance_time = forever
                input_port.update_safe_to_advance_time()
                self.logger.debug(
                    f"Received NoMoreMessage from {message.from_port}, "
                    f"active_upstream_count={input_port.active_upstream_count}"
                )
            elif isinstance(message, Message):
                if message.to_port is None:
                    raise ValueError(f"Message missing to_port field: {message}")
                if message.to_port not in self.input_port_connectors:
                    raise ValueError(
                        f"Message to_port {message.to_port} not found in node {self.node_name}"
                    )
                input_port = self.input_port_connectors[message.to_port]

                # Update ENT on upstream output port
                if message.ENT is not None:
                    from_output_port_name = message.from_port
                    if from_output_port_name is not None:
                        from_output_port = input_port.get_upstream_port_by_name(
                            from_output_port_name
                        )
                        from_output_port.safe_to_advance_time = max(
                            from_output_port.safe_to_advance_time,
                            message.ENT,
                        )
                        input_port.update_safe_to_advance_time()

                # Insert into event queue
                if message.timestamp is not None:
                    self.event_queue.push_input_port_event(
                        message.timestamp, input_port, message.data
                    )
            else:
                raise ValueError(
                    f"Unexpected message type: [{type(message)}] {message}"
                )

    def advance_logical_time(self, to_time: Time) -> None:
        while self.event_queue and self.event_queue.peek_time() < to_time:
            event = self.event_queue.pop()
            self.logical_time = event.timestamp

            if isinstance(event, ShutdownEvent):
                self.shutdown_requested = True
                return

            if isinstance(event, InputPortEvent):
                # Set port values
                for port, payload in event.input_port_values.items():
                    port.set_value_from_event(payload)

                # Collect and trigger reactions
                trigger_functions = set()
                affected_output_ports: List[OutputPortConnector[Any]] = []
                for port in event.input_port_values:
                    trigger_functions.update(port.trigger_functions)
                    affected_output_ports.extend(port.affected_output_ports)

                for trigger_function in trigger_functions:
                    try:
                        self.logger.set_logical_time(self.logical_time)
                        self.logger.set_physical_time(
                            get_physical_time() - self.start_logical_time
                        )
                        self.logger.debug(f"{trigger_function.__name__}()")
                        for input_port in self.input_port_connectors.values():
                            if trigger_function in input_port.trigger_functions:
                                if hasattr(input_port.value, "to_rerun"):
                                    self.logger.rerun(
                                        input_port.value.to_rerun(),  # type: ignore
                                        rerun_subpath=f"{input_port.name}",
                                    )
                                else:
                                    self.logger.rerun(
                                        rr.TextLog(
                                            text=str(input_port.value), level="DEBUG"
                                        ),
                                        rerun_subpath=f"{input_port.name}",
                                    )
                        trigger_function(self.node_instance)
                    except Exception as e:
                        print(f"Exception in trigger function {trigger_function}: {e}")
                        traceback.print_exc()
                        self.request_shutdown(0 * s, status_code=1)
                        return

                # Recompute STAT after processing each event
                self.update_STAT()

                # Send ENT updates to affected output ports
                ent = min(self.STAT, self.event_queue.peek_data_time())
                for output_port in affected_output_ports:
                    output_port._set_value(None, None, ent)

    def advance_time(self, delta: Time) -> None:
        target_time = self.logical_time + delta
        while self.logical_time < target_time:
            if self.shutdown_requested:
                return
            self.drain_message_queue()
            self.update_STAT()
            if self.STAT > self.logical_time:
                advance_to = min(target_time, self.STAT)
                self.advance_logical_time(to_time=advance_to)
                if self.shutdown_requested:
                    return
                if not self.event_queue or self.event_queue.peek_time() >= advance_to:
                    self.logical_time = advance_to
            else:
                self.transport.wait_for_message()

    def _all_upstream_done(self) -> bool:
        if not self.input_port_connectors:
            return False  # Source nodes handled separately
        for input_port in self.input_port_connectors.values():
            if input_port.active_upstream_count > 0:
                return False
        return True

    def send_no_more_messages(self) -> None:
        for output_port in self.output_port_connectors.values():
            for downstream_port in output_port.downstream_ports:
                if downstream_port.transport is not None:
                    downstream_port.transport.send(
                        NoMoreMessage(
                            timestamp=None,
                            from_port=output_port.name,
                            to_port=downstream_port.name,
                        )
                    )

    def event_loop(self) -> None:
        while not self.shutdown_requested:
            self.drain_message_queue()
            self.update_STAT()
            self.logger.debug("Event loop processing messages")

            if self.event_queue and self.event_queue.peek_time() < self.STAT:
                self.advance_logical_time(to_time=self.STAT)
            elif not self.event_queue and self._all_upstream_done():
                self.send_no_more_messages()
                self.request_shutdown(0 * s, status_code=0)
                self.shutdown_requested = True
            else:
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

            # Source nodes: if no input ports and no pending events, send NoMoreMessage
            if not self.input_port_connectors and not self.event_queue:
                self.send_no_more_messages()
                self.shutdown_requested = True

            if not self.shutdown_requested:
                self.event_loop()
            # Shutdown after loop exits
            if hasattr(self.node_instance, "shutdown"):
                self.node_instance.shutdown()
            sys.exit(0)
        except KeyboardInterrupt:
            print("KeyboardInterrupt received, shutting down")
            if hasattr(self.node_instance, "shutdown"):
                self.node_instance.shutdown()
            sys.exit(0)
        except Exception as e:
            print(f"Exception in {self.node_name}: {e}")
            traceback.print_exc()
            self.request_shutdown(0 * s, status_code=1)
            sys.exit(1)

    def request_shutdown(self, delay: Time = Time(0), status_code: int = 0) -> None:
        shutdown_timestamp = self.logical_time + delay
        self.logger.debug(
            f"Requesting shutdown in {delay} at time {shutdown_timestamp}"
        )
        self.coordinator_receiver_transport.send(
            CoordinatorShutdownRequestMessage(
                timestamp=shutdown_timestamp, status_code=status_code
            )
        )
