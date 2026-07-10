---
sidebar_position: 3
---

# Synchronization

[Full source code](https://github.com/rosia-project/rosia-py/blob/main/examples/synchronization.py)

This tutorial builds on the [Timer](timer.md) tutorial. Instead of having just one timer and integer generator, now two independent timers drive two integer generators, and a single printer receives both streams and verifies they are
synchronized.

## Pipeline

Two timers tick at the same interval and offset. Each drives its own `IntGenerator`. The `Printer` has two input ports and reacts when both have a value at the same [logical time](../handbook/logical_time).

![Synchronization Pipeline Diagram](imgs/synchronization_diagram.png)

## Nodes

```python
from rosia import InputPort, OutputPort, reaction, Node, Application, request_shutdown, log
from rosia.time import Timer, Time, s


@Node
class IntGenerator:
    timer = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @reaction([timer])
    def generate(self):
        self.output(self.count)
        self.count += 1


@Node
class Printer:
    input_int1 = InputPort[int]()
    input_int2 = InputPort[int]()

    def __init__(self):
        self.receive_count = 0

    @reaction([input_int1, input_int2])  # Fire when EITHER port receives a message
    def print_message(self):
        assert self.input_int1 == self.input_int2, "Input ports should have the same value"
        log.info(f"Received: {self.input_int1} {self.input_int2}")
        self.receive_count += 1
        if self.receive_count >= 3:
            request_shutdown()
```

## Wiring

```python
app = Application()
timer1 = app.create_node(Timer(interval=1 * s, offset=0 * s))
timer2 = app.create_node(Timer(interval=1 * s, offset=0 * s))
int_gen1 = app.create_node(IntGenerator())
int_gen2 = app.create_node(IntGenerator())
printer = app.create_node(Printer())

timer1.output_timer >>= int_gen1.timer
timer2.output_timer >>= int_gen2.timer
int_gen1.output >>= printer.input_int1
int_gen2.output >>= printer.input_int2

app.execute()
```

Output:

```
[Printer_4] Received: 0 0
[Printer_4] Received: 1 1
[Printer_4] Received: 2 2
```

## Why does this work?

Both timers tick at the same interval, so `IntGenerator1` and `IntGenerator2` produce messages at the same logical timestamps. When `Printer` reacts at logical time `0s`, both `input_int1` and `input_int2` hold the value `0`. At `1s`, both
hold `1`, and so on.

The `assert` never fails because Rosia guarantees that a reaction sees all port values at the same logical time. Even though the two generators run in separate processes and may finish at different wall-clock times, `Printer` will not fire
until both values for that timestamp are available.

This is the key difference from callback-based and pub-sub frameworks: you don't need locks, queues, or manual synchronization. Rosia handles it automatically based on logical time.

## Key points

- A [reaction](../handbook/model#reactions) listing multiple input ports (`@reaction([port1, port2])`) fires when **any** listed port receives a message.
- When the reaction fires, all ports reflect their values at that [logical time](../handbook/logical_time).
- Two independent pipelines producing messages at the same logical time are automatically synchronized at the consumer.
