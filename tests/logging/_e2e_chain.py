from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown, log
from rosia.time import s, Timer, Time


@Node
class Source:
    input_port = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @reaction([input_port])
    def generate(self):
        log.warning(f"sending {self.count}")
        self.output(self.count)
        self.count += 1
        if self.count >= 3:
            request_shutdown(0 * s)


@Node
class Sink:
    input_port = InputPort[int]()

    @reaction([input_port])
    def on_input(self):
        log.warning(f"got {self.input_port}")


if __name__ == "__main__":
    app = Application()
    timer = app.create_node(Timer(interval=1 * s, offset=0 * s))
    src = app.create_node(Source())
    sink = app.create_node(Sink())
    timer.output_timer >>= src.input_port
    src.output >>= sink.input_port
    app.execute(timeout=10)
