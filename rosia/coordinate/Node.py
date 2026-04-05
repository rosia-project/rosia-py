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
    NodeRequestShutdownMessage,
    NodeForceShutdownRequest,
    ApplicationRequestShutdownMessage,
    ApplicationShutdownResponseMessage,
    ExitMessage,
    NoMoreMessage,
)
from rosia.coordinate.Events import (
    InputPortEvent,
    ShutdownEvent,
    EventQueue,
)
from rosia.coordinate.Reaction import Reaction, ReactionQueue
from rosia.time import s, never
import inspect
from rosia.config import ExecutionConfig
from rosia.logging import Logger
from rosia.config import RerunConfig
import signal

T = TypeVar("T")


class NodeRuntime:
    def __init__(
        self,
        rosia_annotations: RosiaAnnotations,
        node_name: str,
        coordinator_transport_endpoint: str,
        transport_cls: Type[TransportBase] = Transport,
        serializer_cls: Type[SerializerBase] = Serializer,
    ) -> None:
        check_rosia_annotations(rosia_annotations)
        node_cls = rosia_annotations["original_cls"]
        self.coordinator_transport_endpoint = coordinator_transport_endpoint

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

        self.logical_time: Time = never
        self.STAT: Time = forever
        self.shutdown_time_barrier: Time = forever

        self.event_queue: EventQueue = EventQueue()
        self.reaction_queue: ReactionQueue = ReactionQueue()

        self.init_ports()

        setattr(
            self.node_cls, "__init__", empty_function
        )  # Replace the record_init_args function with empty_function
        self.node_instance = self.node_cls()
        self.logger = Logger(self.node_name)

    def init_ports(self) -> None:
        self.input_port_connectors: Dict[str, InputPortConnector[Any]] = {}
        self.output_port_connectors: Dict[str, OutputPortConnector[Any]] = {}
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

    def init_remote(
        self, execution_config: ExecutionConfig, rerun_config: Optional[RerunConfig]
    ) -> Dict[str, str]:
        self.execution_config = execution_config
        rosia.logger.set_target(self.logger)  # type: ignore # overwrite the global logger
        self.logger.set_level(execution_config.log_level)
        self.logger.set_trace(trace=execution_config.trace)
        if rerun_config is not None:
            self.logger.set_rerun_config(rerun_config)
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
        self.coordinator_transport = Transport(
            ClientType.SENDER, Serializer, self.coordinator_transport_endpoint
        )
        self.node_instance.__init__(
            self.node_instance, *self.node_init_args.args, **self.node_init_args.kwargs
        )

    def get_output_port_DSTAT(self) -> Dict[str, Time]:
        output_port_safe_to_advance_to = {}
        for output_port in self.output_port_connectors.values():
            output_port_safe_to_advance_to[output_port.name] = (
                output_port.safe_to_advance_to
            )
        return output_port_safe_to_advance_to

    def set_output_port_DSTAT(self, output_port_to_sta: Dict[str, Time]) -> None:
        for input_port in self.input_port_connectors.values():
            for output_port in input_port.upstream_ports:
                if output_port.name in output_port_to_sta.keys():
                    output_port.set_DSTAT(output_port_to_sta[output_port.name])
            input_port.update_safe_to_advance_to()

    def event_loop(self) -> None:
        self.logger.debug(f"Starting event loop for node {self.node_name}")
        while True:
            try:
                self.drain_message_queue()
            except Exception as e:
                self.logger.error(f"Error in event loop for node {self.node_name}: {e}")
                traceback.print_exc()
                self.request_shutdown(0 * s, status_code=1)
            self.update_STAT()

            has_work = (
                self.event_queue.peek_time() is not None
                and self.event_queue.peek_time() < self.STAT
            ) or (
                self.reaction_queue.peek_time() is not None
                and self.reaction_queue.peek_time() < self.STAT
            )

            if has_work:
                self.advance_to_STAT()
            elif self.check_natural_shutdown():
                return
            else:
                self.transport.wait_for_message()

    def advance_to_STAT(self) -> None:
        while True:
            self.drain_message_queue()
            self.update_STAT()

            next_event_timestamp = self.event_queue.peek_time()
            next_reaction_timestamp = self.reaction_queue.peek_time()

            advance_to_time: Time = self.logical_time

            if next_event_timestamp is None and next_reaction_timestamp is None:
                break
            elif next_event_timestamp is None:
                advance_to_time = next_reaction_timestamp  # type: ignore
            elif next_reaction_timestamp is None:
                advance_to_time = next_event_timestamp  # type: ignore
            else:
                advance_to_time = min(next_event_timestamp, next_reaction_timestamp)
            if advance_to_time >= self.STAT:
                return  # Wait until STAT increases

            if advance_to_time < self.logical_time:
                self.logger.error(
                    f"Logical time decrease: {self.logical_time} -> {advance_to_time}"
                )

            if self.logger._trace and advance_to_time != self.logical_time:
                self.logger.debug(
                    f"Logical time: {self.logical_time} -> {advance_to_time}"
                )
            self.logical_time = advance_to_time

            self.execute_reactions(advance_to_time)

            while (
                self.event_queue.peek_time() is not None
                and self.event_queue.peek_time() == advance_to_time
            ):
                event = self.event_queue.pop()
                assert event is not None, "Event is None"
                if isinstance(event, InputPortEvent):
                    for input_port, value in event.input_port_values.items():
                        input_port.set_value_from_event(value)
                    trigger_reactions = []
                    for input_port in event.input_port_values.keys():
                        for func in input_port.trigger_functions:
                            if func not in trigger_reactions:
                                trigger_reactions.append(func)
                    for func in trigger_reactions:
                        reaction = Reaction(func, advance_to_time, self.node_instance)
                        self.reaction_queue.enqueue(reaction)
                elif isinstance(event, ShutdownEvent):
                    reaction = Reaction(self.shutdown, advance_to_time)
                    self.reaction_queue.enqueue(reaction, is_shutdown=True)
                else:
                    raise ValueError(f"Unexpected event type: {type(event)}")

            self.execute_reactions(advance_to_time)

    def execute_reactions(self, timestamp: Time) -> None:
        while (
            self.reaction_queue.peek_time() is not None
            and self.reaction_queue.peek_time() == timestamp
        ):
            reaction, is_shutdown = self.reaction_queue.dequeue()
            if is_shutdown:
                self.shutdown()
                break
            assert reaction is not None, "Reaction is None"
            next_reaction = reaction.execute()
            if next_reaction is not None:
                self.reaction_queue.enqueue(next_reaction)

    def drain_message_queue(self) -> None:
        while True:
            message: Optional[MessageBase[Any]] = self.transport.receive()
            if message is None:
                break

            if isinstance(message, ApplicationRequestShutdownMessage):
                if message.timestamp is None:
                    raise ValueError(
                        "ApplicationRequestShutdownMessage timestamp is None"
                    )
                requested_time = message.timestamp
                if self.logical_time > requested_time:
                    response_time = self.logical_time
                else:
                    response_time = requested_time
                self.shutdown_time_barrier = response_time + Time(1)
                self.coordinator_transport.send(
                    ApplicationShutdownResponseMessage(timestamp=response_time)
                )
            elif isinstance(message, ShutdownMessage):
                if message.timestamp is None:
                    raise ValueError("Shutdown message timestamp is None")
                self.shutdown_time_barrier = message.timestamp + Time(1)
                self.update_STAT()
                if message.timestamp < self.logical_time:
                    if message.timestamp != never:
                        self.logger.warning(
                            f"Shutdown message timestamp {message.timestamp} is in the past. Shutting down immediately."
                        )
                    self.shutdown()
                    return
                self.event_queue.push_shutdown_event(message.timestamp)
            elif isinstance(message, NoMoreMessage):
                if message.to_port not in self.input_port_connectors:
                    raise ValueError(
                        f"NoMoreMessage to_port {message.to_port} not found in node {self.node_name}"
                    )
                input_port = self.input_port_connectors[message.to_port]
                input_port.active_upstream_count -= 1
                from_output_port = input_port.get_upstream_port_by_name(
                    message.from_port
                )
                from_output_port.safe_to_advance_to = forever
                input_port.update_safe_to_advance_to()
            elif isinstance(message, Message):
                assert message.to_port in self.input_port_connectors, (
                    f"Message to_port {message.to_port} not found in node {self.node_name}"
                )
                input_port = self.input_port_connectors[message.to_port]

                if message.DSTAT is not None:
                    from_output_port_name = message.from_port
                    assert from_output_port_name is not None, (
                        f"Message from_port {message.from_port} is None"
                    )
                    from_output_port = input_port.get_upstream_port_by_name(
                        from_output_port_name
                    )
                    from_output_port.safe_to_advance_to = max(
                        from_output_port.safe_to_advance_to,
                        message.DSTAT,
                    )
                    input_port.update_safe_to_advance_to()
                self.update_STAT()

                assert message.timestamp is not None, "Message timestamp is None"
                self.event_queue.push_input_port_event(
                    message.timestamp, input_port, message.data
                )
            else:
                raise ValueError(
                    f"Unexpected message type: [{type(message)}] {message}"
                )

    def update_STAT(self) -> None:
        min_safe_to_advance_to = forever
        for input_port in self.input_port_connectors.values():
            min_safe_to_advance_to = min(
                min_safe_to_advance_to, input_port.safe_to_advance_to
            )
        if min_safe_to_advance_to < self.STAT and self.STAT != forever:
            self.logger.warning(
                f"STAT decrease: {self.STAT} -> {min_safe_to_advance_to}"
            )
        min_safe_to_advance_to = min(min_safe_to_advance_to, self.shutdown_time_barrier)
        if self.logger._trace and self.STAT != min_safe_to_advance_to:
            self.logger.debug(f"STAT: {self.STAT} -> {min_safe_to_advance_to}")
        self.STAT = min_safe_to_advance_to

    def execute(self, start_logical_time: Time) -> None:
        signal.signal(
            signal.SIGINT, signal.SIG_IGN
        )  # Ignore SIGINT in subprocesses. KeyboardInterrupt will be handled by the main process.
        self.start_logical_time = start_logical_time
        try:
            self.startup(start_logical_time)

            if self.check_natural_shutdown():
                self.coordinator_transport.send(
                    ExitMessage(timestamp=None, node_name=self.node_name)
                )
                self.shutdown()

            self.event_loop()

            self.coordinator_transport.send(
                ExitMessage(timestamp=None, node_name=self.node_name)
            )
            self.shutdown(status_code=0)
        except Exception as e:
            print(f"Exception in {self.node_name}: {e}")
            traceback.print_exc()
            self.coordinator_transport.send(
                NodeForceShutdownRequest(timestamp=self.logical_time, status_code=1)
            )
            self.close_transports()
            sys.exit(1)

    def request_shutdown(self, delay: Time = Time(0), status_code: int = 0) -> None:
        shutdown_timestamp = self.logical_time + delay
        self.logger.debug(
            f"Requesting shutdown in {delay} at time {shutdown_timestamp}"
        )
        self.coordinator_transport.send(
            NodeRequestShutdownMessage(
                timestamp=shutdown_timestamp, status_code=status_code
            )
        )

    def startup(self, start_logical_time: Time) -> None:
        if hasattr(self.node_instance, "start"):
            if not inspect.signature(self.node_instance.start).parameters:
                start_reaction = Reaction(self.node_instance.start, Time(0))
                self.reaction_queue.enqueue(start_reaction)
            elif (
                "start_logical_time"
                in inspect.signature(self.node_instance.start).parameters
            ):
                start_reaction = Reaction(
                    self.node_instance.start,
                    Time(0),
                    start_logical_time=start_logical_time,
                )
                self.reaction_queue.enqueue(start_reaction)
            else:
                raise ValueError(
                    f"Node {self.node_name} has a start method with an unexpected signature: {inspect.signature(self.node_instance.start)}"
                )

    def check_natural_shutdown(self) -> bool:
        def all_done() -> bool:
            for input_port in self.input_port_connectors.values():
                if input_port.active_upstream_count > 0:
                    return False
            if not self.input_port_connectors:
                return True
            return True

        if (
            not self.event_queue
            and not self.reaction_queue.has_pending()
            and all_done()
        ):
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
            return True
        return False

    def close_transports(self) -> None:
        if hasattr(self, "transport"):
            self.transport.close()
        if hasattr(self, "coordinator_transport"):
            self.coordinator_transport.close()
        closed: set[int] = set()
        for output_port in self.output_port_connectors.values():
            for downstream_port in output_port.downstream_ports:
                if (
                    downstream_port.transport is not None
                    and id(downstream_port.transport) not in closed
                ):
                    downstream_port.transport.close()
                    closed.add(id(downstream_port.transport))

    def shutdown(self, status_code: int = 0) -> None:
        if hasattr(self.node_instance, "shutdown"):
            self.node_instance.shutdown()
        self.close_transports()
        self.logger.shutdown()
        sys.exit(status_code)
