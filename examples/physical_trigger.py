"""Example: a physical action driven by a sensor thread.

`SensorReader` exposes a `@trigger` method `on_sample`. A daemon thread
started in `start()` periodically calls `self.on_sample(value)`, which
schedules the decorated body as a reaction at logical time equal to the
wall-clock elapsed since application start. The reaction emits the value
on an output port consumed by a regular logical reaction in `Printer`.
"""

import threading
import time

from rosia import InputPort, Node, OutputPort, Application, reaction, trigger, log
from rosia import request_shutdown
import rosia


@Node
class SensorReader:
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @trigger
    def on_sample(self, value):
        self.count += 1
        self.output(value)
        log.info(f"trigger fired with value={value}")
        log.info(f"logical time: {rosia.logical_time()}")
        if self.count >= 5:
            request_shutdown()

    def start(self):
        threading.Thread(target=self._poll, daemon=True).start()

    def _poll(self):
        for i in range(5):
            time.sleep(0.2)
            self.on_sample(i)


@Node
class Printer:
    input_int = InputPort[int]()

    @reaction([input_int])
    def print_value(self):
        log.info(f"Printer received: {self.input_int}")


if __name__ == "__main__":
    app = Application()
    sensor = app.create_node(SensorReader())
    printer = app.create_node(Printer())
    sensor.output >>= printer.input_int
    app.execute()
