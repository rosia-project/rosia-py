import pytest

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown, log
from rosia.time import Time, s


@Node
class Worker:
    input_int = InputPort[int]()
    output_int = OutputPort[int]()

    @reaction([input_int])
    def forward(self):
        log.info(f"Worker received: {self.input_int}")
        self.output_int(self.input_int)
        if self.input_int == 5:
            request_shutdown(1 * s)


@Node
class Manager:
    input_int = InputPort[int]()
    output_int = OutputPort[int]()

    def __init__(self):
        self.output_int.set_DSTAT(Time(0))

    def start(self):
        log.info("Manager starting")
        self.output_int(0, DSTAT=1 * s)

    @reaction([input_int])
    def forward(self):
        log.info(f"Manager received: {self.input_int}, sending: {self.input_int + 1}")
        yield 1 * s
        self.output_int(self.input_int + 1, DSTAT=1 * s)


@pytest.mark.timeout(30)
def test_loop_logical():
    app = Application()
    worker = app.create_node(Worker())
    manager = app.create_node(Manager())
    worker.output_int >>= manager.input_int
    manager.output_int >>= worker.input_int
    app.execute(trace=True, log_level="DEBUG")


if __name__ == "__main__":
    test_loop_logical()
