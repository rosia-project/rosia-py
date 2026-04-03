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
from rosia.coordinate.messages.base import ApplicationShutdownRequestMessage
import asyncio
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


class Application:
    def __init__(self) -> None:
        self.node_infos: Dict[str, NodeRuntimeInfo] = {}
        self.node_endpoints: Dict[str, str] = {}
        self.coordinator_receiver_transport = Transport(ClientType.RECEIVER, Serializer)
        self.logger = Logger(self.__class__.__name__)

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

    def diagram(
        self,
        rerun_config: Optional[RerunConfig] = None,
        save_to: Optional[str] = None,
        save_json: bool = False,
    ) -> None:
        if rerun_config is not None:
            rosia.rerun_manager.init(rerun_config)
        diagram(
            self.node_infos,
            save_to=save_to,
            rerun=rerun_config is not None,
            save_json=save_json,
        )

    def execute(
        self,
        trace: bool = False,
        log_level: str = "INFO",
        rerun_config: Optional[RerunConfig] = None,
        timeout: Optional[float] = None,
    ) -> None:
        asyncio.run(
            self._execute(
                trace=trace,
                log_level=log_level,
                rerun_config=rerun_config,
                timeout=timeout,
            )
        )

    async def _execute(
        self,
        trace: bool = False,
        log_level: str = "INFO",
        rerun_config: Optional[RerunConfig] = None,
        timeout: Optional[float] = None,
    ) -> None:
        if log_level.upper() not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError(
                f"Invalid log level: {log_level}, valid levels are: DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        log_level_int = getattr(logging, log_level.upper(), logging.INFO)
        execution_config = ExecutionConfig(trace=trace, log_level=log_level_int)
        self.execution_config = execution_config
        self.logger.set_level(execution_config.log_level)
        self.logger.set_trace(execution_config.trace)
        if rerun_config is not None:
            self.logger.set_rerun_config(rerun_config)
        self.logger.debug(f"Start execution with config: {execution_config}")
        self.logger.debug("Setting up remote nodes and initializing input endpoints...")
        executor_controllers: Dict[str, ExecutorController] = {}
        for name, node_info in self.node_infos.items():
            executor_controller = ExecutorController(node_info.node)
            node_info.executor = executor_controller
            executor_controllers[name] = executor_controller
        init_results = await asyncio.gather(
            *(
                executor_controller.call("init_remote", execution_config, rerun_config)
                for executor_controller in executor_controllers.values()
            )
        )
        for node_endpoints in init_results:
            self.node_endpoints.update(node_endpoints)

        self.logger.debug("Updating Node copy of input endpoints...")
        await asyncio.gather(
            *(
                executor_controller.call("init_output_transports", self.node_endpoints)
                for executor_controller in executor_controllers.values()
            )
        )

        self.logger.debug("Initializing node instances...")
        await asyncio.gather(
            *(
                executor_controller.call("init_node_instance")
                for executor_controller in executor_controllers.values()
            )
        )

        self.logger.debug("Collecting output port safe to advance to values...")
        output_port_safe_to_advance_to = {}
        dstat_results = await asyncio.gather(
            *(
                executor_controller.call("get_output_port_DSTAT")
                for executor_controller in executor_controllers.values()
            )
        )
        for dstat in dstat_results:
            output_port_safe_to_advance_to.update(dstat)

        self.logger.debug("Propagating output port DSTATs...")

        def propagate_output_DSTAT(
            port: OutputPortConnector, propagated: List[str]
        ) -> None:
            if port.name in propagated:
                return
            propagated.append(port.name)
            if port.name in output_port_safe_to_advance_to:
                port.set_DSTAT(
                    min(
                        port.safe_to_advance_to,
                        output_port_safe_to_advance_to[port.name],
                    )
                )
                output_port_safe_to_advance_to[port.name] = min(
                    output_port_safe_to_advance_to[port.name],
                    port.safe_to_advance_to,
                )
            for downstream_port in port.downstream_ports:
                downstream_port.update_safe_to_advance_to()
                for affected_output_port in downstream_port.affected_output_ports:
                    affected_output_port.set_DSTAT(
                        min(
                            affected_output_port.safe_to_advance_to,
                            downstream_port.safe_to_advance_to,
                        )
                    )
                    propagate_output_DSTAT(affected_output_port, propagated)

        for name, node_info in self.node_infos.items():
            for output_port in node_info.node.output_port_connectors.values():
                propagate_output_DSTAT(output_port, propagated=[])

        self.logger.debug("Updating ports DSTATs...")
        await asyncio.gather(
            *(
                executor_controller.call(
                    "set_output_port_DSTAT",
                    output_port_safe_to_advance_to,
                )
                for executor_controller in executor_controllers.values()
            )
        )

        self.logger.debug("Executing nodes...")
        start_physical_time = get_physical_time()
        await asyncio.gather(
            *(
                executor_controller.call_no_ret(
                    "execute", start_logical_time=start_physical_time
                )
                for executor_controller in executor_controllers.values()
            )
        )

        self.logger.debug("Waiting for shutdown request...")
        timeout_ms = int(timeout * 1000) if timeout is not None else -1
        has_message = self.coordinator_receiver_transport.wait_for_message(
            timeout=timeout_ms
        )
        if not has_message:
            self.logger.debug("Timeout reached, initiating shutdown...")
            shutdown_timestamp = get_physical_time() - start_physical_time
            status_code = 0
        else:
            message = self.coordinator_receiver_transport.receive()
            self.logger.debug(f"Received shutdown request: {message}")
            if not isinstance(message, ApplicationShutdownRequestMessage):
                raise ValueError("Expected ApplicationShutdownRequestMessage")
            shutdown_timestamp = message.timestamp
            status_code = message.status_code
        # Drain any additional shutdown requests that arrived
        while True:
            extra = self.coordinator_receiver_transport.receive()
            if extra is None:
                break
            self.logger.warning(f"Ignoring additional shutdown request: {extra}")
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
        # Wait for all child processes to finish so they can flush output
        # and release resources cleanly before the main process exits.
        for name, node_info in self.node_infos.items():
            if node_info.executor is not None:
                node_info.executor.join()

        if status_code != 0:
            sys.exit(status_code)
