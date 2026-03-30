from typing import Any, Type

from rosia.comms.serializers.base import SerializerBase

from rosia.comms.transports.base import TransportBase
from rosia.comms.Types import ClientType
import zmq


class ZMQTransport(TransportBase):
    def __init__(
        self,
        type: ClientType,
        serializer: Type[SerializerBase],
        endpoint: str = "",
    ):
        self.type = type
        self.serializer = serializer(type)
        context = zmq.Context.instance()
        self.socket: zmq.Socket
        if type == ClientType.SENDER:
            self.socket = context.socket(zmq.PUSH)
            self.socket.connect(endpoint)
        else:
            assert endpoint == "", (
                "Endpoint will be automatically assigned for receiver."
            )
            self.socket = context.socket(zmq.PULL)
            port = self.socket.bind_to_random_port("tcp://127.0.0.1")
            self.endpoint = f"tcp://127.0.0.1:{port}"
        self._has_pending: bool = False

    def send(self, msg: Any):
        assert self.type == ClientType.SENDER, "Cannot send on a receiver socket."
        self.socket.send(self.serializer.serialize(msg))

    def receive(self) -> Any:
        """Non-blocking receive. Returns None if no message available."""
        assert self.type == ClientType.RECEIVER, "Cannot receive on a sender socket."
        if self._has_pending or self.socket.poll(0, zmq.POLLIN):
            self._has_pending = False
            return self.serializer.deserialize(self.socket.recv())
        return None

    def receive_blocking(self, timeout: int = -1) -> Any:
        """Blocking receive. Returns None if timed out."""
        assert self.type == ClientType.RECEIVER, "Cannot receive on a sender socket."
        if timeout >= 0:
            if not self.socket.poll(timeout, zmq.POLLIN):
                return None
        return self.serializer.deserialize(self.socket.recv())

    def wait_for_message(self, timeout: int = -1) -> bool:
        assert self.type == ClientType.RECEIVER, (
            "Cannot wait for a message on a sender socket."
        )
        if self._has_pending:
            return True
        result = self.socket.poll(timeout, zmq.POLLIN)
        if result:
            self._has_pending = True
        return result != 0

    def close(self):
        self.socket.close()


if __name__ == "__main__":
    from rosia.comms.serializers.pickle import Serializer
    import time

    def run_test():
        # Receiver auto-binds to random port
        receiver = ZMQTransport(ClientType.RECEIVER, Serializer, "")
        print(f"Receiver bound to: {receiver.endpoint}")

        # Sender connects to receiver's endpoint
        sender = ZMQTransport(ClientType.SENDER, Serializer, receiver.endpoint)

        # Give connection time to establish
        time.sleep(0.1)

        # Test send and receive_blocking
        sender.send("Hello, ZMQ!")
        msg = receiver.receive_blocking()
        print(f"Received: {msg}")

        # Test send and receive (non-blocking)
        sender.send("Hello, ZMQ2!")
        time.sleep(0.1)  # Give time for message to arrive
        msg = receiver.receive()
        print(f"Received: {msg}")

        # Test receive when no message available
        msg = receiver.receive()
        print(f"Received (should be None): {msg}")

        # Test large message
        import os

        sender.send(os.urandom(1048576))
        msg = receiver.receive_blocking()
        print(f"Received large message: {len(msg)} bytes")

        receiver.close()
        sender.close()

    run_test()
