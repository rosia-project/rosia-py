"""Tests for ``rosia.tools.Input``.

Run this file as a subprocess with a known stdin payload and assert
inside the worker via a custom Sink node. The subprocess's exit code
carries the assertion result back to the test.
"""

import subprocess
import sys
from pathlib import Path

import pytest


def _run(stdin_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(Path(__file__))],
        capture_output=True,
        text=True,
        timeout=15,
        input=stdin_text,
    )


@pytest.mark.timeout(30)
def test_input_lines_are_emitted():
    result = _run("hello\nworld\n")
    assert result.returncode == 0, f"stderr:\n{result.stderr}"


if __name__ == "__main__":
    from rosia import Application, InputPort, Node, reaction, request_shutdown
    from rosia.time import Time
    from rosia.tools import Input

    EXPECTED = ["hello", "world"]

    @Node
    class Sink:
        line_in = InputPort[str]()

        def __init__(self):
            self.received = []

        @reaction([line_in])
        def collect(self):
            self.received.append(self.line_in)
            if len(self.received) >= len(EXPECTED):
                request_shutdown(Time(0))

        def shutdown(self):
            assert self.received == EXPECTED, f"received {self.received!r}, expected {EXPECTED!r}"

    app = Application(realtime=False)
    reader = app.create_node(Input())
    sink = app.create_node(Sink())
    reader.line >>= sink.line_in
    app.execute()
