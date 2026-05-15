import time

import pytest

from rosia import Node, Application
from rosia import request_shutdown
from rosia.time import Time, ms
from rosia.time.utils import get_physical_time
import rosia


@Node
class RealtimeYielder:
    def __init__(self):
        self.iterations = 5
        self.step = 100 * ms

    def start(self, start_logical_time: Time):
        for _ in range(self.iterations):
            yield self.step
            elapsed = get_physical_time() - start_logical_time
            assert elapsed.value >= rosia.logical_time().value, (
                f"realtime violated: elapsed={elapsed}, logical={rosia.logical_time()}"
            )
        request_shutdown()


@pytest.mark.timeout(30)
def test_realtime_gating():
    app = Application()
    app.create_node(RealtimeYielder(), realtime=True)
    t0 = time.monotonic()
    app.execute()
    elapsed = time.monotonic() - t0
    # 5 yields of 100 ms must take at least 500 ms of wall-clock time when
    # realtime=True; allow a generous slack to absorb startup/shutdown
    # negotiation. Without realtime gating, this completes in < 100 ms.
    assert elapsed >= 0.45, f"realtime mode finished too fast: {elapsed:.3f}s"


if __name__ == "__main__":
    test_realtime_gating()
