"""Generic logger node.

`Printer` logs every value it receives on its ``value`` input port at
``INFO`` level. Useful for quick wiring tests and as a sink in examples.
"""

from typing import Any

from rosia.frontend import InputPort, Node, reaction
import rosia


@Node
class Printer:
    value = InputPort[Any]()

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix

    @reaction([value])
    def _on_value(self) -> None:
        rosia.log.info(f"{self.prefix}{self.value!r}")
