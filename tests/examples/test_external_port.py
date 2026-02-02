import pytest

from rosia import InputPort, reaction, Node, Coordinator


@Node
class Printer:
    input_str = InputPort[str]()

    @reaction([input_str])
    def print_message(self):
        pass


@pytest.mark.skip(reason="Coordinator.execute() blocks; set_value requires threading")
def test_external_port():
    coor = Coordinator()
    coor.create_node(Printer())
    coor.execute()
