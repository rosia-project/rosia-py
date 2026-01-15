from typing import Dict, List, Optional, TypeVar, cast
from rosia.comms.Types import ClientType
from rosia.comms.serializers import Serializer
from rosia.comms.transports import Transport
from rosia.coordinate.Node import Node
from rosia.coordinate.Port import InputPort, OutputPort
from rosia.coordinate.messages.base import Message
from rosia.execute.Executor import Executor
from dataclasses import dataclass
import logging

T = TypeVar("T")


@dataclass
class NodeInfo:
    node: Node
    executor: Optional[Executor]
    input_endpoints: Dict[str, str]


class Coordinator:
    def __init__(self, log_level: Optional[int] = logging.INFO) -> None:
        self.node_infos: Dict[str, NodeInfo] = {}
        self.node_count = 0
        self.input_endpoints: Dict[str, str] = {}
        self.log_level = log_level
        self.logger = logging.getLogger("Coordinator")
        logging.basicConfig(level=log_level)

    def create_node(self, node_cls: T) -> T:
        self.node_count += 1
        assert hasattr(node_cls, "_NodeInitArgs"), (
            "Node class must be instantiated as argument to create_node"
        )
        node_init_args = getattr(node_cls, "_NodeInitArgs")
        assert hasattr(node_cls, "_original_cls"), (
            "Node class must be annotated with @Node"
        )
        original_cls = getattr(node_cls, "_original_cls")
        node_name = f"{original_cls.__name__}_{self.node_count}"
        wrapped_node = Node(
            original_cls, node_init_args, node_name=node_name, log_level=self.log_level
        )
        self.node_infos[node_name] = NodeInfo(
            node=wrapped_node, executor=None, input_endpoints={}
        )
        wrapped_node = cast(T, wrapped_node)
        return wrapped_node

    def execute(self) -> None:
        for name, node_info in self.node_infos.items():
            executor = Executor(node_info.node)
            node_info.executor = executor
            node_info.executor.call("_init_input_transports")

        # Collect input endpoints and update upstream outputs
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            input_endpoints = node_info.executor.call(
                "_get_input_transport_endpoint_dict"
            )
            node_info.input_endpoints = input_endpoints
            self.input_endpoints.update(input_endpoints)

        # Update Node copy of input endpoints
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call("_set_output_transports", self.input_endpoints)

        # Initialize node instances
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call("_init_node_instance")

        # Collect output port safe to advance times
        output_port_safe_to_advance_time = {}
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            output_port_safe_to_advance_time.update(
                node_info.executor.call("_get_output_port_safe_to_advance_time")
            )

        def propage_output_sta(port: OutputPort, propagated: List[str]) -> None:
            if port.name in propagated:
                return
            propagated.append(port.name)
            if port.name in output_port_safe_to_advance_time:
                port.set_next_timestamp(
                    min(
                        port.safe_to_advance_time,
                        output_port_safe_to_advance_time[port.name],
                    )
                )
                output_port_safe_to_advance_time[port.name] = min(
                    output_port_safe_to_advance_time[port.name],
                    port.safe_to_advance_time,
                )
            for downstream_port in port.downstream_ports:
                downstream_port.update_safe_to_advance_time()
                for affected_output_port in downstream_port.affected_output_ports:
                    affected_output_port.set_next_timestamp(
                        min(
                            affected_output_port.safe_to_advance_time,
                            downstream_port.safe_to_advance_time,
                        )
                    )
                    propage_output_sta(affected_output_port, propagated)

        for name, node_info in self.node_infos.items():
            for output_port in node_info.node.output_port_infos.values():
                propage_output_sta(output_port, propagated=[])

        # Update ports of safe to advance time
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call(
                "_set_output_port_safe_to_advance_time",
                output_port_safe_to_advance_time,
            )

        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call_no_ret("_execute")

    def set_value(self, port: T, value: T) -> None:
        """setting values with timestamps is not supported in the coordinator"""
        port = cast(InputPort[T], port)  # type: ignore

        assert isinstance(port, InputPort), "You can only set values on input ports"
        if getattr(port, "transport", None) is None:
            if port.name not in self.input_endpoints:
                raise ValueError(
                    f"Endpoint for port {port.name} not found. "
                    "Make sure execute() has been called first."
                )
            endpoint = self.input_endpoints[port.name]
            port.port_type = ClientType.SENDER
            port.transport = Transport(ClientType.SENDER, Serializer, endpoint)
        if port.port_type == ClientType.SENDER:
            port.set_value(
                Message(
                    data=value,
                    timestamp=None,
                    next_timestamp=None,
                    from_port="",
                    to_port=port.name,
                )
            )
        else:
            raise Exception("Internal error: Input port is not a sender")
