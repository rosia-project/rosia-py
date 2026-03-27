"""Script for timed shutdown test.

Pipeline:
  Timer -> Producer1 -> Sink1
        -> Producer2 (slow) -> Sink2

Producer1 requests shutdown after 10 ticks.
Producer2 is slow (sleeps per tick).
All nodes log their progress so the test can verify completion.
"""

import time
import random

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown, log
from rosia.time import s, ms, Time
from rosia.time.Timer import Timer


@Node
class Producer:
    tick = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self, name: str, max_ticks: int = 10, slow: bool = False):
        self.name = name
        self.count = 0
        self.max_ticks = max_ticks
        self.slow = slow

    @reaction([tick])
    def step(self):
        if self.slow:
            time.sleep(random.uniform(0.0, 0.01))
        log.warning(f"{self.name} step {self.count}")
        self.output(self.count)
        self.count += 1
        if self.count >= self.max_ticks and not self.slow:
            request_shutdown(0 * s)


@Node
class Sink:
    input_port = InputPort[int]()

    def __init__(self, name: str):
        self.name = name

    @reaction([input_port])
    def on_input(self):
        log.warning(f"{self.name} got {self.input_port}")


if __name__ == "__main__":
    app = Application()
    timer = app.create_node(Timer(interval=10 * ms, offset=0 * s))
    producer1 = app.create_node(Producer(name="P1", max_ticks=10))
    producer2 = app.create_node(Producer(name="P2", max_ticks=10, slow=True))
    sink1 = app.create_node(Sink(name="S1"))
    sink2 = app.create_node(Sink(name="S2"))
    timer.output_timer >>= producer1.tick
    timer.output_timer >>= producer2.tick
    producer1.output >>= sink1.input_port
    producer2.output >>= sink2.input_port
    app.execute(timeout=10)
