"""Example: a line-based stdin reader feeding a printer.

Wires `Input` (line-based stdin reader) to `Printer`, both from
``rosia.tools``. Press Ctrl-C to quit.

Run with:
    python examples/tools/input.py
"""

from rosia import Application
from rosia.tools import Input, Printer


if __name__ == "__main__":
    app = Application()
    reader = app.create_node(Input())
    printer = app.create_node(Printer(prefix="line: "))
    reader.line >>= printer.value
    app.execute()
