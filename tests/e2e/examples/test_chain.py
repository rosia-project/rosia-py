import pytest

from rosia import InputPort, OutputPort, reaction, Node, Application
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
            yield 1 * s
        request_shutdown()


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
    app = Application()
    int_gen = app.create_node(IntGenerator())
    doubler = app.create_node(Doubler())
    printer = app.create_node(Printer())
    int_gen.output >>= doubler.input_port
    doubler.output_port >>= printer.input_int
    app.execute()


if __name__ == "__main__":
    test_chain()
