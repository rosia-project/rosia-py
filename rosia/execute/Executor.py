from rosia.comms.Types import ClientType
from rosia.comms.request import Client, Server
from rosia.comms.serializers import CloudpickleSerializer as Serializer
from typing import Any, Optional
import multiprocessing
import asyncio

from rosia.execute.Messages import (
    ExecutorStartupMessage,
    ExecutorExecuteRequestMessage,
    ExecutorExecuteResponseMessage,
)


class Executor:
    def __init__(self, cls: Any, controller_endpoint: str):
        self.cls = cls
        self.server = Server(ClientType.RECEIVER, Serializer)
        startup_client = Client(ClientType.SENDER, Serializer, endpoint=controller_endpoint)
        asyncio.run(startup_client.request(ExecutorStartupMessage(executor_receive_endpoint=self.server.endpoint)))
        startup_client.close()

    def handle_request(self, request_message: Any) -> ExecutorExecuteResponseMessage:
        if (
            not isinstance(request_message, ExecutorExecuteRequestMessage)
            or request_message.error_message is not None
            or request_message.func_name == ""
        ):
            return ExecutorExecuteResponseMessage(error_message="Failed to process request: " + str(request_message))
        return self.call(
            request_message.func_name,
            *request_message.args,
            **request_message.kwargs,
        )

    def call(self, func_name: str, *args, **kwargs) -> ExecutorExecuteResponseMessage:
        try:
            method = getattr(self.cls, func_name)
            result = method(*args, **kwargs)
            return ExecutorExecuteResponseMessage(result=result)
        except Exception as e:
            return ExecutorExecuteResponseMessage(error_message=str(e))

    def run(self):
        self.server.serve_callback(self.handle_request)
        self.server.close()


def ExecutorProcess(cls: Any, controller_endpoint: str):
    cls = Serializer().deserialize(cls)
    executor = Executor(cls, controller_endpoint)
    executor.run()


class ExecutorController:
    """
    Creates an ExecutorProcess and manages the class within the process remotely.
    """

    def __init__(self, cls: Any):
        startup_server = Server(ClientType.RECEIVER, Serializer)
        serializer = Serializer()
        serialized_cls = serializer.serialize(cls)
        self.remote_process = multiprocessing.Process(
            target=ExecutorProcess,
            args=(serialized_cls, startup_server.endpoint),
        )
        self.remote_process.start()
        startup_message = None

        def handle_startup(msg: Any) -> Any:
            nonlocal startup_message
            startup_message = msg
            startup_server._running = False
            return msg

        startup_server.serve_callback(handle_startup)
        startup_server.close()
        if (
            not isinstance(startup_message, ExecutorStartupMessage)
            or startup_message.error_message is not None
            or startup_message.executor_receive_endpoint == ""
        ):
            raise RuntimeError("Failed to start executor process: " + str(startup_message))
        self.client = Client(
            ClientType.SENDER,
            Serializer,
            endpoint=startup_message.executor_receive_endpoint,
        )

    async def call(self, func_name: str, *args, **kwargs):
        response_message = await self.client.request(
            ExecutorExecuteRequestMessage(func_name=func_name, args=args, kwargs=kwargs)
        )
        if (
            not isinstance(response_message, ExecutorExecuteResponseMessage)
            or response_message.error_message is not None
        ):
            raise RuntimeError("Failed to execute function: " + str(response_message))
        return response_message.result

    def send(self, msg: ExecutorExecuteRequestMessage) -> None:
        """Send a request without waiting for a reply. Closes the client after sending."""
        self.client.socket.send(self.client.serializer.serialize(msg))
        self.client.close()

    def join(self, timeout: Optional[float] = None) -> None:
        """Wait for the child process to exit."""
        self.remote_process.join(timeout=timeout)
