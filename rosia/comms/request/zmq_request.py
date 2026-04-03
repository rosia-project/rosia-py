from typing import Any, Callable, Type

import zmq

from rosia.comms.Types import ClientType
from rosia.comms.serializers.base import SerializerBase

from .base import ClientBase, ServerBase


class ZMQClient(ClientBase):
    def __init__(
        self,
        type: ClientType,
        serializer: Type[SerializerBase],
        endpoint: str,
    ):
        self.type = type
        self.serializer = serializer(type)
        context = zmq.Context.instance()
        self.socket = context.socket(zmq.REQ)
        self.socket.connect(endpoint)
        self.endpoint = endpoint

    async def request(self, msg: Any):
        self.socket.send(self.serializer.serialize(msg))
        reply = self.socket.recv()
        return self.serializer.deserialize(reply)

    def close(self):
        self.socket.close()


class ZMQServer(ServerBase):
    def __init__(
        self,
        type: ClientType,
        serializer: Type[SerializerBase],
    ):
        self.type = type
        self.serializer = serializer(type)
        context = zmq.Context.instance()
        self.socket = context.socket(zmq.REP)
        port = self.socket.bind_to_random_port("tcp://127.0.0.1")
        self.endpoint = f"tcp://127.0.0.1:{port}"
        self._running = False

    def register_callback(self, callback: Callable[[Any], Any]):
        assert not self._running, "Server is already running"
        self._running = True
        while self._running:
            msg = self.socket.recv()
            result = callback(self.serializer.deserialize(msg))
            self.socket.send(self.serializer.serialize(result))

    def close(self):
        self._running = False
        self.socket.close()


if __name__ == "__main__":
    import threading
    from rosia.comms.serializers.pickle import Serializer
    import asyncio

    def run_test():
        server = ZMQServer(ClientType.RECEIVER, Serializer)
        print(f"Server bound to: {server.endpoint}")

        client = ZMQClient(ClientType.SENDER, Serializer, server.endpoint)

        def echo(msg):
            print(f"Server received: {msg}")
            return f"echo: {msg}"

        server_thread = threading.Thread(target=server.register_callback, args=(echo,))
        server_thread.start()

        reply = asyncio.run(client.request("Hello, ZMQ!"))
        print(f"Client received reply: {reply}")

        reply = asyncio.run(client.request("Second message"))
        print(f"Client received reply: {reply}")

        client.close()
        server.close()
        server_thread.join(timeout=1)

    run_test()
