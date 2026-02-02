import pytest
import time

from rosia import InputPort, OutputPort, reaction, Node, Coordinator
from rosia import request_shutdown
from rosia.time import s


@Node
class IntGenerator:
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    def start(self):
        for _ in range(3):
            self.output(self.count)
            self.count += 1
            time.sleep(0.01)
        request_shutdown(0 * s)


@Node
class Doubler:
    input_port = InputPort[int]()
    output_port = OutputPort[int]()

    @reaction([input_port])
    def process_input(self):
        input_value = self.input_port
        output_value = input_value * 2
        self.output_port(output_value)


@Node
class Printer:
    input_int = InputPort[int]()

    @reaction([input_int])
    def print_message(self):
        pass


@pytest.mark.timeout(30)
def test_chain():
    coor = Coordinator()
    int_gen = coor.create_node(IntGenerator())
    doubler = coor.create_node(Doubler())
    printer = coor.create_node(Printer())
    int_gen.output >>= doubler.input_port
    doubler.output_port >>= printer.input_int
    coor.execute()
