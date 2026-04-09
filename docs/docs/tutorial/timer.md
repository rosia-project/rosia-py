---
sidebar_position: 2
---

# Timer

This tutorial shows how to use a `Timer` node to drive periodic events.

## Pipeline

```
Timer -> IntGenerator -> Printer
```

A `Timer` fires at a fixed interval. Each tick triggers `IntGenerator` to produce the next integer, which `Printer` logs.

![Timer Pipeline Diagram](imgs/timer_diagram.png)

## Timer

`Timer` is a built-in source node that emits its logical time at a fixed interval. It has one output port, `output_timer`, of type `Time`.

```python
timer = app.create_node(Timer(interval=1 * s, offset=0 * s))
```

- `interval` — time between ticks. `1 * s` means one tick per second.
- `offset` — logical time of the first tick. `0 * s` means the first tick fires immediately.

The timer runs indefinitely until the application shuts down. To stop it, call `request_shutdown()` from any node.

## Nodes

```python
from rosia import InputPort, OutputPort, reaction, Node, Application, request_shutdown
from rosia import log
from rosia.time import Timer, Time, s

@Node
class IntGenerator:
    tick = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @reaction([tick])
    def generate(self):
        log.info(f"tick: {self.tick}")
        self.count += 1
        self.output(self.count)
        if self.count >= 5:
            request_shutdown()


@Node
class Printer:
    input_port = InputPort[int]()

    @reaction([input_port])
    def print_value(self):
        log.info(f"Result: {self.input_port}")
```

## Wiring

```python
app = Application()
timer = app.create_node(Timer(interval=1 * s, offset=0 * s))
gen = app.create_node(IntGenerator())
printer = app.create_node(Printer())

timer.output_timer >>= gen.tick
gen.output >>= printer.input_port

app.execute()
```

Output:

```
[IntGenerator_1] tick:  0.000ns
[Printer_2] Result: 1
[IntGenerator_1] tick:  1.000s
[Printer_2] Result: 2
[IntGenerator_1] tick:  2.000s
[Printer_2] Result: 3
[IntGenerator_1] tick:  3.000s
[Printer_2] Result: 4
[IntGenerator_1] tick:  4.000s
[Printer_2] Result: 5
```

## Logical time

Each message in Rosia carries a **logical timestamp**. The `Timer` emits timestamps at its configured interval: `0ns`, `1s`, `2s`, etc. These are logical times, not wall-clock times — the application may run faster or slower than real time.

Notice the output above: `IntGenerator` receives tick `0.000ns` first, then `Printer` sees `Result: 1`, then tick `1.000s`, then `Result: 2`, and so on. Rosia guarantees that all nodes process messages in logical time order. Even though
`IntGenerator` and `Printer` run in separate processes, `Printer` will never see `Result: 2` before `Result: 1`.

Time units available: `s` (seconds), `ms` (milliseconds), `us` (microseconds), `ns` (nanoseconds). For example, `500 * ms` is half a second.

## Key points

- `Timer` is a built-in source node that emits its current logical time at a fixed `interval`.
- `IntGenerator` reacts to each tick by incrementing a counter and sending it downstream.
- `request_shutdown()` stops the application after 5 ticks.
- The `>>=` operator connects an output port to an input port.
