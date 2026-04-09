"""Feedback loop example.

Pipeline:
  Worker <-> Manager

Worker sends 0 to Manager. Manager increments it and sends back.
Worker forwards the value back to Manager. This continues until
the value reaches 5, at which point Worker requests shutdown.

Demonstrates bidirectional connections forming a feedback loop.
"""

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown, log


@Node
class Worker:
    input_int = InputPort[int]()
    output_int = OutputPort[int]()

    def start(self):
        self.output_int(0)

    @reaction([input_int])
    def forward(self):
        log.info(f"Worker received: {self.input_int}")
        self.output_int(self.input_int)
        if self.input_int == 5:
            request_shutdown()


@Node
class Manager:
    input_int = InputPort[int]()
    output_int = OutputPort[int]()

    @reaction([input_int])
    def forward(self):
        log.info(f"Manager received: {self.input_int}, sending: {self.input_int + 1}")
        self.output_int(self.input_int + 1)


if __name__ == "__main__":
    app = Application()
    worker = app.create_node(Worker())
    manager = app.create_node(Manager())
    worker.output_int >>= manager.input_int
    manager.output_int >>= worker.input_int
    app.execute()
