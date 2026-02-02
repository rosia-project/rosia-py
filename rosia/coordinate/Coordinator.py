from typing import Dict, List, Optional, TypeVar, cast
from rosia.comms.Types import ClientType
from rosia.comms.serializers import Serializer
from rosia.comms.transports import Transport
from rosia.coordinate.Node import NodeRuntime
from rosia.frontend.Connection import InputPortConnector, OutputPortConnector
from rosia.coordinate.messages.base import Message, ShutdownMessage
from rosia.execute import ExecutorController
from dataclasses import dataclass
import logging
from rosia.frontend.Annotators import get_rosia_annotations, check_rosia_annotations
from rosia.coordinate.messages.base import CoordinatorShutdownRequestMessage
import sys

T = TypeVar("T")


@dataclass
class NodeRuntimeInfo:
    node: NodeRuntime
    executor: Optional[ExecutorController]


class Coordinator:
    def __init__(self, log_level: str = "WARNING") -> None:
        self.log_level = log_level
        self.node_infos: Dict[str, NodeRuntimeInfo] = {}
        self.node_endpoints: Dict[str, str] = {}
        self.logger = logging.getLogger("Coordinator")
        self.coordinator_receiver_transport = Transport(ClientType.RECEIVER, Serializer)

    def create_node(self, node_cls: T) -> T:
        rosia_annotations = get_rosia_annotations(node_cls)
        check_rosia_annotations(rosia_annotations)
        node_name = (
            f"{rosia_annotations['original_cls'].__name__}_{len(self.node_infos)}"
        )
        node_runtime = NodeRuntime(
            rosia_annotations=rosia_annotations,
            node_name=node_name,
            coordinator_receiver_endpoint=self.coordinator_receiver_transport.endpoint,
            log_level=self.log_level,
        )
        self.node_infos[node_name] = NodeRuntimeInfo(node=node_runtime, executor=None)
        return cast(T, node_runtime)

    def execute(self) -> None:
        # Setup remote nodes and initialize input endpoints
        for name, node_info in self.node_infos.items():
            executor = ExecutorController(node_info.node)
            node_info.executor = executor
            node_endpoints = node_info.executor.call("init_remote")
            self.node_endpoints.update(node_endpoints)

        # Update Node copy of input endpoints
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call("init_output_transports", self.node_endpoints)

        # Initialize node instances
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call("init_node_instance")

        # Collect output port safe to advance times
        output_port_safe_to_advance_time = {}
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            output_port_safe_to_advance_time.update(
                node_info.executor.call("get_output_port_ENT")
            )

        def propage_output_sta(
            port: OutputPortConnector, propagated: List[str]
        ) -> None:
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
            for output_port in node_info.node.output_port_connectors.values():
                propage_output_sta(output_port, propagated=[])

        # Update ports of safe to advance time
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call(
                "set_output_port_ENT",
                output_port_safe_to_advance_time,
            )

        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call_no_ret("execute")

        # Wait for shutdown request
        self.coordinator_receiver_transport.wait_for_message()
        message = self.coordinator_receiver_transport.receive()
        if not isinstance(message, CoordinatorShutdownRequestMessage):
            raise ValueError("Expected CoordinatorShutdownMessage")
        shutdown_timestamp = message.timestamp
        status_code = message.status_code
        for name, node_info in self.node_infos.items():
            self.coordinator_sender_transport = Transport(
                ClientType.SENDER, Serializer, self.node_endpoints[name]
            )
            self.coordinator_sender_transport.send(
                ShutdownMessage(
                    timestamp=shutdown_timestamp,
                )
            )
        if status_code != 0:
            sys.exit(status_code)

    def set_value(self, port: T, value: T) -> None:
        """setting values with timestamps is not supported in the coordinator"""
        port = cast(InputPortConnector[T], port)  # type: ignore

        assert isinstance(port, InputPortConnector), (
            "You can only set values on input ports"
        )
        if getattr(port, "transport", None) is None:
            if port.name not in self.node_endpoints:
                raise ValueError(
                    f"Endpoint for port {port.name} not found. "
                    "Make sure execute() has been called first."
                )
            endpoint = self.node_endpoints[port.name]
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
