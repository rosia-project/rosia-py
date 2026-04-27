---
sidebar_position: 0
---

# Model of Computation

Rosia is a variant of the [reactor model of computation](https://reactor-model.org/). A program is a directed graph of **nodes** that communicate through **ports**. Each node runs in its own process. All ordering and synchronization is
governed by **logical time**, not wall-clock time.

## Nodes

A node is a Python class decorated with `@Node`. Each node is an isolated unit of computation with its own logical clock, event queue, and reaction queue. Nodes do not share memory — they communicate exclusively by sending messages through
ports.

```python
@Node
class MyNode:
    ...
```

A node's lifecycle has three phases:

1. **Initialization** (`__init__`): Set up internal state. No messages are sent or received during this phase.
2. **Startup** (`start()`): Called once before the event loop begins. The node can send initial messages and use `yield` to schedule future work.
3. **Event loop**: The node repeatedly drains incoming messages, advances logical time, and fires reactions until shutdown.

## Ports

Nodes declare typed **input ports** and **output ports** as class attributes:

```python
@Node
class MyNode:
    data_in = InputPort[int]()
    data_out = OutputPort[int]()
```

- **Output ports** send messages. Calling `self.data_out(value)` sends `value` to all connected downstream input ports, stamped with the node's current logical time.
- **Input ports** receive messages. Reading `self.data_in` returns the most recent value delivered to that port.

Ports are connected in the application wiring using the `>>=` operator:

```python
node_a.data_out >>= node_b.data_in
```

A single output port can connect to multiple input ports (fan-out), and a single input port can receive from multiple output ports (fan-in). Connections are type-checked at wiring time.

### Port value retention

Port values are **retained**, not cleared after each reaction. If a reaction reads a port that did not receive a new message at the current logical time, it sees the most recent value that port held.

## Reactions

A **reaction** is a method that fires in response to messages arriving on one or more input ports. It is declared with the `@reaction` decorator:

```python
@reaction([data_in])
def on_data(self):
    result = self.data_in * 2
    self.data_out(result)
```

Key properties:

- A reaction lists one or more **trigger ports**. It fires when **any** of them receives a message.
- When triggered, the node's logical time advances to the timestamp of the triggering message. All port values reflect their state at that logical time.
- Multiple messages arriving at the same logical time on different trigger ports of the same reaction cause **a single firing**, not one per port. The runtime waits until all messages at that timestamp have arrived before firing — see
  [STAT](STAT) for how that synchronization is enforced.
- A reaction can use `yield <Time>` to pause and resume after a logical time interval. This turns the reaction into a generator that is re-scheduled at `current_time + delta`.

## Logical Time

Every message carries a **logical timestamp**. Logical time is a discrete, monotonically increasing value that determines the order in which messages are processed. It is independent of wall-clock time — an application may run faster or
slower than real time.

Each node maintains its own logical clock. The clock advances when:

- A reaction is triggered by an incoming message (the clock moves to the message's timestamp).
- A reaction yields a time delta (the clock moves forward by that amount).

Rosia guarantees that within a node, messages are always processed in logical time order. Across nodes, [STAT](STAT) ensures that a node does not advance past a time where it might still receive messages.

For details on time representation and arithmetic, see [Logical Time](logical_time).

## Dataflow Execution

Rosia uses a **push-based dataflow** model. When a node sends a message on an output port, the message is delivered to all connected downstream input ports via ZeroMQ transports. There is no polling or pull-based fetching.

The execution order within a node follows these rules:

1. All events at logical time $t$ are processed before any event at $t' > t$.
2. At a given logical time, all pending reactions complete before new events are dequeued.
3. A node never advances its logical time past its [STAT](STAT) boundary.

These rules guarantee causal consistency: if message A caused message B, any node that sees both will always process A first.
