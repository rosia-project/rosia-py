import threading
import time

import pytest

from rosia import InputPort, Node, OutputPort, Application, reaction, trigger
from rosia import request_shutdown


@Node
class SensorReader:
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0
        self.expected_total = 5

    @trigger
    def on_sample(self, value):
        assert value == self.count, f"out-of-order trigger: expected {self.count}, got {value}"
        self.count += 1
        self.output(value)
        if self.count >= self.expected_total:
            request_shutdown()

    def start(self):
        threading.Thread(target=self._poll, daemon=True).start()

    def _poll(self):
        for i in range(5):
            time.sleep(0.05)
            self.on_sample(i)


@Node
class Printer:
    input_int = InputPort[int]()

    def __init__(self):
        self.received = []
        self.expected_total = 5

    @reaction([input_int])
    def collect(self):
        self.received.append(self.input_int)

    def shutdown(self):
        assert self.received == list(range(self.expected_total)), f"received unexpected sequence: {self.received}"


@pytest.mark.timeout(30)
def test_trigger_physical():
    app = Application()
    sensor = app.create_node(SensorReader())
    printer = app.create_node(Printer())
    sensor.output >>= printer.input_int
    app.execute()


if __name__ == "__main__":
    test_trigger_physical()
