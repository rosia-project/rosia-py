---
sidebar_position: 2
---

# Chaining Nodes

This tutorial shows how to build a processing pipeline by chaining multiple nodes together.

## Pipeline

```
Timer -> IntGenerator -> Doubler -> Printer
```

Each node transforms the data and passes it to the next.

## Nodes

```python
from rosia import InputPort, OutputPort, reaction, Node, Coordinator
from rosia import request_shutdown, log
from rosia.time import s, Time
from rosia.time.Timer import Timer


@Node
class IntGenerator:
    tick = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @reaction([tick])
    def generate(self):
        self.count += 1
        self.output(self.count)
        if self.count >= 5:
            request_shutdown(0 * s)


@Node
class Doubler:
    input_port = InputPort[int]()
    output_port = OutputPort[int]()

    @reaction([input_port])
    def process(self):
        self.output_port(self.input_port * 2)


@Node
class Printer:
    input_port = InputPort[int]()

    @reaction([input_port])
    def print_value(self):
        log.info(f"Result: {self.input_port}")
```

## Wiring

```python
coor = Coordinator()
timer = coor.create_node(Timer(interval=1 * s, offset=0 * s))
gen = coor.create_node(IntGenerator())
doubler = coor.create_node(Doubler())
printer = coor.create_node(Printer())

timer.output_timer >>= gen.tick
gen.output >>= doubler.input_port
doubler.output_port >>= printer.input_port

coor.execute()
```

Output:

```
Result: 2
Result: 4
Result: 6
Result: 8
Result: 10
```

## Key points

- Nodes are connected in a chain. Each node reacts to its input and sends to its output.
- The `>>=` operator connects an output port to an input port.
- Data flows through the chain in timestamp order — `Printer` always sees the doubled value at the same logical time as the original.
