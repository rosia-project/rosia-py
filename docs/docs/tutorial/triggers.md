---
sidebar_position: 4
---

# Physical Actions with `@trigger`

[Full source code](https://github.com/rosia-project/rosia/blob/main/examples/physical_trigger.py)

Reactions decorated with `@reaction` only fire in response to messages on input ports. That is not enough when the world outside the dataflow graph needs to inject events — sensor callbacks, GUI inputs, network polls, hardware interrupts.
The `@trigger` decorator declares a **physical action**: a method on a node that becomes callable from any thread, scheduling its body as a reaction stamped at the wall-clock time of the call.

This is Rosia's equivalent of [Lingua Franca's physical action](https://www.lf-lang.org/docs/handbook/actions#physical-actions).

## API

```python
from rosia import Node, OutputPort, trigger

@Node
class SensorReader:
    output = OutputPort[int]()

    @trigger
    def on_sample(self, value):
        self.output(value)
```

Calling `self.on_sample(value)` from any thread:

1. Captures the **wall-clock** time of the call and converts it to a logical timestamp `t = physical_time_now - application_start_time`.
2. Enqueues the decorated body as a reaction at `t` in the owning node's reaction queue. The enqueue is thread-safe.
3. Wakes the node's event loop so the reaction fires as soon as the queue is processed.

Arguments passed to the call (`value` here) flow through to the reaction body. The body itself always runs on the node's event-loop thread, so user code inside `on_sample` does not need locks even though the call site can be on any thread.

## A complete example

```python
import threading
import time

from rosia import InputPort, Node, OutputPort, Application, reaction, trigger, log
from rosia import request_shutdown


@Node
class SensorReader:
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @trigger
    def on_sample(self, value):
        self.count += 1
        self.output(value)
        log.info(f"trigger fired with value={value}")
        if self.count >= 5:
            request_shutdown()

    def start(self):
        # Spawn a producer thread inside the node. The thread lives for
        # the lifetime of the node; it can fire triggers at any time.
        threading.Thread(target=self._poll, daemon=True).start()

    def _poll(self):
        for i in range(5):
            time.sleep(0.2)
            self.on_sample(i)


@Node
class Printer:
    input_int = InputPort[int]()

    @reaction([input_int])
    def print_value(self):
        log.info(f"Printer received: {self.input_int}")


if __name__ == "__main__":
    app = Application()
    sensor = app.create_node(SensorReader())
    printer = app.create_node(Printer())
    sensor.output >>= printer.input_int
    app.execute()
```

A daemon thread inside `SensorReader.start()` periodically calls `self.on_sample(i)`. Each call schedules `on_sample` at `t = physical_time_now - app_start`. The reaction body runs at that logical time, emits the value on `output`, and
(after five samples) requests shutdown.

## Differences from `@reaction`

|                         | `@reaction([port])`                           | `@trigger`                                                         |
| ----------------------- | --------------------------------------------- | ------------------------------------------------------------------ |
| Fired by                | A message arriving on a listed input port     | A direct call to the decorated method, from any thread             |
| Timestamp               | The message's logical timestamp               | `physical_time_now - app_start`                                    |
| Args                    | None (reads port values via `self.port`)      | Passed through to the body                                         |
| Thread safety           | Always runs on the event-loop thread          | Call site can be any thread; body runs on the event-loop thread    |
| Affects downstream STAT | Yes (via [ENT propagation](../handbook/STAT)) | No — the node reports the same ENT as it would without the trigger |

The last row is important: **triggers do not propagate ENT** to downstream nodes. Downstream may have already advanced past the trigger's logical timestamp by the time the emitted message arrives. If the downstream consumer is tolerant of
out-of-order messages (e.g. it processes them via a `//=` physical connection, which carries no timestamp), this is fine. If you need strict logical-time ordering, place the consumer on a separate node connected with `>>=` and accept that
the consumer's logical clock may have advanced.

## When to use `@trigger`

- Wrapping hardware: a serial port reader, a GPIO interrupt, a USB event.
- Bridging into a callback API: ROS subscribers, ZeroMQ, gRPC streams.
- GUI input: a button click handler running on the GUI thread.
- Periodic external sources you don't want to express as a Rosia `Timer` (e.g. a fast incoming network stream).

For purely logical-time-driven sources (e.g. "produce a value every 1 second of logical time"), use a [Timer](timer.md) instead — it integrates cleanly with [STAT](../handbook/STAT).

## Lifecycle notes

- A node that declares any `@trigger` method stays alive until `request_shutdown()` is called. The runtime never natural-shutdowns such a node, because the external thread could fire a trigger at any time.
- Calls from the same trigger thread are serialized in arrival order. Calls from multiple threads are serialized through a thread-safe queue, but inter-thread ordering depends on the OS scheduler.
- Calling `self.on_sample(...)` from inside an existing reaction also works — the new reaction is just scheduled at `physical_time_now - app_start`. The current reaction continues to completion first.

## Key points

- `@trigger` declares a physical action that can be invoked from any thread.
- The call site is thread-safe; the reaction body runs on the event-loop thread.
- The reaction is stamped at wall-clock time, not at any upstream logical time.
- Triggers do not bound downstream STAT — use physical (`//=`) connections downstream of a trigger if you need to avoid logical-time violations.
