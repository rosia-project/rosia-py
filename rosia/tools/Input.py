"""Line-based stdin reader as a Rosia node.

`Input` spawns a daemon thread that reads complete lines from stdin and
emits each one on its ``line`` output port via a ``@trigger`` physical
action. Each emitted message is stamped at the wall-clock time the line
finished arriving.

The node reads file descriptor 0 directly with ``os.read`` rather than
``sys.stdin``. Rosia spawns each node in its own subprocess via
``multiprocessing`` 's "spawn" context, which rebinds ``sys.stdin`` to
an internal pipe; fd 0 itself is still inherited from the parent.
"""

import os
import threading

from rosia.frontend import Node, OutputPort, trigger


@Node
class Input:
    line = OutputPort[str]()

    @trigger
    def _on_line(self, value: str) -> None:
        self.line(value)

    def start(self) -> None:
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self) -> None:
        buf = b""
        while True:
            chunk = os.read(0, 4096)
            if not chunk:
                return  # EOF
            buf += chunk
            while b"\n" in buf:
                line_bytes, buf = buf.split(b"\n", 1)
                self._on_line(line_bytes.decode(errors="replace"))
