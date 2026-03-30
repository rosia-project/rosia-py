from rosia.comms.Types import ClientType
from rosia.comms.transports import Transport
from rosia.comms.serializers import CloudpickleSerializer as Serializer
from typing import Any, Optional
import multiprocessing

from rosia.execute.Messages import (
    ExecutorMessage,
    ExecutorStartupMessage,
    ExecutorExecuteRequestMessage,
    ExecutorExecuteResponseMessage,
)


class Executor:
    def __init__(self, cls: Any, response_endpoint: str):
        self.cls = cls
        self.receive_request_transport = Transport(ClientType.RECEIVER, Serializer)
        self.send_response_transport = Transport(
            ClientType.SENDER, Serializer, endpoint=response_endpoint
        )

    def send_response(self, message: ExecutorMessage):
        self.send_response_transport.send(message)

    def call(self, func_name: str, *args, **kwargs):
        try:
            method = getattr(self.cls, func_name)
            result = method(*args, **kwargs)
            self.send_response(ExecutorExecuteResponseMessage(result=result))
        except Exception as e:
            self.send_response(ExecutorExecuteResponseMessage(error_message=str(e)))


def ExecutorProcess(cls: Any, response_endpoint: str):
    cls = Serializer().deserialize(cls)
    executor = Executor(cls, response_endpoint)
    executor.send_response(
        ExecutorStartupMessage(
            executor_receive_endpoint=executor.receive_request_transport.endpoint
        )
    )
    while True:
        request_message = executor.receive_request_transport.receive_blocking()
        if (
            not isinstance(request_message, ExecutorExecuteRequestMessage)
            or request_message.error_message is not None
            or request_message.func_name == ""
        ):
            executor.send_response(
                ExecutorExecuteResponseMessage(
                    error_message="Failed to process request: " + str(request_message)
                )
            )
        else:
            executor.call(
                request_message.func_name,
                *request_message.args,
                **request_message.kwargs,
            )


class ExecutorController:
    """
    Creates an ExecutorProcess and manages the class within the process remotely.
    """

    def __init__(self, cls: Any):
        self.response_transport = Transport(ClientType.RECEIVER, Serializer)
        serializer = Serializer()
        serialized_cls = serializer.serialize(cls)
        self.remote_process = multiprocessing.Process(
            target=ExecutorProcess,
            args=(serialized_cls, self.response_transport.endpoint),
        )
        self.remote_process.start()
        response_message = self.response_transport.receive_blocking()
        if (
            not isinstance(response_message, ExecutorStartupMessage)
            or response_message.error_message is not None
            or response_message.executor_receive_endpoint == ""
        ):
            raise RuntimeError(
                "Failed to start executor process: " + str(response_message)
            )
        executor_receive_endpoint = response_message.executor_receive_endpoint
        self.request_transport = Transport(
            ClientType.SENDER, Serializer, endpoint=executor_receive_endpoint
        )

    def call(self, func_name: str, *args, **kwargs):
        self.request_transport.send(
            ExecutorExecuteRequestMessage(func_name=func_name, args=args, kwargs=kwargs)
        )
        response_message = self.response_transport.receive_blocking()
        if (
            not isinstance(response_message, ExecutorExecuteResponseMessage)
            or response_message.error_message is not None
        ):
            raise RuntimeError("Failed to execute function: " + str(response_message))
        return response_message.result

    def call_no_ret(self, func_name: str, *args, **kwargs):
        self.request_transport.send(
            ExecutorExecuteRequestMessage(func_name=func_name, args=args, kwargs=kwargs)
        )

    def join(self, timeout: Optional[float] = None) -> None:
        """Wait for the child process to exit."""
        self.remote_process.join(timeout=timeout)
