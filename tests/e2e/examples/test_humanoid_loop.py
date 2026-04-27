"""Test that replicates the humanoid example's failure mode locally.

Mirrors humanoid-example/main.py topology and physical timing characteristics
exactly enough to reproduce the multi-input race / double-fire issue:

    MultiOutSource (3 outputs: a, b, c, like joint_state/imu/image)
       ├──▶ Pre1 ──▶┐
       ├──▶ Pre2 ──▶│
       ├──▶ Pre3 ──▶│
       │            ├──▶ Combiner (7 inputs) ──▶ OutputRelay ──▶ MultiOutSource
       ├──▶ Pre4 ──▶│                                           (delay = 1us)
       ├──▶ Pre5 ──▶│
       ├──▶ Pre6 ──▶│
       └──▶ Pre7 ──▶┘

Physical timing matches humanoid-example:
- MultiOutSource.start sleeps to mimic ONNX model loading.
- MultiOutSource.on_command does physical work before yield (mujoco physics).
- Preprocesses do small physical work.
- Combiner does substantial physical work (inference).

Without proper logical-time synchronization the test fails with:
- Combiner.combine: an input is None (multi-input merge race).
- Or "Output port written twice at logical time T" (a reaction firing twice
  at T because events at T arrived in batches).
"""

import time

import numpy as np
import pytest

from rosia import Application, InputPort, Node, OutputPort, reaction, request_shutdown
from rosia.time import ms


@Node
class MultiOutSource:
    """Like MujocoNode."""

    cmd = InputPort[np.ndarray]()

    out_a = OutputPort[np.ndarray]()
    out_b = OutputPort[np.ndarray]()
    out_c = OutputPort[np.ndarray]()

    def __init__(self) -> None:
        self.iterations = 0
        self.dt = 20 * ms

    def start(self):
        # Mimic ONNX model loading delay.
        time.sleep(1.0)
        self.out_a(np.zeros(29, dtype=np.float32))
        self.out_b(np.zeros(7, dtype=np.float32))
        self.out_c(np.zeros((84, 84, 3), dtype=np.uint8))

    @reaction([cmd])
    def on_command(self):
        # Mimic mujoco.mj_step + render: substantial physical work.
        time.sleep(0.01)
        yield self.dt
        time.sleep(0.005)
        self.iterations += 1
        if self.iterations == 30:
            request_shutdown()
            return
        v = float(self.iterations)
        self.out_a(np.full(29, v, dtype=np.float32))
        self.out_b(np.full(7, v, dtype=np.float32))
        self.out_c(np.full((84, 84, 3), int(v) & 0xFF, dtype=np.uint8))


def _make_preprocess(idx: int):
    @Node
    class Preprocess:
        in_data = InputPort[np.ndarray]()
        out = OutputPort[np.ndarray]()

        @reaction([in_data])
        def fwd(self):
            self.out((self.in_data.astype(np.float32) * 0.1 + idx).astype(np.float32))

    return Preprocess


Pre1 = _make_preprocess(1)
Pre2 = _make_preprocess(2)
Pre3 = _make_preprocess(3)
Pre4 = _make_preprocess(4)
Pre5 = _make_preprocess(5)
Pre6 = _make_preprocess(6)
Pre7 = _make_preprocess(7)


@Node
class Combiner:
    """Like InferenceNode: 7 inputs."""

    in_1 = InputPort[np.ndarray]()
    in_2 = InputPort[np.ndarray]()
    in_3 = InputPort[np.ndarray]()
    in_4 = InputPort[np.ndarray]()
    in_5 = InputPort[np.ndarray]()
    in_6 = InputPort[np.ndarray]()
    in_7 = InputPort[np.ndarray]()

    out = OutputPort[np.ndarray]()

    @reaction([in_1, in_2, in_3, in_4, in_5, in_6, in_7])
    def combine(self):
        # Mimic ONNX inference latency.
        time.sleep(0.02)
        for i, v in enumerate(
            [self.in_1, self.in_2, self.in_3, self.in_4, self.in_5, self.in_6, self.in_7],
            start=1,
        ):
            assert v is not None, f"in_{i} is None"
        self.out(np.array([1.0], dtype=np.float32))


@Node
class OutputRelay:
    in_data = InputPort[np.ndarray]()
    cmd = OutputPort[np.ndarray]()

    @reaction([in_data])
    def fwd(self):
        self.cmd(self.in_data)


@pytest.mark.timeout(60)
def test_humanoid_loop():
    app = Application()
    src = app.create_node(MultiOutSource())
    p1 = app.create_node(Pre1())
    p2 = app.create_node(Pre2())
    p3 = app.create_node(Pre3())
    p4 = app.create_node(Pre4())
    p5 = app.create_node(Pre5())
    p6 = app.create_node(Pre6())
    p7 = app.create_node(Pre7())
    combiner = app.create_node(Combiner())
    out_relay = app.create_node(OutputRelay())

    src.out_a >>= p1.in_data
    src.out_a >>= p2.in_data
    src.out_a >>= p3.in_data
    src.out_b >>= p4.in_data
    src.out_b >>= p5.in_data
    src.out_b >>= p6.in_data
    src.out_c >>= p7.in_data

    p1.out >>= combiner.in_1
    p2.out >>= combiner.in_2
    p3.out >>= combiner.in_3
    p4.out >>= combiner.in_4
    p5.out >>= combiner.in_5
    p6.out >>= combiner.in_6
    p7.out >>= combiner.in_7

    combiner.out >>= out_relay.in_data
    out_relay.cmd.connect(src.cmd, delay=1)  # 1-microstep loop closure

    app.execute()


if __name__ == "__main__":
    test_humanoid_loop()
