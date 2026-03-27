import pytest

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown
from rosia.time import s
from rosia import log
import time


@Node
class IntGenerator:
    output = OutputPort[int]()

    def __init__(self):
        self.count = 1

    def start(self):
        while self.count <= 100:
            self.output(self.count)
            time.sleep(0.01)
            self.count += 1
        request_shutdown(1 * s)


@Node
class Printer:
    input_int1 = InputPort[int]()
    input_int2 = InputPort[int]()

    def __init__(self):
        self.receive_count = 0

    @reaction([input_int1, input_int2])
    def print_message(self):
        log.info(f"Printer received messages: {self.input_int1} {self.input_int2}")
        assert self.input_int1 == self.input_int2
        self.receive_count += 1


@pytest.mark.xfail(raises=SystemExit, strict=True)
@pytest.mark.timeout(30)
def test_parallel():
    app = Application()
    int_gen1 = app.create_node(IntGenerator())
    int_gen2 = app.create_node(IntGenerator())
    printer = app.create_node(Printer())
    int_gen1.output >>= printer.input_int1
    int_gen2.output >>= printer.input_int2

    app.execute()


if __name__ == "__main__":
    test_parallel()
