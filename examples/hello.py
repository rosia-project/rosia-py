from rosia import InputPort, OutputPort, reaction, Node, Application
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
    app = Application()
    greeter = app.create_node(Greeter())
    printer = app.create_node(Printer())
    greeter.output >>= printer.message
    app.diagram(save_to="hello_diagram.png")
    app.execute()
