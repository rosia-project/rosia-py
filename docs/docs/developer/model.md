---
sidebar_position: 2
---

# Model of Computation

Rosia is a variant of the [reactor model of computation](https://reactor-model.org/). It uses a decentralized coordination method for minimal coordination. This documentation discuesses the _desired behavior_ of Rosia, and it's
implementation details will be discussed in other chapters.

## Node Lifecycle

Each node in Rosia is a _reactive_ state machine; state transitions are always triggered externally by other nodes.

```python
@Node
class RosiaNode:
    input_port_1 = InputPort[type]()
    input_port_2 = InputPort[type]()
    output_port_1 = OutputPort[type]()
    output_port_2 = OutputPort[type]()

    def __init__():
        # This function is called before startup

    def start():
        # This function is called at startup

    @reaction([input_port_1, input_port_2])
    def RosiaReaction():
        print(self.input_port_1)
        print(self.input_port_2)

    def shutdown():
        # This function is called at shutdown
```

There are four stages in a Rosia node's lifecycle. Lifecycles between nodes are synced automatically by the coordinator. It is not expected behavior that two nodes are in different states in the lifecycle.

- **Initialize**: The `__init__` function is executed during the setup stage, before the application actually runs. This is used to load models, setup ENT, etc. Nodes are not expected to send data to each other at this stage.
- **Startup**: After the setup stage, the application starts running. The `start` function is always the first function called in a node during execution.
- **Exection**: Any node marked with `@reaction` will be triggered by the framework if a new message arrives on the ports that the function is marked to react to.
- **Shutdown**: The `shutdown` function will be automatically triggered by the framework at the time designated by `request_shutdown()`.

## Coordination

Nodes can communicate with each other via `InputPort` and `OutputPort`. To do so, first setup a group of nodes coordinated by the `Coordinator`, then connect output ports to input ports using the `>>=` operator.

```python
coor = Coordinator()
node1 = coor.create_node(Node())
node2 = coor.create_node(Node())
node1.output_port_1 >>= node2.input_port_1
...
```

## Node Logical Time

In Rosia, the rule of thumb for synchronization is that messages with the same timestamp will be processed at the same time (if ENT is configured correctly).

Each node maintains two logical times:

- Logical Time $t_{node}$: the logical time of the node. This is the timestamp of the messages that is currently being processed.
- Safe To Advance Time (STAT) $g_{node}$: the node is not waiting for any messages with timestasmp $t < g_{node}$, and is safe to process any messages with timestamp $t < g_{node}$.

Each node has a logical time that initially from $t_{node}$ = `never`, and $g_{node}$ = `forever`. This means that the node has logical time is capable of advancing to any time upon request. When `start`, all nodes advance to logical
time 0.

There are two ways for a node to advance it's logical time.

1. Reaction trigger. To process messages with a bigger timestamp than $t_{node}$, the node will advance it's logical time $t_{node}$.
2. Advance Time API. `rosia.advance_time(t')` will advnace logical time to $t_{node} =  t_{node}+ t'$

It is not always possible to advance time immediately. The node might have to process more events, or wait for messages before advancing time.

If $t_{node} = t_1$, and $t_{node}$ tries to advance to $t_2$, the requirement is that $t_2$ must be smaller than STAT: $t_{node} = t_1 < t_2 < g_{node}$.

When this is not satisfied, there are two ways to imcrease STAT:

1. Process more events on the event queue.
2. Wait for messages, and process more events.

STAT can be computed from node state. Each node maintains two queues:

- Message Queue: this is maintained by the transport layer.
- Event Queue: ordered by timestamp, every event maps to a set of messages.

STAT is the minimum of:

1. The minimum ENT of all upstream ports of all input ports.
2. The minimum timestamp on the event queue.

So the STAT should be updated when

1. After a event is processed.
2. After a message queue received a new message (potentially different ENT)

## Node Synchronization

Synchronization is achieved via a simple API:

```python
@reaction([input_port_1, input_port_2])
def RosiaReaction():
    self.output_port_1(
        <message>,
        ENT=<Time>
    )
```

With each message that is sent out, two associated values are also sent: `timestamp` and `ENT`.

- **Timestamp**: the timestamp $t$ of the message, which is the same as logical time of the node.
- **Earliest Next Timestamp (ENT)**: an ENT of timestamp $g$ is a promise that this output port will not send another message with timestamp $t'$ < $g$. Since $t <= t'$ of the current message timestamp, this means $t < g$, and an error will
  be thrown otherwise.

ENT has a dual purpose. First, it tells the downstream node to not advance to time $t >= g$ and wait for a message from this port. On the other hand, it tells the downstream node that this port is not opposed to it advancing to any time
$t < g$.

Normally the user doesn't have to deal with setting `timestamp` and `ENT`. Rosia provides a `Timer` node that should cover most of normal uses cases. The user has to deal with setting these values if custom timing and syncronization is
required, for example, when creating a simulator node.

### ENT Inference

`timestamp` and `ENT` can be omitted by the user.

- `timestamp = None` and `ENT = None`: use the current logical time as `timestamp` and Safe to Advance Time (STAT) as `ENT`.
