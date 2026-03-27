from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown
from rosia.time import s
from rosia import log


from rosia.time import Timer, Time


@Node
class IntGenerator:
    input_port = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @reaction([input_port])
    def generate(self):
        self.count += 1
        self.output(self.count)
        if self.count >= 5:
            request_shutdown(0 * s)


@Node
class Doubler:
    input_port = InputPort[int]()
    output_port = OutputPort[int]()

    @reaction([input_port])
    def process_input(self):
        log.info(f"Doubling value: {self.input_port}")
        input_value = self.input_port
        output_value = input_value * 2
        self.output_port(output_value)


@Node
class Printer:
    input_int = InputPort[int]()

    @reaction([input_int])
    def print_message(self):
        log.info(f"Printing value: {self.input_int}")


if __name__ == "__main__":
    app = Application()
    timer = app.create_node(Timer(interval=1 * s, offset=0 * s))
    int_gen = app.create_node(IntGenerator())
    doubler = app.create_node(Doubler())
    printer = app.create_node(Printer())
    timer.output_timer >>= int_gen.input_port
    int_gen.output >>= doubler.input_port
    doubler.output_port >>= printer.input_int
    app.diagram()
    app.execute(trace=True)
