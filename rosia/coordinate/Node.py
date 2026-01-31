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
from typing import Any, Dict, Optional, Tuple, Type, TypeVar, List
import traceback
import sys

from rosia.time import Time, forever

T = TypeVar("T")


class NodeRuntime:
    def __init__(
        self,
        rosia_annotations: RosiaAnnotations,
        node_name: str,
        transport_cls: Type[TransportBase] = Transport,
        serializer_cls: Type[SerializerBase] = Serializer,
    ) -> None:
        check_rosia_annotations(rosia_annotations)
        node_cls = rosia_annotations["original_cls"]
        self.node_cls = clone_class_detached(
            node_cls, f"{node_cls.__name__}NodeRuntime"
        )
        self.node_original_init = rosia_annotations["original_init"]
        self.node_init_args = rosia_annotations["init_args"]
        self.node_name = node_name

        self.serializer_cls: Type[SerializerBase] = serializer_cls
        self.transport_cls: Type[TransportBase] = transport_cls

        self.transport: Optional[TransportBase] = None
        self.input_port_connectors: Dict[str, InputPortConnector[Any]] = {}
        self.output_port_connectors: Dict[str, OutputPortConnector[Any]] = {}

        self.current_time: Time = Time(0)
        self.next_time: Time = Time(0)
        self.safe_to_advance_time: Time = Time(
            0
        )  # Safe to advance time to any current_time < safe_to_advance_time
        self.message_queue: Dict[
            Time, List[Tuple[Message[Any], InputPortConnector[Any]]]
        ] = {}

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

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self.__dict__.update(state)

    def init_input_transports(self) -> None:
        self.transport = self.transport_cls(ClientType.RECEIVER, self.serializer_cls)
        for name, input_port in self.input_port_connectors.items():
            input_port.port_type = ClientType.RECEIVER

    def get_input_transport_endpoint_dict(self) -> Dict[str, str]:
        # Return a single endpoint for the node (all input ports share the same endpoint)
        if self.transport is None:
            raise RuntimeError("Transport not initialized")
        node_endpoint = self.transport.endpoint
        return {name: node_endpoint for name in self.input_port_connectors.keys()}

    def init_output_transports(self, intput_endpoints: Dict[str, str]) -> None:
        downstream_nodes: Dict[str, List[InputPortConnector[Any]]] = {}
        for name, output_port in self.output_port_connectors.items():
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

    def init_node_instance(self) -> None:
        setattr(self.node_instance, "__init__", self.node_original_init)
        if self.node_init_args is None:
            raise RuntimeError(
                f"Node init args are not set for node {self.node_name}. This is a bug within the Rosia framework."
            )
        self.node_instance.__init__(
            self.node_instance, *self.node_init_args.args, **self.node_init_args.kwargs
        )

    def get_output_port_safe_to_advance_time(self) -> Dict[str, Time]:
        output_port_safe_to_advance_time = {}
        for output_port in self.output_port_connectors.values():
            output_port_safe_to_advance_time[output_port.name] = (
                output_port.safe_to_advance_time
            )
        return output_port_safe_to_advance_time

    def set_output_port_safe_to_advance_time(
        self, output_port_to_sta: Dict[str, Time]
    ) -> None:
        for input_port in self.input_port_connectors.values():
            for output_port in input_port.upstream_ports:
                if output_port.name in output_port_to_sta.keys():
                    output_port.set_next_timestamp(output_port_to_sta[output_port.name])
            input_port.update_safe_to_advance_time()

    def update_safe_to_advance_time(self) -> None:
        old_safe_to_advance_time = self.safe_to_advance_time
        min_safe_to_advance_time = forever
        for input_port in self.input_port_connectors.values():
            min_safe_to_advance_time = min(
                min_safe_to_advance_time, input_port.safe_to_advance_time
            )
        # print(
        #     f"Advance time: {old_safe_to_advance_time} -> {min_safe_to_advance_time}"
        # )
        if old_safe_to_advance_time > min_safe_to_advance_time:
            print(
                f"Safe to advance time decreased from {old_safe_to_advance_time} to {min_safe_to_advance_time}"
            )
        self.safe_to_advance_time = min_safe_to_advance_time

    def event_loop(self) -> None:
        if self.transport is None:
            raise RuntimeError("Transport not initialized")
        while True:
            while True:
                message: Optional[Message[Any]] = self.transport.receive()
                if message is None:
                    break

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
                affected_output_ports: List[OutputPortConnector[Any]] = []
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

    def execute(self) -> None:
        try:
            if hasattr(self.node_instance, "start"):
                self.node_instance.start()
            self.event_loop()
        except KeyboardInterrupt:
            print("KeyboardInterrupt received, shutting down")
            sys.exit(0)
        except Exception as e:
            print(f"Exception in {self.node_name}: {e}")
            traceback.print_exc()
