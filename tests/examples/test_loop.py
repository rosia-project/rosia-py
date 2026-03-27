import pytest
import time

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown
from rosia.time import s


@Node
class Worker:
    input_int = InputPort[int]()
    output_int = OutputPort[int]()

    def start(self):
        self.output_int(0)

    @reaction([input_int])
    def forward(self):
        self.output_int(self.input_int)
        if self.input_int >= 3:
            request_shutdown(0 * s)
        time.sleep(0.01)


@Node
class Manager:
    input_int = InputPort[int]()
    output_int = OutputPort[int]()

    @reaction([input_int])
    def forward(self):
        self.output_int(self.input_int + 1)


@pytest.mark.timeout(30)
def test_loop():
    app = Application()
    worker = app.create_node(Worker())
    manager = app.create_node(Manager())
    worker.output_int >>= manager.input_int
    manager.output_int >>= worker.input_int
    app.execute()
