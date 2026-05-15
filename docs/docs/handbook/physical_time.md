---
sidebar_position: 3
---

# Physical Time and Realtime Mode

[Logical time](logical_time) is the ordering and synchronization clock. Logical time is independent of wall-clock time: a logical timestamp like `1 * s` is just a label that orders messages, not a guarantee about how long execution actually
takes.

**Physical time** is wall-clock time. By default, every node runs in **realtime mode**: before firing any reaction at logical time `t`, the node waits until physical time has caught up. This makes a logical timestamp behave like a real-time
deadline — useful for hardware, simulators with visualization, and any pipeline whose pace must match the real world.

## Default behavior

```python
app = Application()                       # realtime=True (default)
timer = app.create_node(Timer(interval=1 * s))
```

A `Timer(interval=1 * s)` emits a tick every second of **wall-clock** time, not every second of CPU time. A reaction that `yield 100 * ms` pauses for 100 ms of wall-clock time before resuming. A node receiving an input stamped at `2 * s`
will not fire the corresponding reaction until 2 s of wall-clock time has elapsed since the application started.

Logical time still controls ordering, synchronization, and STAT. Realtime mode only adds a **lower bound** on when each reaction may fire.

## Turning realtime off

For tests, simulations, replay, and any pipeline that should run as fast as the CPU allows, disable realtime mode:

```python
app = Application(realtime=False)          # whole-app default
```

Every node created through this `Application` runs as-fast-as-possible. The `Timer` still emits at logical `0 * s`, `1 * s`, `2 * s`, …, but downstream nodes process them in tight succession.

Individual nodes can override the application default:

```python
app = Application(realtime=False)           # default: as-fast-as-possible
sensor = app.create_node(SensorReader(), realtime=True)   # this one is realtime
fast = app.create_node(Crunch())                          # inherits app default
```

This is useful when one node interacts with hardware while the rest of the pipeline can churn through logical time at full speed.

## When to use each mode

|                                      | `realtime=True` (default)                     | `realtime=False`            |
| ------------------------------------ | --------------------------------------------- | --------------------------- |
| Hardware loop                        | ✅                                            | ❌ — hardware can't keep up |
| Visualization / Rerun                | ✅                                            | usually too fast to watch   |
| Closed-loop simulator with a live UI | ✅                                            | ❌                          |
| Headless training / batch simulation | unnecessary cost                              | ✅                          |
| Unit and integration tests           | only when wall-clock is the system under test | ✅ — finish in milliseconds |
| Replaying a log                      | matches original cadence                      | ✅ — analyze quickly        |

## How the gate works

When realtime mode is on, the node's event loop computes the wall-clock equivalent of the next pending reaction's timestamp:

```
target_physical_time = application_start_time + next_reaction_timestamp
```

If `get_physical_time() < target_physical_time`, the node blocks until the deadline. The block is **interruptible**: if a [`@trigger`](../tutorial/triggers) call or an earlier-timestamp upstream message arrives during the wait, the node
wakes immediately, re-evaluates its heap, and fires the earliest pending event first.

The gate is per-node. STAT (the synchronization mechanism across nodes) is unaffected: a realtime node still reports the same ENT as a non-realtime one.

## Interaction with `@trigger`

[Triggers](../tutorial/triggers) already capture wall-clock at the call site, so the realtime gate is effectively a no-op for them: the moment they're enqueued, `physical_time_now >= start_time + t` by construction.

## Precision and limits

- The realtime gate uses ZeroMQ polling under the hood, which has millisecond resolution. Sub-millisecond targets round up to 1 ms.
- On non-`PREEMPT_RT` Linux, `time.sleep`-style waits typically wake 100 µs – 1 ms late under load. The reaction's stamped logical time is unaffected — only the moment of firing slips.
- Realtime mode does not slow down a node whose logical clock is already behind wall-clock: the gate is "wait if too early, never wait if late or on-time". If logical time has fallen behind physical time, reactions fire back-to-back until
  the node catches up.
