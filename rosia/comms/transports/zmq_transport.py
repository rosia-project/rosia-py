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
            assert endpoint == "", "Endpoint will be automatically assigned for receiver."
            self.socket = context.socket(zmq.PULL)
            port = self.socket.bind_to_random_port("tcp://127.0.0.1")
            self.endpoint = f"tcp://127.0.0.1:{port}"

    def send(self, msg: Any):
        assert self.type == ClientType.SENDER, "Cannot send on a receiver socket."
        self.socket.send(self.serializer.serialize(msg))

    def receive(self) -> Any:
        """Non-blocking receive. Returns None if no message available."""
        try:
            return self.serializer.deserialize(self.socket.recv(zmq.NOBLOCK))
        except zmq.Again:
            return None

    def wait_for_message(self, timeout: int = -1) -> bool:
        assert self.type == ClientType.RECEIVER, "Cannot wait for a message on a sender socket."
        result = self.socket.poll(timeout, zmq.POLLIN)
        return result != 0

    def wait_for_message_or_wake(self, wake_socket: "zmq.Socket", timeout: int = -1) -> bool:
        """Block until either a message is available on the transport or
        ``wake_socket`` is readable (used to interrupt the wait from another
        thread). Drains any pending wake-up byte. Returns True iff a real
        message is available on the transport socket."""
        assert self.type == ClientType.RECEIVER, "Cannot wait for a message on a sender socket."
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(wake_socket, zmq.POLLIN)
        events = dict(poller.poll(timeout))
        if wake_socket in events:
            try:
                while True:
                    wake_socket.recv(zmq.NOBLOCK)
            except zmq.Again:
                pass
        return self.socket in events

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

        # Test send and wait_for_message
        sender.send("Hello, ZMQ!")
        receiver.wait_for_message()  # ZMQ wait_for_message() just waits, doesn't return
        msg = receiver.receive()  # Need to call receive() to get the message
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
        receiver.wait_for_message()
        msg = receiver.receive()
        print(f"Received large message: {len(msg)} bytes")

        receiver.close()
        sender.close()

    run_test()
