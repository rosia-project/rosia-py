"""Test transitive upstream tracking.

A passive relay node (no internal yield) sits between a yielding source and a
downstream receiver. The receiver also has an independent yielding trigger
input. Without transitive upstream tracking, the receiver only knows the relay
as a direct upstream — and the relay reports ENT=forever (no internal yield),
which doesn't constrain the receiver. The receiver can then process the trigger
event before the relay's data has propagated, leading to mismatched values.

With transitive upstream tracking, the receiver's STAT is bounded by the
source's ENT (transitively, through the relay). The receiver waits until the
source has advanced past the trigger time, ensuring the relay has had a chance
to emit at the same logical time.

Topology:
    Source(yield 10ms)  -> Relay -> Receiver.relay_data
    Trigger(yield 10ms) ----------> Receiver.tick
"""

import pytest

from rosia import Application, InputPort, Node, OutputPort, reaction, request_shutdown
from rosia.time import ms


@Node
class Source:
    out = OutputPort[int]()

    def __init__(self) -> None:
        self.count = 0

    def start(self):
        while True:
            yield 10 * ms
            self.out(self.count)
            self.count += 1


@Node
class Relay:
    """Passive relay - no internal yield. Multiplies value by 10."""

    in_data = InputPort[int]()
    out = OutputPort[int]()

    @reaction([in_data])
    def fwd(self):
        self.out(self.in_data * 10)


@Node
class Trigger:
    out = OutputPort[int]()

    def __init__(self) -> None:
        self.count = 0

    def start(self):
        while True:
            yield 10 * ms
            self.out(self.count)
            self.count += 1


@Node
class Receiver:
    relay_data = InputPort[int]()
    tick = InputPort[int]()

    def __init__(self) -> None:
        self.received = 0

    @reaction([tick])
    def on_tick(self):
        expected = self.tick * 10
        assert self.relay_data == expected, f"relay_data={self.relay_data} expected={expected} tick={self.tick}"
        self.received += 1
        if self.received == 3:
            request_shutdown()


@pytest.mark.timeout(15)
def test_transitive_upstream():
    app = Application()
    src = app.create_node(Source())
    relay = app.create_node(Relay())
    trigger = app.create_node(Trigger())
    receiver = app.create_node(Receiver())

    src.out >>= relay.in_data
    relay.out >>= receiver.relay_data
    trigger.out >>= receiver.tick

    app.execute()


if __name__ == "__main__":
    test_transitive_upstream()
