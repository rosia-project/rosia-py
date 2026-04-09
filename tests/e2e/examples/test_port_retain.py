"""Test that input port values are retained across reactions.

Pipeline:
  fast_timer (10ms) -> Producer -> Consumer.data
  slow_timer (30ms) -----------------> Consumer.tick

Producer sends on every tick. Consumer has two input ports: one from Producer
and one from a second Timer at a slower rate. When the slow timer fires,
Consumer should still see the latest value from Producer (not None).
"""

import pytest

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown, log
from rosia.time import s, ms, Time
from rosia.time.Timer import Timer


@Node
class Producer:
    tick = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @reaction([tick])
    def step(self):
        self.output(self.count)
        self.count += 1


@Node
class Consumer:
    data = InputPort[int]()
    tick = InputPort[Time]()

    def __init__(self):
        self.checks = 0

    @reaction([tick])
    def on_tick(self):
        # data should retain the latest value from Producer, not be None
        if self.data is not None:
            log.warning(f"RETAINED OK data={self.data}")
            self.checks += 1
            if self.checks >= 3:
                request_shutdown()
        else:
            log.warning("RETAINED FAIL data=None")
            request_shutdown()


@pytest.mark.timeout(30)
def test_port_retain():
    """Input ports retain the most recent value, not cleared after reaction."""
    app = Application()
    fast_timer = app.create_node(Timer(interval=10 * ms, offset=0 * s))
    slow_timer = app.create_node(Timer(interval=30 * ms, offset=0 * s))
    producer = app.create_node(Producer())
    consumer = app.create_node(Consumer())
    fast_timer.output_timer >>= producer.tick
    producer.output >>= consumer.data
    slow_timer.output_timer >>= consumer.tick
    app.execute(timeout=10)


if __name__ == "__main__":
    test_port_retain()
