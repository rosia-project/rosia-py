"""End-to-end logging tests.

Pipeline:
  Timer -> Source -> Sink

Source sends 3 values, then requests shutdown.
Verifies that node logs appear with correct prefixes.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown, log
from rosia.time import s, Time
from rosia.time.Timer import Timer


@Node
class Source:
    input_port = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @reaction([input_port])
    def generate(self):
        log.warning(f"sending {self.count}")
        self.output(self.count)
        self.count += 1
        if self.count >= 3:
            request_shutdown()


@Node
class Sink:
    input_port = InputPort[int]()

    @reaction([input_port])
    def on_input(self):
        log.warning(f"got {self.input_port}")


def _run_as_subprocess() -> subprocess.CompletedProcess[str]:
    """Run this file as a subprocess to capture stderr from child processes."""
    return subprocess.run(
        [sys.executable, str(Path(__file__))],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[2]),
        timeout=20,
    )


@pytest.mark.timeout(30)
def test_logger_output_in_subprocess():
    """Logger output appears from nodes running in child processes."""
    result = _run_as_subprocess()
    assert result.returncode == 0
    assert "[Source_1] sending 0" in result.stderr
    assert "[Source_1] sending 1" in result.stderr
    assert "[Source_1] sending 2" in result.stderr
    assert "[Sink_2] got 0" in result.stderr
    assert "[Sink_2] got 1" in result.stderr
    assert "[Sink_2] got 2" in result.stderr


@pytest.mark.timeout(30)
def test_logger_node_name_prefix():
    """Node logs with its own [name] prefix in subprocess."""
    result = _run_as_subprocess()
    assert result.returncode == 0
    assert "[Source_1]" in result.stderr
    assert "[Sink_2]" in result.stderr


if __name__ == "__main__":
    app = Application()
    timer = app.create_node(Timer(interval=1 * s, offset=0 * s))
    src = app.create_node(Source())
    sink = app.create_node(Sink())
    timer.output_timer >>= src.input_port
    src.output >>= sink.input_port
    app.execute(timeout=10, trace=True)
