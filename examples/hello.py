from rosia import InputPort, OutputPort, reaction, Node, Coordinator
from rosia import log


@Node
class Greeter:
    output = OutputPort[str]()

    def start(self):
        self.output("Hello, World!")


@Node
class Printer:
    message = InputPort[str]()

    @reaction([message])
    def print_message(self):
        log.info(self.message)


if __name__ == "__main__":
    coor = Coordinator()
    greeter = coor.create_node(Greeter())
    printer = coor.create_node(Printer())
    greeter.output >>= printer.message
    coor.execute()
