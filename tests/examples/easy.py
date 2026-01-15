from rosia import InputPort, OutputPort, reaction, Node, Coordinator
import time


@Node
class IntGenerator:
    output_int = OutputPort[int]()

    def __init__(self):
        self.count = 0

    def start(self):
        while True:
            print("Sending:", self.count)
            self.output_int(self.count)
            self.count += 1
            time.sleep(1)


@Node
class Printer:
    input_int = InputPort[int]()

    @reaction([input_int])
    def print_message(self):
        print(f"Received: {self.input_int}")


if __name__ == "__main__":
    coor = Coordinator()
    int_gen = coor.create_node(IntGenerator())
    printer = coor.create_node(Printer())
    int_gen.output_int >>= printer.input_int

    coor.execute()
