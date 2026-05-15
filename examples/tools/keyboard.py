"""Example: a keyboard reader feeding a printer.

Wires `Keystroke` (single-key reader) to `Printer`, both from
``rosia.tools``. Press Ctrl-C to quit.

Run with:
    python examples/tools/keyboard.py

Requires a POSIX terminal (Linux/macOS).
"""

from rosia import Application
from rosia.tools import Keystroke, Printer


if __name__ == "__main__":
    app = Application()
    keys = app.create_node(Keystroke())
    printer = app.create_node(Printer(prefix="key: "))
    keys.key >>= printer.value
    app.execute()
