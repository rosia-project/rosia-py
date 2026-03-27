---
sidebar_position: 4
---

# Timed Simulation

This tutorial builds a physics simulation with synchronized rendering — a bouncing ball driven by a timer. It shows how Rosia keeps a slow node synchronized with a fast one.

## Pipeline

```
Timer -> BallSimulator1 (fast) -+-> SyncRenderer
      -> BallSimulator2 (slow) -+
```

Two ball simulators feed into a single renderer. One simulator is slow (simulating a heavy computation). Rosia ensures the renderer always sees both balls at the same logical time.

## Ball state

```python
import numpy as np

class BallState:
    def __init__(self, position: np.ndarray, velocity: np.ndarray):
        self.position = position
        self.velocity = velocity
```

## Simulator

```python
import time
import random
from rosia import InputPort, OutputPort, reaction, Node
from rosia import request_shutdown
from rosia.time import s, Time


@Node
class BallSimulator:
    tick = InputPort[Time]()
    output = OutputPort[BallState]()

    def __init__(self, gravity=-9.81, dt=0.02, max_ticks=100, slow=False):
        self.position = np.array([0.0, 0.0, 5.0])
        self.velocity = np.array([2.0, 1.5, 0.0])
        self.gravity = gravity
        self.dt = dt
        self.max_ticks = max_ticks
        self.tick_count = 0
        self.slow = slow

    @reaction([tick])
    def step(self):
        if self.slow:
            time.sleep(random.uniform(0.0, 0.1))

        self.velocity[2] += self.gravity * self.dt
        self.position += self.velocity * self.dt

        if self.position[2] <= 0.0:
            self.position[2] = -self.position[2]
            self.velocity[2] *= -0.85

        self.output(BallState(self.position.copy(), self.velocity.copy()))
        self.tick_count += 1
        if self.tick_count >= self.max_ticks and not self.slow:
            request_shutdown(0 * s)
```

## Synchronized renderer

The renderer reacts to both balls. Because both simulators are driven by the same timer, their messages share the same logical timestamp and are merged into a single event.

```python
from rosia import log


@Node
class SyncRenderer:
    ball1 = InputPort[BallState]()
    ball2 = InputPort[BallState]()

    @reaction([ball1, ball2])
    def render(self):
        log.info(f"ball1 {self.ball1.position}  ball2 {self.ball2.position}")
```

## Wiring

```python
from rosia import Application
from rosia.time import ms
from rosia.time.Timer import Timer

app = Application()
timer = app.create_node(Timer(interval=20 * ms, offset=0 * s))
sim1 = app.create_node(BallSimulator(max_ticks=100))
sim2 = app.create_node(BallSimulator(max_ticks=100, slow=True))
renderer = app.create_node(SyncRenderer())

timer.output_timer >>= sim1.tick
timer.output_timer >>= sim2.tick
sim1.output >>= renderer.ball1
sim2.output >>= renderer.ball2

app.execute()
```

## What happens

1. The `Timer` fires every 20ms, driving both simulators.
2. `BallSimulator1` (fast) processes each tick immediately.
3. `BallSimulator2` (slow) sleeps 0–100ms per tick, falling behind in physical time.
4. `SyncRenderer` waits for **both** balls before rendering. Even though `BallSimulator2` is slow, the renderer always sees both positions at the same logical time.
5. After 100 ticks, `BallSimulator1` requests shutdown. All nodes — including the slow `BallSimulator2` — finish processing events up to the shutdown timestamp before exiting.

This is the key benefit of Rosia's synchronization model: correctness is guaranteed by logical time, regardless of physical execution speed.
