import pytest

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown
from rosia.time import Time, s
from rosia.time.Timer import Timer


@Node
class IntGenerator:
    input_port = InputPort[Time]()
    output_port = OutputPort[Time]()

    def __init__(self):
        self.number = 0

    @reaction([input_port])
    def process_input(self):
        self.output_port(self.input_port)
        self.number += 1


@Node
class Printer:
    input_timer = InputPort[Time]()

    def __init__(self):
        self.receive_count = 0

    @reaction([input_timer])
    def print_message(self):
        self.receive_count += 1
        if self.receive_count >= 3:
            request_shutdown()


@pytest.mark.timeout(30)
def test_timer_chain():
    app = Application()
    timer_node = app.create_node(Timer(interval=1 * s, offset=0 * s))
    int_generator = app.create_node(IntGenerator())
    printer = app.create_node(Printer())
    timer_node.output_timer >>= int_generator.input_port
    int_generator.output_port >>= printer.input_timer
    app.execute(timeout=10)


if __name__ == "__main__":
    test_timer_chain()
