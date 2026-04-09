---
sidebar_position: 6
---

# Logical Time

In Rosia, _logical time_ is the timestamp system used for ordering and synchronization. It is up to you to control logical time within each node, and Rosia will take care of execution and synchronization across nodes.

Logical time is a monotonically increasing value. You can think of it as an order specification for messages and code execution. A message with a smaller logical time will be processed with a reaction before a message with a large logical
time.

Messages with the same logical time are considered simultaneous. As shown in example [Synchronization](tutorial/synchronization), if multiple input ports have the same logical time, they will be synchronized to only trigger the reaction
once.

Each node has logical time `Time(0)` when `start()` is called at the beginning of execution. The logical time can be manipulated in `start()` and reactions marked with `@reaction()` annotator in the following ways:

- `yield <Time>` pauses the current reaction, and resumes after the specified logical time interval. In the meantime, it will process other reactions.
- When a reaction is triggered by reacting to input ports defined in `@reaction(<ports>)`, the node will advance logical time to the logical time associated with the message received at the input port.

# Safe To Advance To (STAT)

Apart from logical time, each node also maintains a Safe To Advance To(STAT) time value. STAT acts as a safeguard for the increase of logical time: the node's logical time is only allowed to advance to $t \lt \text{STAT}$. For eager
reactions (see below), the bound is relaxed to $t \leq \text{STAT}$.

By default, STAT is set to `forever`, meaning that the logical time can grow whenever it wants. Consider a reaction triggered by two input ports A and B. If A receives a message with logical time $t_A$, the node will immediately advance to
$t_A$ since $t_A \lt \text{STAT}=\text{forever}$. Now the node receives another message with logical time $t_B \leq t_A$ and this will cause a problem since we now have to go backwards in time to process the new message.

This can be solved with STAT. If we know $t_B$ in advance and set STAT to $t_B$, since $t_B \leq t_A$, when we receive the message on port A, we know that we cannot process it yet since we have to wait for the message from $t_B$.

# Configuring STAT

A STAT can be set for each output port when sending an message. The API is

```python
self.output_port(<value>, STAT=<Time>)
```

Note that STAT is an interval instead of absolute time. The current logical time will be automatically added when sending STAT. One rule of thumb for setting STAT is to set it to the timestamp of the earliest next message(ENT, earliest next
timestamp). This will ensure that the downsteam will not advance it's logical time past the ENT, essencially waiting for this message before advancing to that logical time.

# Eager Reactions

In feedback loops (e.g., `A → B → A`), a normal `yield` can deadlock: the yield waits for STAT to advance strictly past the target time, but STAT depends on a message that can only be sent after the yield returns. This is a **causality
loop**.

`@reaction([...], eager=True)` resolves this by relaxing the STAT bound from $t \lt \text{STAT}$ to $t \leq \text{STAT}$. This allows the reaction to resume when its yield target equals STAT exactly, breaking the circular dependency.

```python
@reaction([action_in], eager=True)
def on_action(self):
    frame = self.env.step(self.action_in)
    yield self.dt                          # resumes when STAT >= dt (inclusive)
    self.observation(frame, STAT=self.dt)
```

See [Simulation](simulation.md) for a full example.
