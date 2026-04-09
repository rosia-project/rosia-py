from rosia import InputPort, OutputPort, reaction, Node, Application, request_shutdown, log
from rosia.time import Timer, Time, s


@Node
class IntGenerator:
    tick = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @reaction([tick])
    def generate(self):
        log.info(f"tick: {self.tick}")
        self.count += 1
        self.output(self.count)
        if self.count >= 5:
            request_shutdown(1 * s)


@Node
class Printer:
    input_port = InputPort[int]()

    @reaction([input_port])
    def print_value(self):
        log.info(f"Result: {self.input_port}")


if __name__ == "__main__":
    app = Application()
    timer = app.create_node(Timer(interval=1 * s, offset=0 * s))
    gen = app.create_node(IntGenerator())
    printer = app.create_node(Printer())
    timer.output_timer >>= gen.tick
    gen.output >>= printer.input_port
    app.diagram(save_to="timer_diagram.png")
    app.execute(trace=True)
