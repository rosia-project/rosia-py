"""Tests for ``rosia.tools.Keystroke``.

Same shape as ``test_input``: subprocess with piped stdin, worker-side
assertions via a Sink node. When stdin is not a TTY (which is the case
under pipe), Keystroke skips cbreak setup and reads raw bytes from
fd 0 one byte at a time.
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
def test_keystroke_chars_are_emitted():
    result = _run("ab")
    assert result.returncode == 0, f"stderr:\n{result.stderr}"


if __name__ == "__main__":
    from rosia import Application, InputPort, Node, reaction, request_shutdown
    from rosia.time import Time
    from rosia.tools import Keystroke

    EXPECTED = ["a", "b"]

    @Node
    class Sink:
        key_in = InputPort[str]()

        def __init__(self):
            self.received = []

        @reaction([key_in])
        def collect(self):
            self.received.append(self.key_in)
            if len(self.received) >= len(EXPECTED):
                request_shutdown(Time(0))

        def shutdown(self):
            assert self.received == EXPECTED, f"received {self.received!r}, expected {EXPECTED!r}"

    app = Application(realtime=False)
    keys = app.create_node(Keystroke())
    sink = app.create_node(Sink())
    keys.key >>= sink.key_in
    app.execute()
