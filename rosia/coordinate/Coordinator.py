from typing import Dict, List, Optional, TypeVar, cast
from rosia.comms.Types import ClientType
from rosia.comms.serializers import Serializer
from rosia.comms.transports import Transport
from rosia.config import ExecutionConfig
from rosia.coordinate.Node import NodeRuntime
from rosia.frontend.Connection import OutputPortConnector
from rosia.coordinate.messages.base import ShutdownMessage
from rosia.execute import ExecutorController
from dataclasses import dataclass
from rosia.frontend.Annotators import get_rosia_annotations, check_rosia_annotations
from rosia.coordinate.messages.base import CoordinatorShutdownRequestMessage
import logging
import sys
from rosia.time.utils import get_physical_time
from rosia.diagram import diagram
from rosia.config import RerunConfig
from rosia.logging import Logger
import rosia

T = TypeVar("T")


@dataclass
class NodeRuntimeInfo:
    node: NodeRuntime
    executor: Optional[ExecutorController]


class Coordinator:
    def __init__(self) -> None:
        self.node_infos: Dict[str, NodeRuntimeInfo] = {}
        self.node_endpoints: Dict[str, str] = {}
        self.coordinator_receiver_transport = Transport(ClientType.RECEIVER, Serializer)
        self.logger = Logger(self.__class__.__name__)
        self.logger.debug("Coordinator created")

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
        )
        self.node_infos[node_name] = NodeRuntimeInfo(node=node_runtime, executor=None)
        self.logger.debug(f"Create node: {node_name}")
        return cast(T, node_runtime)

    def diagram(self, rerun_config: RerunConfig = RerunConfig()) -> None:
        self.logger.debug("Render diagram")
        rosia.rerun_manager.init(rerun_config)
        diagram(self.node_infos)

    def execute(
        self,
        trace: bool = False,
        log_level: str = "INFO",
        rerun_config: RerunConfig = RerunConfig(),
    ) -> None:
        if log_level.upper() not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError(
                f"Invalid log level: {log_level}, valid levels are: DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        log_level_int = getattr(logging, log_level.upper(), logging.INFO)
        execution_config = ExecutionConfig(trace=trace, log_level=log_level_int)
        self.execution_config = execution_config
        self.logger.set_level(execution_config.log_level)
        self.logger.set_trace(execution_config.trace, rerun_config)
        self.logger.debug(f"Start execution with config: {execution_config}")
        self.logger.debug("Setting up remote nodes and initializing input endpoints...")
        # Setup remote nodes and initialize input endpoints
        for name, node_info in self.node_infos.items():
            executor = ExecutorController(node_info.node)
            node_info.executor = executor
            node_endpoints = node_info.executor.call(
                "init_remote", execution_config, rerun_config
            )
            self.node_endpoints.update(node_endpoints)

        self.logger.debug("Updating Node copy of input endpoints...")
        # Update Node copy of input endpoints
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call("init_output_transports", self.node_endpoints)

        self.logger.debug("Initializing node instances...")
        # Initialize node instances
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call("init_node_instance")

        self.logger.debug("Collecting output port safe to advance times...")
        # Collect output port safe to advance times
        output_port_safe_to_advance_time = {}
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            output_port_safe_to_advance_time.update(
                node_info.executor.call("get_output_port_ENT")
            )

        self.logger.debug("Propagating output port ENTs...")

        def propage_output_ENT(
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
                    propage_output_ENT(affected_output_port, propagated)

        for name, node_info in self.node_infos.items():
            for output_port in node_info.node.output_port_connectors.values():
                propage_output_ENT(output_port, propagated=[])

        self.logger.debug("Updating ports ENTs...")
        # Update ports ENTs
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call(
                "set_output_port_ENT",
                output_port_safe_to_advance_time,
            )

        self.logger.debug("Executing nodes...")
        start_physical_time = get_physical_time()
        for name, node_info in self.node_infos.items():
            assert node_info.executor is not None
            node_info.executor.call_no_ret(
                "execute", start_logical_time=start_physical_time
            )

        self.logger.debug("Waiting for shutdown request...")
        self.coordinator_receiver_transport.wait_for_message()
        message = self.coordinator_receiver_transport.receive()
        self.logger.debug(f"Received shutdown request: {message}")
        if not isinstance(message, CoordinatorShutdownRequestMessage):
            raise ValueError("Expected CoordinatorShutdownRequestMessage")
        shutdown_timestamp = message.timestamp
        status_code = message.status_code
        if shutdown_timestamp is None:
            raise ValueError("Shutdown timestamp is None")
        self.logger.set_logical_time(shutdown_timestamp)
        self.logger.set_physical_time(get_physical_time() - start_physical_time)
        for name, node_info in self.node_infos.items():
            self.logger.debug(
                f"Sending shutdown request to node: {name} with timestamp {shutdown_timestamp}"
            )
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
