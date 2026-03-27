---
sidebar_position: 1
---

# Hello World

This tutorial builds the simplest possible Rosia application: one node sends a message, another prints it.

## Define Nodes

A Rosia node is a Python class decorated with `@Node`. Ports are declared as class attributes.

```python
from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import log


@Node
class Greeter:
    output = OutputPort[str]()

    def start(self):
        self.output("Hello, World!")


@Node
class Printer:
    message = InputPort[str]()

    @reaction([message])
    def print_message(self):
        log.info(self.message)
```

- `OutputPort[T]()` declares a typed output port.
- `InputPort[T]()` declares a typed input port.
- `start()` is called once when the application begins. Here, `Greeter` sends a single message.
- `@reaction([ports...])` marks a method to fire when any listed port receives a message.
- `self.output(value)` sends a value on an output port.
- `self.message` reads the current value of an input port. Do not use `input` to name your port since it's a reserved python keyword.

## Wire and Run

Create a `Application`, instantiate nodes, connect ports with `>>=`, and call `execute()`. Connections are automatically type checked.

```python
app = Application()
greeter = app.create_node(Greeter())
printer = app.create_node(Printer())
greeter.output >>= printer.message
app.execute()
```

Run with `python hello.py`. This produces:

```
[Printer_1] Hello, World!
```

## What happened

1. `Greeter.start()` sends `"Hello, World!"` on its output port.
2. `Printer` reacts to the message and logs it. Since greeter is numbered 0, printer is numbered 1.
3. Since `Greeter` has no more messages to send, it signals completion. `Printer` receives this signal, detects it has no more work, and the application shuts down automatically.

No timers, no explicit shutdown — Rosia detects when the dataflow graph has finished and exits cleanly.
