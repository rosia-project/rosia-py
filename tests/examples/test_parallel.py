import pytest

from rosia import InputPort, OutputPort, reaction, Node, Coordinator
from rosia import request_shutdown
from rosia.time import s


@Node
class IntGenerator:
    output = OutputPort[int]()

    def __init__(self):
        self.count = 1

    @reaction([])
    def start(self):
        while self.count <= 100:
            print(f"IntGenerator {self.count} starting")
            self.output(self.count)
            self.count += 1


@Node
class Printer:
    input_int1 = InputPort[int]()
    input_int2 = InputPort[int]()

    def __init__(self):
        self.receive_count = 0

    @reaction([input_int1, input_int2])
    def print_message(self):
        print(f"Printer received messages: {self.input_int1} {self.input_int2}")
        assert self.input_int1 == self.input_int2
        self.receive_count += 1
        if self.receive_count >= 100:
            request_shutdown(0 * s)


@pytest.mark.skip
def test_parallel():
    coor = Coordinator("DEBUG")
    int_gen1 = coor.create_node(IntGenerator())
    int_gen2 = coor.create_node(IntGenerator())
    printer = coor.create_node(Printer())
    int_gen1.output >>= printer.input_int1
    int_gen2.output >>= printer.input_int2
    for i in range(10):
        coor.execute()


if __name__ == "__main__":
    test_parallel()
