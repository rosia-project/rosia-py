---
sidebar_position: 5
---

# Visualization with Rerun

Rosia integrates with [Rerun](https://rerun.io/) for visualizing node data over time. Rerun provides an interactive viewer that plots data against both logical and physical time.

## Enabling Tracing

Pass `trace=True` to `app.execute()` to enable Rerun logging. This opens the Rerun viewer automatically.

```python
app.execute(trace=True)
```

When tracing is enabled:

- All input port values are automatically logged to Rerun on each reaction.
- Text log messages from `log.info(...)`, `log.debug(...)`, etc. appear in the Rerun timeline.
- Data is indexed by both **logical time** and **physical time**, so you can scrub through the timeline in either mode.

## Node Diagram

Call `app.diagram()` before `execute()` to render the node graph in Rerun. This shows the topology of your application — nodes, ports, and connections.

```python
app.diagram()
app.execute(trace=True)
```

## Automatic Port Logging

When tracing is enabled, Rosia automatically logs every input port value on each reaction. If the value is a plain type (int, str, etc.), it is logged as a `TextLog`. If the value has a `to_rerun()` method, Rosia calls it and logs the
result as a Rerun component.

### The `to_rerun()` method

Define `to_rerun()` on your data class to control how it appears in the Rerun viewer:

```python
import numpy as np
import rerun as rr


class BallState:
    def __init__(self, position: np.ndarray, color: list[int]):
        self.position = position
        self.color = color

    def to_rerun(self) -> rr.Points3D:
        return rr.Points3D(
            [self.position],
            radii=[0.3],
            colors=[self.color],
        )
```

When a node receives a `BallState` on an input port, Rosia calls `ball_state.to_rerun()` and logs the resulting `rr.Points3D` to Rerun. This appears as a 3D point in the spatial viewer.

You can return any Rerun archetype — `rr.Points3D`, `rr.Image`, `rr.LineStrips3D`, `rr.TextLog`, etc.

## Manual Logging with `log.rerun()`

Use `log.rerun()` to log arbitrary Rerun data from within a node:

```python
from rosia import log
import rerun as rr


@Node
class Renderer:
    input_state = InputPort[BallState]()

    def start(self):
        # Log static geometry (ground plane)
        lines = [[[0, 0, 0], [10, 0, 0]], [[0, 0, 0], [0, 10, 0]]]
        log.rerun(
            rr.LineStrips3D(lines, colors=[[200, 200, 200]]),
            rerun_subpath="ground",
        )

    @reaction([input_state])
    def render(self):
        log.info(f"ball {self.input_state}")
```

- `log.rerun(archetype, rerun_subpath="...")` logs a Rerun component. The `rerun_subpath` controls where it appears in the Rerun entity tree.
- `log.info(...)`, `log.warning(...)`, etc. also appear in Rerun as text logs when tracing is enabled.

## Custom Rerun Blueprints

Use Rerun's blueprint API to configure the viewer layout:

```python
import rerun as rr
import rerun.blueprint as rrb

app.diagram()
rr.send_blueprint(
    rrb.Blueprint(
        rrb.Horizontal(
            rrb.Spatial3DView(origin="/"),
        )
    )
)
app.execute(trace=True)
```

## Full Example

Here is a complete example — a bouncing ball simulation with Rerun visualization:

```python
import numpy as np
import rerun as rr
import rerun.blueprint as rrb

from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown, log
from rosia.time import s, ms, Time
from rosia.time.Timer import Timer


class BallState:
    def __init__(self, position: np.ndarray, velocity: np.ndarray):
        self.position = position
        self.velocity = velocity

    def to_rerun(self) -> rr.Points3D:
        return rr.Points3D([self.position], radii=[0.3], colors=[[255, 100, 50]])


@Node
class BallSimulator:
    tick = InputPort[Time]()
    output = OutputPort[BallState]()

    def __init__(self):
        self.position = np.array([0.0, 0.0, 5.0])
        self.velocity = np.array([2.0, 1.5, 0.0])
        self.tick_count = 0

    @reaction([tick])
    def step(self):
        dt = 0.02
        self.velocity[2] += -9.81 * dt
        self.position += self.velocity * dt
        if self.position[2] <= 0.0:
            self.position[2] = -self.position[2]
            self.velocity[2] *= -0.85
        self.output(BallState(self.position.copy(), self.velocity.copy()))
        self.tick_count += 1
        if self.tick_count >= 100:
            request_shutdown(0 * s)


@Node
class Renderer:
    ball = InputPort[BallState]()

    def start(self):
        lines = []
        for i in range(-5, 16):
            lines.append([[i, -5, 0], [i, 15, 0]])
            lines.append([[-5, i, 0], [15, i, 0]])
        log.rerun(rr.LineStrips3D(lines, colors=[[200, 200, 200]]), rerun_subpath="ground")

    @reaction([ball])
    def render(self):
        log.info(f"ball {self.ball.position}")


app = Application()
timer = app.create_node(Timer(interval=20 * ms, offset=0 * s))
sim = app.create_node(BallSimulator())
renderer = app.create_node(Renderer())
timer.output_timer >>= sim.tick
sim.output >>= renderer.ball

app.diagram()
rr.send_blueprint(rrb.Blueprint(rrb.Spatial3DView(origin="/")))
app.execute(trace=True)
```

Run this and the Rerun viewer opens with:

- A 3D view showing the ball bouncing on a grid
- A timeline scrubber indexed by logical time and physical time
- Text logs from each node
- The node topology diagram
