"""Test: advance_time in a reaction must not affect the logical time of
subsequent reactions triggered by the same event.

When two input ports receive messages at the same logical timestamp, they
are merged into a single InputPortEvent. All triggered reactions should
observe logical_time == event.timestamp. If one reaction calls
advance_time(), the others must still see the original timestamp.
"""

import pytest

import rosia
from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown, log
from rosia.time import ms, Time


@Node
class SourceA:
    out = OutputPort[int]()

    def __init__(self):
        self.out.set_STAT(Time(0))

    def start(self):
        t = Time(0)
        dt = 200 * ms
        self.out(1, STAT=t + dt)


@Node
class SourceB:
    out = OutputPort[int]()

    def __init__(self):
        self.out.set_STAT(Time(0))

    def start(self):
        t = Time(0)
        dt = 200 * ms
        self.out(2, STAT=t + dt)


@Node
class Receiver:
    port_a = InputPort[int]()
    port_b = InputPort[int]()

    def __init__(self):
        self.react_a_time_ok = False
        self.react_b_time_ok = False
        self.time_wrong = False

    @reaction([port_a])
    def react_a(self):
        t = rosia.node_runtime_instance.logical_time
        log.warning(f"REACT_A fired: port_a={self.port_a} at logical_time={t}")
        if t == Time(0):
            self.react_a_time_ok = True
            log.warning("REACT_A_TIME_OK")
        else:
            self.time_wrong = True
            log.warning(f"REACT_A_TIME_WRONG expected=0 got={t}")

    @reaction([port_b])
    def react_b(self):
        t = rosia.node_runtime_instance.logical_time
        log.warning(f"REACT_B fired: port_b={self.port_b} at logical_time={t}")
        if t == Time(0):
            self.react_b_time_ok = True
            log.warning("REACT_B_TIME_OK")
        else:
            self.time_wrong = True
            log.warning(f"REACT_B_TIME_WRONG expected=0 got={t}")
        # yield advances time — all remaining T=0 reactions
        # must fire BEFORE time advances past T=0
        yield 100 * ms
        log.warning(f"REACT_B yield returned, logical_time={rosia.node_runtime_instance.logical_time}")
        request_shutdown()


def run(trace: bool = False):
    app = Application()
    source_a = app.create_node(SourceA())
    source_b = app.create_node(SourceB())
    receiver = app.create_node(Receiver())
    source_a.out >>= receiver.port_a
    source_b.out >>= receiver.port_b
    app.execute(timeout=15, trace=trace)


@pytest.mark.timeout(30)
def test_advance_time_same_timestamp_reactions():
    """Reactions at the same timestamp must all see the correct logical time,
    even if one of them calls advance_time()."""
    run()


if __name__ == "__main__":
    run(trace=True)
