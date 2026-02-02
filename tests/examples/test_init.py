import pytest
import time

from rosia import InputPort, OutputPort, reaction, Node, Coordinator
from rosia import request_shutdown
from rosia.time import s


@Node
class StringGenerator:
    output_str = OutputPort[str]()

    def __init__(self, multiplier: int):
        self.multiplier = multiplier
        self.count = 0

    def start(self):
        for _ in range(3):
            string = f"Hello, ROSIA! {self.count * self.multiplier}"
            self.output_str(string)
            self.count += 1
            time.sleep(0.01)
        request_shutdown(0 * s)


@Node
class Printer:
    input_str = InputPort[str]()

    @reaction([input_str])
    def print_message(self):
        pass


@pytest.mark.timeout(30)
def test_init():
    coor = Coordinator()
    str_gen = coor.create_node(StringGenerator(multiplier=2))
    printer = coor.create_node(Printer())
    str_gen.output_str >>= printer.input_str
    coor.execute()
