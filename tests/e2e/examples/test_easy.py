import pytest

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown
from rosia.time import s


@Node
class IntGenerator:
    output_int = OutputPort[int]()

    def __init__(self):
        self.count = 0

    def start(self):
        for _ in range(3):
            self.output_int(self.count)
            yield 1 * s
            self.count += 1
            # time.sleep(0.01)
        request_shutdown()


@Node
class Printer:
    input_int = InputPort[int]()

    def __init__(self):
        self.received = []

    @reaction([input_int])
    def print_message(self):
        self.received.append(self.input_int)


@pytest.mark.timeout(30)
def test_easy():
    app = Application()
    int_gen = app.create_node(IntGenerator())
    printer = app.create_node(Printer())
    int_gen.output_int >>= printer.input_int
    app.execute()


if __name__ == "__main__":
    test_easy()
