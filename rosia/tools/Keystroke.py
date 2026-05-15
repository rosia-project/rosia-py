"""Single-keystroke stdin reader as a Rosia node.

`Keystroke` spawns a daemon thread that puts the terminal into cbreak
mode (one byte at a time, no Enter required) and emits each keypress on
its ``key`` output port via a ``@trigger`` physical action. Each emitted
message is stamped at the wall-clock time of the keypress.

The node reads file descriptor 0 directly with ``os.read`` rather than
``sys.stdin``. Rosia spawns each node in its own subprocess via
``multiprocessing`` 's "spawn" context, which rebinds ``sys.stdin`` to
an internal pipe; fd 0 itself is still inherited from the parent.

POSIX-only (Linux/macOS). When fd 0 is not a TTY (e.g. piped input), the
node falls back to plain byte-by-byte reads with no terminal mode change.
"""

import os
import termios
import threading
import tty

from rosia.frontend import Node, OutputPort, trigger


@Node
class Keystroke:
    key = OutputPort[str]()

    @trigger
    def _on_key(self, ch: str) -> None:
        self.key(ch)

    def start(self) -> None:
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self) -> None:
        fd = 0
        old_settings = termios.tcgetattr(fd) if os.isatty(fd) else None
        try:
            if old_settings is not None:
                tty.setcbreak(fd)
            while True:
                data = os.read(fd, 1)
                if not data:
                    return  # EOF
                self._on_key(data.decode(errors="replace"))
        finally:
            if old_settings is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
