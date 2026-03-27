import pytest
import time

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown
from rosia.time import s


@Node
class IntGenerator:
    output_int = OutputPort[int]()

    def __init__(self):
        self.count = 0

    def start(self):
        while True:
            self.output_int(self.count)
            self.count += 1
            if self.count > 2:
                request_shutdown(0 * s)
                break
            time.sleep(0.01)


@Node
class Printer:
    input_int = InputPort[int]()

    @reaction([input_int])
    def print_message(self):
        pass


@pytest.mark.timeout(30)
def test_shutdown():
    app = Application()
    int_gen = app.create_node(IntGenerator())
    printer = app.create_node(Printer())
    int_gen.output_int >>= printer.input_int
    app.execute()
