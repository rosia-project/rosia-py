---
sidebar_position: 3
---

# Synchronization

This tutorial shows how Rosia automatically synchronizes messages from multiple sources. When two messages arrive at the same logical time, they are processed together in a single reaction.

## Pipeline

```
Timer -> IntGenerator1 -+-> Printer
Timer -> IntGenerator2 -+
```

Two independent timers drive two generators. Both feed into a single `Printer` node with two input ports.

## Nodes

```python
from rosia import InputPort, OutputPort, reaction, Node, Coordinator
from rosia import request_shutdown, log
from rosia.time import s, Time
from rosia.time.Timer import Timer


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

    @reaction([input_int1, input_int2])
    def print_message(self):
        log.info(f"Received: {self.input_int1}, {self.input_int2}")
        assert self.input_int1 == self.input_int2
        self.receive_count += 1
        if self.receive_count >= 3:
            request_shutdown(0 * s)
```

## Wiring

Both timers use the same interval and offset, so they fire at the same logical times.

```python
coor = Coordinator()
timer1 = coor.create_node(Timer(interval=1 * s, offset=0 * s))
timer2 = coor.create_node(Timer(interval=1 * s, offset=0 * s))
gen1 = coor.create_node(IntGenerator())
gen2 = coor.create_node(IntGenerator())
printer = coor.create_node(Printer())

timer1.output_timer >>= gen1.timer
timer2.output_timer >>= gen2.timer
gen1.output >>= printer.input_int1
gen2.output >>= printer.input_int2

coor.execute()
```

Output:

```
Received: 0, 0
Received: 1, 1
Received: 2, 2
```

## How synchronization works

Both generators send at the same logical timestamp (driven by timers with the same interval). Rosia's event queue merges messages at the same timestamp into a single event. The `Printer`'s reaction fires once per timestamp with both values
available.

This happens automatically — no manual synchronization is needed. Even if one generator is physically slower than the other, Rosia waits until all messages for a timestamp have arrived before triggering the reaction.

## Port value retention

Input ports retain their most recent value. If a reaction is triggered by one port, the other port still holds its previous value:

```python
@reaction([input_int1, input_int2])
def print_message(self):
    # Both ports are always readable, even if only one
    # received a new message in this event
    log.info(f"{self.input_int1}, {self.input_int2}")
```
