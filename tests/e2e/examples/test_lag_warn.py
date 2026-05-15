import pytest

from rosia import Node, Application, request_shutdown
from rosia.time import Time, s


@Node
class FastYielder:
    """Yields in tight succession so logical time races far ahead of
    physical time. With realtime=False (no gating) and ``lag_warn=Time(0)``,
    every advancement should trigger the lag warning."""

    def __init__(self):
        self.iterations = 3

    def start(self):
        for _ in range(self.iterations):
            yield 1 * s
        request_shutdown()


@pytest.mark.timeout(30)
def test_lag_warn_emitted(capfd):
    app = Application(realtime=False)
    app.create_node(FastYielder(), lag_warn=Time(0))
    app.execute()
    _, err = capfd.readouterr()
    assert "Lag" in err and "exceeds lag_warn" in err, f"expected lag warning in stderr, got:\n{err}"


if __name__ == "__main__":
    app = Application(realtime=False)
    app.create_node(FastYielder(), lag_warn=Time(0))
    app.execute()
