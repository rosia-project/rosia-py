---
sidebar_position: 1
---

# Logical Time

In Rosia, _logical time_ is the timestamp system used for ordering and synchronization. It is up to you to control logical time within each node, and Rosia will take care of execution and synchronization across nodes.

Logical time is a monotonically increasing value. You can think of it as an order specification for messages and code execution. A message with a smaller logical time will be processed with a reaction before a message with a large logical
time.

Messages with the same logical time are considered simultaneous. As shown in example [Synchronization](../tutorial/synchronization), if multiple input ports have the same logical time, they will be synchronized to only trigger the reaction
once.

Each node has logical time `Time(0)` when `start()` is called at the beginning of execution. The logical time can be manipulated in `start()` and reactions marked with the `@reaction()` decorator in the following ways:

- `yield <Time>` pauses the current reaction, and resumes after the specified logical time interval. In the meantime, it will process other reactions.
- When a reaction is triggered by reacting to input ports defined in `@reaction(<ports>)`, the node will advance logical time to the logical time associated with the message received at the input port.

# Time Representation

Rosia is a variant of the [reactor model of computation](https://reactor-model.org/) and uses the discrete time model. In `rosia/time/Time.py`, a time value is a `(value, microstep)` pair where `value` is an integer count of nanoseconds and
`microstep` is an integer used to order events that share the same `value`. Rosia provides built-in time units `s`, `ms`, `us` and `ns`:

- 1 `ns` = 1 nanosecond
- 1 `us` = 1000 `ns`
- 1 `ms` = 1000 `us`
- 1 `s` = 1000 `ms`

All time values are treated as intervals, so you can add, subtract and multiply time. For example, to denote an interval of 3 seconds, you can use `3 * s`.

Microsteps order events at the same nanosecond. They are compared lexicographically with `value`: `Time(t, m) < Time(t, m+1) < Time(t+1, 0)`. Microsteps are used by after-delays on connections to break feedback-loop ties without advancing
physical-time-aligned logical time.

There's also `never` that represents the smallest time value, and `forever` that represents the largest time value. Adding or subtracting time to `never` and `forever` will yield `never` or `forever`.

# After-Delays on Connections

Connections can be declared with an `after-delay` that bumps the logical time of every message flowing through them:

```python
output_port.connect(input_port, delay=5 * ms)   # delay by 5 ms of logical time
output_port.connect(input_port, delay=1)        # delay by one microstep
output_port.connect(input_port, delay=3)        # delay by three microsteps
```

The delay is added to the message's timestamp on the sending side, so the downstream input port receives and processes the message at `sender_logical_time + delay`. The same delay is also folded into [STAT](STAT) calculations: a transitive
upstream node reachable through a path with total delay $d$ contributes its ENT $+ d$ to the receiver's STAT.

When `delay` is passed as an `int`, it is interpreted as a microstep count: `delay=N` is equivalent to `delay=Time(0, microstep=N)`. For non-microstep delays, pass a `Time` value (e.g. `5 * ms`).

Use a microstep delay (e.g. `delay=1`) to break causality in feedback loops without advancing the physical-time-aligned `value`. Each pass around the loop strictly increases the microstep, so logical time is monotonic and the runtime never
deadlocks waiting on its own future output.
