import pytest
import time

from rosia import InputPort, OutputPort, reaction, Node, Coordinator
from rosia import request_shutdown, log
from rosia.time import s
import rosia


@Node
class IntGenerator:
    output_int = OutputPort[int]()

    def __init__(self):
        self.count = 0

    def start(self):
        for _ in range(3):
            assert log.name == "IntGenerator_0"
            assert rosia.log.name == "IntGenerator_0"
            assert log == rosia.log
            log.info(f"Sending: {self.count}")
            self.output_int(self.count)
            self.count += 1
            time.sleep(0.01)
        request_shutdown(0 * s)


@Node
class Printer:
    input_int = InputPort[int]()

    @reaction([input_int])
    def print_message(self):
        pass


@pytest.mark.timeout(30)
def test_logger():
    coor = Coordinator()
    int_gen = coor.create_node(IntGenerator())
    printer = coor.create_node(Printer())
    int_gen.output_int >>= printer.input_int
    coor.execute()
