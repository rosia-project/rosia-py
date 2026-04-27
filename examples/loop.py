import pytest

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown


@Node
class Counter:
    counter_in = InputPort[int]()
    counter_out = OutputPort[int]()

    def __init__(self):
        self.expected = 0

    def start(self):
        print("Starting")
        self.counter_out(0)

    @reaction([counter_in])
    def increment(self):
        print(f"received {self.counter_in}")
        assert self.counter_in == self.expected, f"Expected {self.expected} but got {self.counter_in}"
        self.expected += 1
        if self.counter_in >= 4:
            request_shutdown()
            return
        self.counter_out(self.counter_in + 1)


@pytest.mark.timeout(30)
def test_loop_logical():
    app = Application()
    counter = app.create_node(Counter())
    counter.counter_out.connect(counter.counter_in, delay=1)
    app.diagram(save_to="loop.png")
    app.execute(trace=True)


if __name__ == "__main__":
    test_loop_logical()
