from rosia.comms.Types import ClientType
from rosia.comms.transports import Transport, TransportBase
from rosia.comms.serializers import Serializer, SerializerBase
from rosia.coordinate.Port import (
    InputPort,
    OutputPort,
    InputPortUserObject,
    OutputPortUserObject,
)

from rosia.coordinate.messages.base import Message
from rosia.execute import Executor
from rosia.frontend.Node import NodeInitArgs
from rosia.frontend.Port import (
    InputPort as UserInputPort,
    OutputPort as UserOutputPort,
    InjectedRosia,
)

from typing import Any, Dict, Optional, Tuple, Type, TypeVar, List
import traceback
import sys
import logging

from rosia.time import Time, forever

T = TypeVar("T")


def clone_class_detached(original_cls, new_name):
    new_namespace = dict(original_cls.__dict__)
    for key in ["__dict__", "__weakref__", "__module__"]:
        new_namespace.pop(key, None)
    return type(new_name, original_cls.__bases__, new_namespace)


class Node:
    def __init__(
        self,
        node_cls: Type[T],
        node_init_args: NodeInitArgs,
        node_name: str,
        transport_cls: Optional[Type[TransportBase]] = None,
        serializer_cls: Optional[Type[SerializerBase]] = None,
        log_level: Optional[int] = logging.INFO,
    ) -> None:
        self.node_cls = clone_class_detached(node_cls, f"{node_cls.__name__}Node")
        self.node_name = node_name
        self.log_level = log_level
        self._setup_logger(log_level)
        self.executor: Executor

        self.serializer_cls: Type[SerializerBase]
        self.transport_cls: Type[TransportBase]
        if serializer_cls is None:
            self.serializer_cls = Serializer
        else:
            self.serializer_cls = serializer_cls
        if transport_cls is None:
            self.transport_cls = Transport
        else:
            self.transport_cls = transport_cls

        self.transport: Optional[TransportBase] = None

        self.input_port_infos: Dict[str, InputPort[Any]] = {}
        self.output_port_infos: Dict[str, OutputPort[Any]] = {}

        self.current_time: Time = Time(0)
        self.next_time: Time = Time(0)
        self.safe_to_advance_time: Time = Time(
            0
        )  # Safe to advance time to any current_time < safe_to_advance_time
        self.message_queue: Dict[Time, List[Tuple[Message[Any], InputPort[Any]]]] = {}
        # Initialize output ports
        for name, value in self.node_cls.__dict__.items():
            if isinstance(value, UserOutputPort):
                output_port = OutputPort(
                    owner=self,
                    name=value.name,
                )
                output_port_user_object = OutputPortUserObject(self, output_port)
                port_name = f"{self.node_name}.{name}"
                self.output_port_infos[port_name] = output_port
                self.__setattr__(name, output_port)
                setattr(self.node_cls, name, output_port_user_object)

        # Initialize input ports
        for name, value in self.node_cls.__dict__.items():
            if isinstance(value, UserInputPort):
                trigger_functions = value.trigger_functions
                input_port_user_object = InputPortUserObject(self)
                affected_output_port_names = list(set(value.affected_output_port_names))
                affected_output_ports = []
                for port_name in affected_output_port_names:
                    output_port_name = f"{self.node_name}.{port_name}"
                    if output_port_name in self.output_port_infos:
                        affected_output_ports.append(
                            self.output_port_infos[output_port_name]
                        )
                # print("affected output ports", affected_output_ports)
                input_port = InputPort(
                    owner=self,
                    name=value.name,
                    trigger_functions=trigger_functions,
                    input_port_user_object=input_port_user_object,
                    affected_output_ports=affected_output_ports,
                )
                port_name = f"{self.node_name}.{name}"
                self.input_port_infos[port_name] = input_port
                self.__setattr__(name, input_port)
                setattr(self.node_cls, name, input_port_user_object)

        self.node_init_args = node_init_args

        def stub_init(self, *args, **kwargs):
            pass

        setattr(self.node_cls, "__init__", stub_init)
        self.node_instance = self.node_cls()
        setattr(self.node_instance, "rosia", InjectedRosia(self.logger, self.node_name))

    def _setup_logger(self, log_level) -> None:
        self.logger = logging.getLogger(f"{self.node_name}")
        handler = logging.StreamHandler()
        formatter = logging.Formatter("[%(name)s] %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        self.logger.setLevel(log_level)
        self.logger.addHandler(handler)

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._setup_logger(
            self.log_level
        )  # This is necessary to set the logger after unpickling

    def _init_input_transports(self) -> None:
        self.transport = self.transport_cls(ClientType.RECEIVER, self.serializer_cls)
        for name, input_port in self.input_port_infos.items():
            input_port.port_type = ClientType.RECEIVER

    def _get_input_transport_endpoint_dict(self) -> Dict[str, str]:
        # Return a single endpoint for the node (all input ports share the same endpoint)
        if self.transport is None:
            raise RuntimeError("Transport not initialized")
        node_endpoint = self.transport.endpoint
        return {name: node_endpoint for name in self.input_port_infos.keys()}

    def _set_output_transports(self, intput_endpoints: Dict[str, str]) -> None:
        downstream_nodes: Dict[str, List[InputPort[Any]]] = {}
        for name, output_port in self.output_port_infos.items():
            for downstream_port in output_port.downstream_ports:
                downstream_node_name = downstream_port.owner.node_name
                if downstream_node_name not in downstream_nodes:
                    downstream_nodes[downstream_node_name] = []
                downstream_nodes[downstream_node_name].append(downstream_port)

        for node_name, ports_list in downstream_nodes.items():
            first_port = ports_list[0]
            if first_port.name not in intput_endpoints:
                raise ValueError(f"Input endpoint for {first_port.name} not found")
            node_endpoint = intput_endpoints[first_port.name]

            node_transport = self.transport_cls(
                ClientType.SENDER,
                self.serializer_cls,
                node_endpoint,
            )

            for downstream_port in ports_list:
                downstream_port.port_type = ClientType.SENDER
                downstream_port.transport = node_transport

    def _init_node_instance(self) -> None:
        assert hasattr(self.node_instance, "_original_init"), (
            "Node instance has no original_init"
        )
        if self.node_instance._original_init is not None:  # type: ignore
            self.node_instance._original_init(
                *self.node_init_args.args, **self.node_init_args.kwargs
            )  # type: ignore

    def _get_output_port_safe_to_advance_time(self) -> Dict[str, Time]:
        output_port_safe_to_advance_time = {}
        for output_port in self.output_port_infos.values():
            output_port_safe_to_advance_time[output_port.name] = (
                output_port.safe_to_advance_time
            )
        return output_port_safe_to_advance_time

    def _set_output_port_safe_to_advance_time(
        self, output_port_to_sta: Dict[str, Time]
    ) -> None:
        self.logger.debug(
            f"Setting safe to advance time for input ports based on output ports: {output_port_to_sta}"
        )
        for input_port in self.input_port_infos.values():
            for output_port in input_port.upstream_ports:
                if output_port.name in output_port_to_sta.keys():
                    output_port.set_next_timestamp(output_port_to_sta[output_port.name])
                    self.logger.debug(
                        f"Set safe to advance time for output port {output_port.name} to {output_port_to_sta[output_port.name]}"
                    )
            input_port.update_safe_to_advance_time()

    def update_safe_to_advance_time(self) -> None:
        old_safe_to_advance_time = self.safe_to_advance_time
        min_safe_to_advance_time = forever
        for input_port in self.input_port_infos.values():
            min_safe_to_advance_time = min(
                min_safe_to_advance_time, input_port.safe_to_advance_time
            )
        self.logger.debug(
            f"Advance time: {old_safe_to_advance_time} -> {min_safe_to_advance_time}"
        )
        if old_safe_to_advance_time > min_safe_to_advance_time:
            self.logger.warning(
                f"Safe to advance time decreased from {old_safe_to_advance_time} to {min_safe_to_advance_time}"
            )
        self.safe_to_advance_time = min_safe_to_advance_time

    def _event_loop(self) -> None:
        if self.transport is None:
            raise RuntimeError("Transport not initialized")
        self.logger.debug("Starting event loop for node")
        while True:
            while True:
                message: Optional[Message[Any]] = self.transport.receive()
                if message is None:
                    break

                # Demux message to the correct input port based on to_port
                if message.to_port is None:
                    raise ValueError(f"Message missing to_port field: {message}")

                if message.to_port not in self.input_port_infos:
                    raise ValueError(
                        f"Message to_port {message.to_port} not found in node {self.node_name}"
                    )

                input_port = self.input_port_infos[message.to_port]

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
                        self.message_queue[message.timestamp] = [(message, input_port)]
                    else:
                        self.message_queue[message.timestamp].append(
                            (message, input_port)
                        )
                else:
                    # it is simply a coordination message to update the STA
                    pass

            self.update_safe_to_advance_time()

            ready_timestamps = [
                timestamp
                for timestamp in self.message_queue.keys()
                if timestamp < self.safe_to_advance_time
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
                messages_and_input_ports = self.message_queue[timestamp]
                trigger_functions = set()
                # Sort messages by from_port to avoid nondeterministic behavior
                sorted_messages_and_input_ports = sorted(
                    messages_and_input_ports, key=lambda x: x[0].from_port
                )
                affected_output_ports: List[OutputPort[Any]] = []
                for message, input_port in sorted_messages_and_input_ports:
                    input_port.set_value(message)
                    affected_output_ports.extend(input_port.affected_output_ports)
                    trigger_functions.update(input_port.trigger_functions)
                for trigger_function in trigger_functions:
                    trigger_function(self.node_instance)
                for output_port in affected_output_ports:
                    # The output may not be set by the user code, but we need to update the downstream STA
                    output_port._set_value(None, None, self.next_time)
                del self.message_queue[timestamp]

            # Blocking wait for messages on the single node transport
            self.transport.wait_for_message()

    def _execute(self) -> None:
        try:
            if hasattr(self.node_instance, "start"):
                self.node_instance.start()
            self._event_loop()
        except KeyboardInterrupt:
            self.logger.debug("KeyboardInterrupt received, shutting down")
            sys.exit(0)
        except Exception as e:
            print(f"Exception in {self.node_name}: {e}")
            traceback.print_exc()
