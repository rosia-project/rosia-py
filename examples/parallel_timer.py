from rosia import InputPort, OutputPort, reaction, Node, Coordinator
from rosia import request_shutdown
from rosia.time import Time, ms, s
from rosia.time.Timer import Timer


@Node
class IntGenerator:
    timer = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @reaction([timer])
    def generate(self):
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
        assert self.input_int1 == self.input_int2, (
            "Input ports should have the same value"
        )
        self.receive_count += 1
        if self.receive_count >= 3:
            request_shutdown(0 * s)


if __name__ == "__main__":
    coor = Coordinator("INFO", diagram=True)
    timer1 = coor.create_node(Timer(interval=1 * ms, offset=0 * s))
    timer2 = coor.create_node(Timer(interval=1 * ms, offset=0 * s))
    int_gen1 = coor.create_node(IntGenerator())
    int_gen2 = coor.create_node(IntGenerator())
    printer = coor.create_node(Printer())
    timer1.output_timer >>= int_gen1.timer
    timer2.output_timer >>= int_gen2.timer
    int_gen1.output >>= printer.input_int1
    int_gen2.output >>= printer.input_int2
    coor.execute()
