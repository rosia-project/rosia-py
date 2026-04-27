"""Test a feedback loop where the driver has a big yield (1s) and the loop is
closed with a small delay (1 microstep).

Topology (closed loop):
    Driver -> Relay1 -> Relay2 -> Driver  (loop closure delay = 1 microstep)

Driver yields 1s in its reaction. Without transitive upstream tracking, the
STAT propagating around the loop would advance by only 1 microstep per cycle
round, so reaching the driver's 1s yield would require ~1 billion round trips
through the loop — the test would time out.

With transitive upstream tracking that excludes self from the cycle, Driver's
STAT is bounded by the relays' ENT (which is `forever` for empty queues),
allowing Driver to advance to its scheduled reaction directly without chasing
microsteps around the loop.
"""

import pytest

from rosia import Application, InputPort, Node, OutputPort, reaction, request_shutdown
from rosia.time import s


@Node
class Driver:
    """Drives the loop with a 1s logical yield per iteration."""

    in_data = InputPort[int]()
    out = OutputPort[int]()

    def __init__(self) -> None:
        self.iterations = 0

    def start(self):
        self.out(0)

    @reaction([in_data])
    def step(self):
        yield 1 * s
        self.iterations += 1
        if self.iterations == 3:
            request_shutdown()
            return
        self.out(self.in_data + 1)


@Node
class Relay:
    """Pure passive relay (no internal yield)."""

    in_data = InputPort[int]()
    out = OutputPort[int]()

    @reaction([in_data])
    def fwd(self):
        self.out(self.in_data)


@pytest.mark.timeout(15)
def test_loop_big_yield_small_delay():
    app = Application()
    driver = app.create_node(Driver())
    relay1 = app.create_node(Relay())
    relay2 = app.create_node(Relay())

    driver.out >>= relay1.in_data
    relay1.out >>= relay2.in_data
    relay2.out.connect(driver.in_data, delay=1)  # 1-microstep loop closure

    app.execute()


if __name__ == "__main__":
    test_loop_big_yield_small_delay()
