---
sidebar_position: 1
---

# Quick Start

Let's get started with **Rosia in less than 5 minutes**.

## Installation

Production installation:

```bash
pip install rosia
```

Install from source:

```bash
git clone https://github.com/rosia-project/rosia.git
cd rosia
pip install -e .
```

Requires `python>=3.9`.

## Your First Application

A Rosia application is a graph of **nodes** connected by **ports**. Each node reacts to messages on its input ports and sends messages on its output ports.

```python
from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import request_shutdown, log
from rosia.time import s, Time
from rosia.time.Timer import Timer


@Node
class Counter:
    tick = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @reaction([tick])
    def on_tick(self):
        self.output(self.count)
        self.count += 1
        if self.count >= 3:
            request_shutdown(0 * s)


@Node
class Printer:
    value = InputPort[int]()

    @reaction([value])
    def on_value(self):
        log.info(f"Got: {self.value}")


app = Application()
timer = app.create_node(Timer(interval=1 * s, offset=0 * s))
counter = app.create_node(Counter())
printer = app.create_node(Printer())

timer.output_timer >>= counter.tick
counter.output >>= printer.value

app.execute()
```

Save this as `app.py` and run it:

```bash
python app.py
```

```
[Counter_1] on_tick()
[Printer_2] on_value()
[Printer_2] Got: 0
[Counter_1] on_tick()
[Printer_2] on_value()
[Printer_2] Got: 1
[Counter_1] on_tick()
[Printer_2] on_value()
[Printer_2] Got: 2
```

## Core Concepts

| Concept              | Description                                                     |
| -------------------- | --------------------------------------------------------------- |
| `@Node`              | Decorator that marks a class as a Rosia node.                   |
| `InputPort[T]()`     | Declares a typed input port on a node.                          |
| `OutputPort[T]()`    | Declares a typed output port on a node.                         |
| `@reaction([ports])` | Marks a method to fire when any listed port receives a message. |
| `self.port(value)`   | Sends a value on an output port.                                |
| `self.port`          | Reads the current value of an input port.                       |
| `>>=`                | Connects an output port to an input port.                       |
| `Application`        | Creates nodes, wires ports, and runs the application.           |
| `Timer`              | Built-in node that fires at a regular interval.                 |
| `request_shutdown()` | Initiates coordinated shutdown of all nodes.                    |

## Next Steps

- [Hello World](tutorial/hello) — a more detailed walkthrough
- [Chaining Nodes](tutorial/chain) — build multi-stage pipelines
- [Synchronization](tutorial/synchronization) — merge multiple sources
- [Timed Simulation](tutorial/simulation) — physics simulation with slow/fast nodes
