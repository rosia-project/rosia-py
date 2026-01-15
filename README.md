# rosia: robotic middleware for python

## Install
```bash
pip install -e .
```

## Quick Start

### First program
Let's write a first program that generates and prints numbers using timers. 

First, write a node that generates numbers:

```python
@Node
class IntGenerator:
    output_int = OutputPort[int]()
    def __init__(self):
        self.count = 0
    def start(self):
        while True:
            print("Sending:", self.count)
            self.output_int(self.count)
            self.count += 1
            time.sleep(1)
```

Output ports are declared with `<output_port> = OutputPort[<type>]()`. `__init__` initializes the node, and `start` automatically runs after all nodes are initialized.

```python
@Node
class Printer:
    input_int = InputPort[int]()
    @reaction([input_int])
    def print_message(self):
        print(f"Received: {self.input_int}")
```

This nodes prints the numbers. Input ports are declared with `<input_port> = InputPort[<type>]()`. The received message can be referenced by `self.<input_port>`.

With the `@reaction` decorator, every time the input port `self.input_int` receives a message, the `print_message` method is executed.

To connect the two nodes, use a coordinator and create nodes within the coordinator. Connect ports using the `>>=` operator. Each node is a separate process for true concurrency. 

```python
coor = Coordinator()
int_gen = coor.create_node(IntGenerator())
printer = coor.create_node(Printer())
int_gen.output_int >>= printer.input_int
coor.execute()
```

Nodes initialize and run after `coor.execute()` is called. Run this example with `python tests/examples/easy.py`.

### Time and synchronization
Let's modify the int generator to be triggered by a timer. 

```python
@Node
class IntGenerator(Rosia):
    timer = InputPort[Time]()
    output = OutputPort[int]()

    def __init__(self):
        self.count = 0

    @reaction([timer])
    def generate(self):
        self.output(self.count)
        self.count += 1
```

and the printer to print two numbers from two input ports.
```python
@Node
class Printer:
    input_int1 = InputPort[int]()
    input_int2 = InputPort[int]()

    @reaction([input_int1, input_int2])
    def print_message(self):
        print(f"Received message: {self.input_int1} {self.input_int2}")
```

We can create two instances of `IntGenerator` in a coordinator:

```python
coor = Coordinator(logging.INFO)
timer1 = coor.create_node(Timer(interval=1 * ms, offset=0 * s))
timer2 = coor.create_node(Timer(interval=1 * ms, offset=0 * s))
int_gen1 = coor.create_node(IntGenerator())
int_gen2 = coor.create_node(IntGenerator())
printer = coor.create_node(Printer())
timer1.output_timer >>= int_gen1.timer
timer2.output_timer >>= int_gen2.timer
int_gen1.output >>= printer.input_int1
int_gen2.output >>= printer.input_int2

coor.execute()
```

When we execute this example with `python tests/examples/parallel_timed.py`, notice how the two inputs are always synchronized since the timers are aligned. Rosia handles synchronization internally so you don't have to worry about it!


## Contributing
### Install Pre-commit Hooks
```bash
pip install pre-commit
pre-commit install --hook-type commit-msg --hook-type pre-push
pre-commit run --all-files
```
Code is automatically formatted before committing. Commit messages should follow conventional commit.