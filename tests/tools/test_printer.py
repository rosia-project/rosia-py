"""Tests for ``rosia.tools.Printer``.

Subprocess pattern: a Generator emits known values, a downstream Sink
asserts what Printer's upstream message sequence was. Asserting in the
worker (via Sink's shutdown hook) avoids the stderr-capture race we hit
with ``capfd`` under parallel test load.
"""

import subprocess
import sys
from pathlib import Path

import pytest


def _run() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(Path(__file__))],
        capture_output=True,
        text=True,
        timeout=15,
    )


@pytest.mark.timeout(30)
def test_printer_logs_each_value():
    result = _run()
    assert result.returncode == 0, f"stderr:\n{result.stderr}"
    # Printer's stderr should mention each emitted value with the prefix.
    for i in range(3):
        assert f"v={i}" in result.stderr, f"missing 'v={i}' in:\n{result.stderr}"


if __name__ == "__main__":
    from rosia import Application, InputPort, Node, OutputPort, reaction, request_shutdown
    from rosia.time import Time, s
    from rosia.tools import Printer

    EXPECTED = [0, 1, 2]

    @Node
    class Generator:
        out = OutputPort[int]()

        def start(self):
            for i in EXPECTED:
                self.out(i)
                yield 1 * s

    @Node
    class Sink:
        val = InputPort[int]()

        def __init__(self):
            self.received = []

        @reaction([val])
        def collect(self):
            self.received.append(self.val)
            if len(self.received) >= len(EXPECTED):
                # Concrete delay so the negotiated shutdown timestamp is
                # >= the timestamp of every emitted value (this Sink
                # node's logical_time at the moment of the last received
                # value), avoiding the never-default race in the
                # shutdown negotiation.
                request_shutdown(Time(0))

        def shutdown(self):
            assert self.received == EXPECTED, f"received {self.received!r}, expected {EXPECTED!r}"

    app = Application(realtime=False)
    gen = app.create_node(Generator())
    printer = app.create_node(Printer(prefix="v="))
    sink = app.create_node(Sink())
    gen.out >>= printer.value
    gen.out >>= sink.val
    app.execute()
