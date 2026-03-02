"""3D bouncing balls on a surface visualized with rerun.

Pipeline:
  Timer -> BallSimulator1 -> Renderer1
        -> BallSimulator2 -> Renderer2

Two balls bounce in parallel with identical trajectories,
driven by the same timer.  Each BallSimulator integrates gravity
and handles elastic bounces off the ground plane (z=0).
Each Renderer logs its ball position to the rerun 3D viewer each tick.

Only uses numpy — no other scientific libraries required.
"""

import random
import time

import numpy as np
import rerun as rr
import rerun.blueprint as rrb

from rosia import InputPort, OutputPort, reaction, Node, Coordinator
from rosia import request_shutdown, log
from rosia.time import s, ms, Time
from rosia.time.Timer import Timer


class BallState:
    """Position + velocity of the ball, streamable to rerun."""

    def __init__(
        self,
        position: np.ndarray,
        velocity: np.ndarray,
        color: list[int] = [255, 100, 50],
    ) -> None:
        self.position = position  # (3,)
        self.velocity = velocity  # (3,)
        self.color = color

    def to_rerun(self) -> rr.Points3D:
        return rr.Points3D(
            [self.position],
            radii=[0.3],
            colors=[self.color],
        )

    def __repr__(self) -> str:
        x, y, z = self.position
        return f"pos=({x:.2f}, {y:.2f}, {z:.2f})"


@Node
class BallSimulator:
    """Simulates a ball under gravity with elastic bounces off z=0."""

    tick = InputPort[Time]()
    output = OutputPort[BallState]()

    def __init__(
        self,
        initial_position: tuple[float, float, float] = (0.0, 0.0, 5.0),
        initial_velocity: tuple[float, float, float] = (2.0, 1.5, 0.0),
        gravity: float = -9.81,
        restitution: float = 0.85,
        dt: float = 0.02,
        max_ticks: int = 100,
        color: list[int] = [255, 100, 50],
        slow: bool = False,
    ):
        self.position = np.array(initial_position, dtype=float)
        self.velocity = np.array(initial_velocity, dtype=float)
        self.gravity = gravity
        self.restitution = restitution
        self.dt = dt
        self.max_ticks = max_ticks
        self.tick_count = 0
        self.color = color
        self.slow = slow

    @reaction([tick])
    def step(self):
        if self.slow:
            time.sleep(random.uniform(0.0, 0.1))
        # Apply gravity (z-axis is up)
        self.velocity[2] += self.gravity * self.dt
        self.position += self.velocity * self.dt

        # Bounce off ground plane z=0
        if self.position[2] <= 0.0:
            self.position[2] = -self.position[2]
            self.velocity[2] = -self.velocity[2] * self.restitution
        self.output(BallState(self.position.copy(), self.velocity.copy(), self.color))
        self.tick_count += 1
        if self.tick_count >= self.max_ticks and not self.slow:
            request_shutdown(0 * s)
            log.warning("Requesting shutdown")


@Node
class Renderer:
    """Logs ball position and ground plane to rerun."""

    input_state = InputPort[BallState]()

    def start(self):
        lines = []
        for i in np.linspace(-5, 15, 21):
            lines.append([[i, -5, 0], [i, 15, 0]])
            lines.append([[-5, i, 0], [15, i, 0]])
        log.rerun(
            rr.LineStrips3D(lines, colors=[[200, 200, 200]]),
            rerun_subpath="ground",
        )
        log.info("ground plane logged")

    @reaction([input_state])
    def render(self):
        log.info(f"ball {self.input_state}")


if __name__ == "__main__":
    coor = Coordinator()

    timer = coor.create_node(Timer(interval=20 * ms, offset=0 * s))

    sim1 = coor.create_node(
        BallSimulator(initial_position=(0.0, 0.0, 5.0), color=[255, 100, 50])
    )
    sim2 = coor.create_node(
        BallSimulator(initial_position=(0.0, 3.0, 5.0), color=[50, 150, 255], slow=True)
    )

    renderer1 = coor.create_node(Renderer())
    renderer2 = coor.create_node(Renderer())

    timer.output_timer >>= sim1.tick
    timer.output_timer >>= sim2.tick
    sim1.output >>= renderer1.input_state
    sim2.output >>= renderer2.input_state

    coor.diagram()
    rr.send_blueprint(
        rrb.Blueprint(
            rrb.Horizontal(
                rrb.Spatial3DView(origin="/"),
            )
        )
    )
    coor.execute(trace=True, log_level="DEBUG")
