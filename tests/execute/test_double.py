import pytest

from rosia.execute import ExecutorController


class NumberDoubler:
    """A simple class that can double numbers."""

    def __init__(self):
        pass

    def double(self, number: int) -> int:
        """Double the given number."""
        return number * 2


@pytest.mark.timeout(30)
def test_double_number_remotely():
    """Test that we can double a number using ExecutorController."""
    controller = ExecutorController(NumberDoubler())
    try:
        assert controller.call("double", 5) == 10
        assert controller.call("double", 0) == 0
        assert controller.call("double", -3) == -6
        assert controller.call("double", 100) == 200
    finally:
        controller.remote_process.terminate()
        controller.remote_process.join()
