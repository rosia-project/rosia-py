"""Script for advance_time same-timestamp reaction test.

Bug: If advance_time is called inside a reaction, subsequent reactions
at the same timestamp must fire BEFORE time advances (logical_time
must be monotonically non-decreasing).

Setup:
  SourceA sends to port_a, SourceB sends to port_b — both at T=0.
  Both messages are merged into one InputPortEvent at T=0.
  react_b calls advance_time(100ms).
  react_a should also fire at logical_time=T=0, BEFORE time advances.

Expected: both reactions fire at logical_time=0, then time advances.
"""

import rosia
from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown, advance_time, log
from rosia.time import s, ms, Time


@Node
class SourceA:
    out = OutputPort[int]()

    def __init__(self):
        self.out.set_DSTAT(Time(0))

    def start(self):
        t = Time(0)
        dt = 200 * ms
        self.out(1, timestamp=t, DSTAT=t + dt)


@Node
class SourceB:
    out = OutputPort[int]()

    def __init__(self):
        self.out.set_DSTAT(Time(0))

    def start(self):
        t = Time(0)
        dt = 200 * ms
        self.out(2, timestamp=t, DSTAT=t + dt)


@Node
class Receiver:
    port_a = InputPort[int]()
    port_b = InputPort[int]()

    def __init__(self):
        pass

    @reaction([port_a])
    def react_a(self):
        t = rosia.node_runtime_instance.logical_time
        log.warning(f"REACT_A fired: port_a={self.port_a} at logical_time={t}")
        if t == Time(0):
            log.warning("REACT_A_TIME_OK")
        else:
            log.warning(f"REACT_A_TIME_WRONG expected=0 got={t}")

    @reaction([port_b])
    def react_b(self):
        t = rosia.node_runtime_instance.logical_time
        log.warning(f"REACT_B fired: port_b={self.port_b} at logical_time={t}")
        if t == Time(0):
            log.warning("REACT_B_TIME_OK")
        else:
            log.warning(f"REACT_B_TIME_WRONG expected=0 got={t}")
        # advance_time is called here — all remaining T=0 reactions
        # must fire BEFORE time advances past T=0
        advance_time(100 * ms)
        log.warning(
            f"REACT_B advance_time returned, logical_time={rosia.node_runtime_instance.logical_time}"
        )
        request_shutdown(0 * s)


if __name__ == "__main__":
    app = Application()
    source_a = app.create_node(SourceA())
    source_b = app.create_node(SourceB())
    receiver = app.create_node(Receiver())
    source_a.out >>= receiver.port_a
    source_b.out >>= receiver.port_b
    app.execute(timeout=15)
