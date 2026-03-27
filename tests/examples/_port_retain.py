"""Script for port retain test.

Pipeline:
  fast_timer (10ms) -> Producer -> Consumer.data
  slow_timer (30ms) -----------------> Consumer.tick

Producer sends an incrementing count on every fast tick.
Consumer reacts to slow_timer ticks and reads both its inputs.
When the slow timer fires, Consumer.data should still hold the latest
value from Producer (not None), since port values are retained.
"""

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
                request_shutdown(0 * s)
        else:
            log.warning("RETAINED FAIL data=None")
            request_shutdown(0 * s)


if __name__ == "__main__":
    app = Application()
    fast_timer = app.create_node(Timer(interval=10 * ms, offset=0 * s))
    slow_timer = app.create_node(Timer(interval=30 * ms, offset=0 * s))
    producer = app.create_node(Producer())
    consumer = app.create_node(Consumer())
    fast_timer.output_timer >>= producer.tick
    producer.output >>= consumer.data
    slow_timer.output_timer >>= consumer.tick
    app.execute(timeout=10)
