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
from dataclasses import dataclass, field
import inspect

from rosia.config import ExecutionConfig
from rosia.logging import Logger
from rosia.config import RerunConfig
import signal
from rosia.time.utils import get_physical_time


@dataclass
class UpstreamInfo:
    """Per-upstream-node tracking used in STAT calculation and ENT propagation.

    `min_delay` is the smallest cumulative logical-time delay along any path
    from this upstream node to self (computed once at startup).

    `ent` is the latest known Earliest Next Timestamp of this upstream — set
    authoritatively by direct messages from the upstream itself, max-merged
    from hearsay forwarded by other nodes.

    `active_port_count` counts direct connections from this upstream to self
    that have not yet sent `NoMoreMessage`. It is 0 for upstreams that are not
    a direct upstream (transitive-only) — for those, `is_active` is managed by
    ENT propagation (the upstream's own `forever` ENT once it is done).

    `is_active` becomes False once a direct upstream has sent `NoMoreMessage`
    on every one of its connections to self. STAT computation ignores inactive
    direct upstreams. Transitive-only upstreams stay `is_active=True`; their
    contribution drops out automatically when their ENT reaches `forever`.
    """

    min_delay: Time
    ent: Time = field(default_factory=lambda: never)
    active_port_count: int = 0
    is_active: bool = True


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

        self.node_cls = clone_class_detached(node_cls, f"{node_cls.__name__}NodeRuntime")
        self.node_original_init = rosia_annotations["original_init"]
        self.node_init_args = rosia_annotations["init_args"]
        self.node_name = node_name

        self.start_logical_time: Time = Time(0)
        self.serializer_cls: Type[SerializerBase] = serializer_cls
        self.transport_cls: Type[TransportBase] = transport_cls

        self.transport: TransportBase

        self.logical_time: Time = never
        self.STAT: Time = never
        self.shutdown_time_barrier: Time = forever

        self.event_queue: EventQueue = EventQueue()
        self.reaction_queue: ReactionQueue = ReactionQueue()

        # All transitive upstream nodes (excluding self). Each entry holds the
        # min path delay from that upstream to self, the latest known ENT, and
        # NoMoreMessage bookkeeping. Populated by `init_topology` once the
        # coordinator has computed the global graph.
        self.upstream_nodes: Dict[str, UpstreamInfo] = {}

        self.init_ports()

        setattr(self.node_cls, "__init__", empty_function)  # Replace the record_init_args function with empty_function
        self.node_instance = self.node_cls()
        self.logger = Logger(self.node_name)

    def init_ports(self) -> None:
        self.input_port_connectors: Dict[str, InputPortConnector[Any]] = {}
        self.output_port_connectors: Dict[str, OutputPortConnector[Any]] = {}
        self.output_port_objects: Dict[str, OutputPortRuntimeObj[Any]] = {}
        for name, value in self.node_cls.__dict__.items():
            if isinstance(value, OutputPort):
                output_port = OutputPortConnector(
                    owner=self,
                    name=value.name,
                )
                output_port_runtime_object = OutputPortRuntimeObj(self, output_port)
                port_name = f"{self.node_name}.{name}"
                self.output_port_connectors[port_name] = output_port
                self.output_port_objects[port_name] = output_port_runtime_object

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
                        affected_output_ports.append(self.output_port_connectors[output_port_name])

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

    def init_remote(self, execution_config: ExecutionConfig, rerun_config: Optional[RerunConfig]) -> Dict[str, str]:
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

    def init_topology(self, upstream_nodes: Dict[str, UpstreamInfo]) -> None:
        """Install the upstream topology computed by the coordinator. The
        coordinator runs a single Bellman-Ford pass over the full graph and
        sends each node its own per-upstream view, so we don't BFS the world
        ourselves on every startup."""
        self.upstream_nodes = upstream_nodes

    def init_output_transports(self, node_endpoints: Dict[str, str]) -> None:
        downstream_nodes: Dict[str, List[InputPortConnector[Any]]] = {}
        for name, output_port in self.output_port_connectors.items():
            for downstream_port, is_physical, delay in output_port.downstream_ports:
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
        self.coordinator_transport = Transport(ClientType.SENDER, Serializer, self.coordinator_transport_endpoint)
        self.node_instance.__init__(self.node_instance, *self.node_init_args.args, **self.node_init_args.kwargs)

    def event_loop(self) -> None:
        self.logger.debug(f"Starting event loop for node {self.node_name}")
        self.logger.debug(f"Logical time: {self.logger.logical_time}")
        self.logger.debug(f"STAT: {self.STAT}")
        # Baseline reflects what we'd send right now: if startup didn't send,
        # we don't want the first iteration's eager check to broadcast a stale
        # "forever" before we've received anything meaningful from upstream.
        last_propagated_ENTs: Dict[str, Time] = self._build_outgoing_ENTs()
        while True:
            try:
                self.drain_message_queue()
            except Exception as e:
                self.logger.error(f"Error in event loop for node {self.node_name}: {e}")
                traceback.print_exc()
                self.request_shutdown(0 * s, status_code=1)
            self.update_STAT()

            # Eagerly propagate ENT updates after every drain so downstream
            # knows about pending events in our queue before we process them.
            # This is what enforces "all events at the same logical time are
            # processed at the same logical time" across the network.
            current_ENTs = self._build_outgoing_ENTs()
            if current_ENTs != last_propagated_ENTs:
                self.send_messages()
                last_propagated_ENTs = self._build_outgoing_ENTs()

            has_work = (self.event_queue.peek_time() is not None and self.event_queue.peek_time() < self.STAT) or (
                self.reaction_queue.peek_time() is not None and self.reaction_queue.peek_time() < self.STAT
            )

            if has_work:
                self.advance_to_STAT()
                last_propagated_ENTs = self._build_outgoing_ENTs()
            elif self.check_natural_shutdown():
                return
            else:
                self.transport.wait_for_message()

    def _compute_self_ENT(self) -> Time:
        # ENT = earliest unprocessed timestamp in this node's queues:
        #   - event queue peek (incoming messages not yet handled)
        #   - reaction queue peek (yield-scheduled work)
        # Bounded below by logical_time so we never report a timestamp in the
        # past. STAT is intentionally NOT a candidate: that would create a
        # recursive STAT-chases-its-own-ENT loop in cycles, and the
        # synchronization need it would otherwise cover (waiting for relay
        # chains) is already provided by transitive upstream ENT propagation.
        candidates: List[Time] = []
        next_event_timestamp = self.event_queue.peek_data_time()
        if next_event_timestamp is not None:
            candidates.append(next_event_timestamp)
        next_reaction_timestamp = self.reaction_queue.peek_time()
        if next_reaction_timestamp is not None:
            candidates.append(next_reaction_timestamp)
        if not candidates:
            return forever
        ent = min(candidates)
        if ent < self.logical_time:
            ent = self.logical_time
        return ent

    def _build_outgoing_ENTs(self) -> Dict[str, Time]:
        ents: Dict[str, Time] = {name: info.ent for name, info in self.upstream_nodes.items()}
        ents[self.node_name] = self._compute_self_ENT()
        return ents

    def send_messages(self) -> None:
        ents_to_send = self._build_outgoing_ENTs()
        for output_port in self.output_port_objects.values():
            output_port._send(self.logical_time, ents_to_send)

    def advance_to_STAT(self) -> None:
        # Track input-triggered reactions that have already been enqueued at
        # each logical timestamp. This dedup spans iterations of this loop, so
        # if more events at the same logical time arrive between drains the
        # reaction still fires at most once. ShutdownEvent reactions are
        # exempt (they're enqueued separately and must always run).
        enqueued_funcs_per_time: Dict[Time, set] = {}
        while True:
            self.drain_message_queue()
            self.update_STAT()

            next_reaction_timestamp = self.reaction_queue.peek_time()
            next_event_timestamp = self.event_queue.peek_time()

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
                self.logger.warning(f"Logical time decrease: {self.logical_time} -> {advance_to_time}")

            # Drop bookkeeping for timestamps strictly in the past.
            for t in list(enqueued_funcs_per_time.keys()):
                if t < advance_to_time:
                    del enqueued_funcs_per_time[t]

            if self.logger._trace and advance_to_time != self.logical_time:
                self.logger.debug(f"Logical time: {self.logical_time} -> {advance_to_time}")
            self.logical_time = advance_to_time
            self.logger.set_logical_time(advance_to_time)
            self.logger.set_physical_time(get_physical_time())

            already_enqueued = enqueued_funcs_per_time.setdefault(advance_to_time, set())
            # Collect trigger functions across all events at advance_to_time
            # before enqueuing reactions, so each function fires at most once
            # per logical timestamp even when its triggering inputs arrive in
            # multiple message batches.
            all_trigger_functions: List[Any] = []
            while self.event_queue.peek_time() is not None and self.event_queue.peek_time() == advance_to_time:
                event = self.event_queue.pop()
                assert event is not None, "Event is None"
                if isinstance(event, InputPortEvent):
                    for input_port, value in event.input_port_values.items():
                        input_port.set_value_from_event(value)
                    for input_port in event.input_port_values.keys():
                        for func in input_port.trigger_functions:
                            if func not in all_trigger_functions:
                                all_trigger_functions.append(func)
                elif isinstance(event, ShutdownEvent):
                    reaction = Reaction(self.shutdown, advance_to_time)
                    self.reaction_queue.enqueue(reaction, is_shutdown=True)
                else:
                    raise ValueError(f"Unexpected event type: {type(event)}")
            for func in all_trigger_functions:
                if func in already_enqueued:
                    continue
                reaction = Reaction(func, advance_to_time, self.node_instance)
                self.reaction_queue.enqueue(reaction)
                already_enqueued.add(func)

            self.execute_reactions(advance_to_time)
            self.update_STAT()
            self.send_messages()

    def execute_reactions(self, timestamp: Time) -> None:
        while self.reaction_queue.peek_time() is not None and self.reaction_queue.peek_time() == timestamp:
            reaction, is_shutdown = self.reaction_queue.dequeue()
            if is_shutdown:
                # Flush any pending output and ENT updates before exiting.
                self.send_messages()
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
                    raise ValueError("ApplicationRequestShutdownMessage timestamp is None")
                requested_time = message.timestamp
                if self.logical_time > requested_time:
                    response_time = self.logical_time
                else:
                    response_time = requested_time
                self.shutdown_time_barrier = response_time + Time(1)
                self.coordinator_transport.send(ApplicationShutdownResponseMessage(timestamp=response_time))
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
                    raise ValueError(f"NoMoreMessage to_port {message.to_port} not found in node {self.node_name}")
                input_port = self.input_port_connectors[message.to_port]
                input_port.active_upstream_count -= 1
                from_output_port = input_port.get_upstream_port_by_name(message.from_port)
                upstream_node = from_output_port.owner.node_name
                info = self.upstream_nodes.get(upstream_node)
                if info is not None and info.active_port_count > 0:
                    info.active_port_count -= 1
                    if info.active_port_count == 0:
                        # Direct upstream fully done. Mark inactive and pin its
                        # ENT to forever so it stops constraining our STAT, and
                        # so our downstream also sees it as done via the
                        # propagated dict.
                        info.is_active = False
                        info.ent = forever
            elif isinstance(message, Message):
                assert message.to_port in self.input_port_connectors, (
                    f"Message to_port {message.to_port} not found in node {self.node_name}"
                )
                input_port = self.input_port_connectors[message.to_port]

                if message.ENTs is not None:
                    sender_node = message.from_port.split(".", 1)[0] if message.from_port else None
                    for node_name, ent in message.ENTs.items():
                        if node_name == self.node_name:
                            continue
                        info = self.upstream_nodes.get(node_name)
                        if info is None:
                            # Not in our upstream chain — irrelevant to our STAT
                            # and never read by our downstream (their topology
                            # would have us as the only path to this node only
                            # if this node is also our upstream, which it isn't).
                            continue
                        if node_name == sender_node:
                            # Sender is authoritative for its own ENT — overwrite
                            # so non-monotonic decreases (queue refills) propagate.
                            info.ent = ent
                        elif ent > info.ent:
                            # Hearsay about other nodes — only accept newer (higher)
                            # values; the authoritative sender will eventually correct.
                            info.ent = ent
                self.update_STAT()

                if message.timestamp is None:  # physical message
                    if message.data is not None:
                        input_port.set_value_from_event(message.data)
                        for trigger_function in input_port.trigger_functions:
                            reaction = Reaction(trigger_function, self.logical_time, self.node_instance)
                            self.reaction_queue.enqueue(reaction)
                else:
                    if message.data is not None:
                        self.event_queue.push_input_port_event(message.timestamp, input_port, message.data)
            else:
                raise ValueError(f"Unexpected message type: [{type(message)}] {message}")

    def update_STAT(self) -> None:
        new_STAT: Time = forever
        for info in self.upstream_nodes.values():
            new_STAT = min(new_STAT, info.ent + info.min_delay)
        if new_STAT < self.STAT and self.STAT != forever and self.STAT != never:
            self.logger.warning(f"STAT decrease: {self.STAT} -> {new_STAT}")
        new_STAT = min(new_STAT, self.shutdown_time_barrier)
        if self.logger._trace and self.STAT != new_STAT:
            self.logger.debug(f"STAT: {self.STAT} -> {new_STAT}")
        self.STAT = new_STAT

    def execute(self, start_logical_time: Time) -> None:
        signal.signal(
            signal.SIGINT, signal.SIG_IGN
        )  # Ignore SIGINT in subprocesses. KeyboardInterrupt will be handled by the main process.
        self.start_logical_time = start_logical_time
        self.logger.set_logical_time(Time(0))
        self.logger.set_physical_time(get_physical_time())
        try:
            self.startup(start_logical_time)

            if self.check_natural_shutdown():
                self.coordinator_transport.send(ExitMessage(timestamp=None, node_name=self.node_name))
                self.shutdown()

            self.event_loop()

            self.coordinator_transport.send(ExitMessage(timestamp=None, node_name=self.node_name))
            self.shutdown(status_code=0)
        except Exception as e:
            print(f"Exception in {self.node_name}: {e}")
            traceback.print_exc()
            self.coordinator_transport.send(NodeForceShutdownRequest(timestamp=self.logical_time, status_code=1))
            self.close_transports()
            sys.exit(1)

    def request_shutdown(self, delay: Time = Time(0), status_code: int = 0) -> None:
        shutdown_timestamp = self.logical_time + delay
        self.logger.debug(f"Requesting shutdown in {delay} at time {shutdown_timestamp}")
        self.coordinator_transport.send(
            NodeRequestShutdownMessage(timestamp=shutdown_timestamp, status_code=status_code)
        )

    def startup(self, start_logical_time: Time) -> None:
        self.logical_time = Time(0)
        if hasattr(self.node_instance, "start"):
            if not inspect.signature(self.node_instance.start).parameters:
                start_reaction = Reaction(self.node_instance.start, Time(0))
            elif "start_logical_time" in inspect.signature(self.node_instance.start).parameters:
                start_reaction = Reaction(
                    self.node_instance.start,
                    Time(0),
                    start_logical_time=start_logical_time,
                )
            else:
                raise ValueError(
                    f"Node {self.node_name} has a start method with an unexpected signature: {inspect.signature(self.node_instance.start)}"
                )
            result = start_reaction.execute()
            if result is not None:
                self.reaction_queue.enqueue(result)
        self.update_STAT()
        # Only broadcast initial state if start() actually produced something:
        # an output value or a scheduled reaction. Otherwise downstream's view
        # of our ENT stays at the default `never`, and our first eager send
        # later (after our queue actually has events) carries real information.
        # This prevents multi-input downstream from racing past pending events.
        has_output = any(p.value is not None for p in self.output_port_objects.values())
        has_reaction = self.reaction_queue.peek_time() is not None
        if has_output or has_reaction:
            self.send_messages()

    def _send_no_more_to_downstream(self) -> None:
        for output_port in self.output_port_connectors.values():
            for downstream_port, is_physical, delay in output_port.downstream_ports:
                if downstream_port.transport is not None:
                    try:
                        downstream_port.transport.send(
                            NoMoreMessage(
                                timestamp=None,
                                from_port=output_port.name,
                                to_port=downstream_port.name,
                            )
                        )
                    except Exception:
                        pass

    def check_natural_shutdown(self) -> bool:
        def all_done() -> bool:
            for input_port in self.input_port_connectors.values():
                if input_port.active_upstream_count > 0:
                    return False
            if not self.input_port_connectors:
                return True
            return True

        if not self.event_queue and not self.reaction_queue.has_pending() and all_done():
            self._send_no_more_to_downstream()
            return True
        return False

    def close_transports(self) -> None:
        if hasattr(self, "transport"):
            self.transport.close()
        if hasattr(self, "coordinator_transport"):
            self.coordinator_transport.close()
        closed: set[int] = set()
        for output_port in self.output_port_connectors.values():
            for downstream_port, is_physical, delay in output_port.downstream_ports:
                if downstream_port.transport is not None and id(downstream_port.transport) not in closed:
                    downstream_port.transport.close()
                    closed.add(id(downstream_port.transport))

    def shutdown(self, status_code: int = 0) -> None:
        self._send_no_more_to_downstream()
        if hasattr(self.node_instance, "shutdown"):
            self.node_instance.shutdown()
        self.close_transports()
        self.logger.shutdown()
        sys.exit(status_code)
