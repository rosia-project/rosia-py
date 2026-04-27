---
sidebar_position: 2
---

# Safe To Advance To (STAT)

Each node maintains a **Safe To Advance To** (STAT) time. STAT is the upper bound on the node's logical clock: the node may only process events at $t < \text{STAT}$. Once STAT advances, more work becomes safe.

The framework derives STAT automatically from the topology and the runtime state of upstream nodes — there is no STAT to set in user code.

## Why STAT exists

Suppose a reaction is triggered by two input ports A and B. A message at timestamp $t_A$ has arrived on A. The node should not fire yet, because a message at timestamp $t_B \le t_A$ might still be in flight on B. STAT is the mechanism that
forces the node to wait until both messages have either arrived or are guaranteed not to come.

Concretely, STAT is computed as

$$
\text{STAT} \;=\; \min_{X \in \text{upstream}(\text{self})} \bigl(\text{ENT}[X] + d(X \to \text{self})\bigr)
$$

where $\text{upstream}(\text{self})$ is the set of every node that can affect this node — including indirect upstreams reached through other nodes — and $d(X \to \text{self})$ is the smallest accumulated logical-time delay from $X$ to
$\text{self}$ along any path. The node itself is excluded from this set so that cycles do not pin STAT to the node's own future emission time.

## Earliest Next Timestamp (ENT)

Each node also maintains an **Earliest Next Timestamp** (ENT) — the smallest timestamp at which the node could produce a new message. ENT is computed from the node's local state:

- The earliest unprocessed event in its event queue.
- The earliest scheduled reaction in its reaction queue (from `yield`).
- For nodes outside any cycle, the node's own STAT is also a candidate (an external event could arrive at STAT and be emitted right away). Cycle members report only the queue-derived value, since their STAT depends on their own ENT through
  the loop.

If there is nothing in the queues, ENT is `forever`. If a queue value is in the past, ENT is bumped up to the current logical time.

ENT is **never** set by user code; it falls out of the node's queue contents.

## Propagation through messages

Every outgoing message from a node carries a dictionary of ENTs:

```
ENTs = { node_name: ENT[node_name], ... }
```

It contains the sender's own ENT plus every other ENT the sender has learned about. When a downstream node receives the message, it merges those entries into its own ENT dict. The sender's own entry is treated as authoritative
(overwritten); other entries are merged with `max` (newer-or-equal information only).

This dict propagation is what lets a downstream node know about ENTs of indirect upstreams — the relays it doesn't directly receive from.

## After-delay on a connection

When a connection has an after-delay $d$, a message sent at logical time $t$ is delivered at $t + d$. The delay is also folded into the receiver's STAT calculation: a transitive upstream $X$ that reaches `self` along a path with total delay
$d$ contributes $\text{ENT}[X] + d$ to `self`'s STAT.

For closing a feedback loop without advancing physical-time-aligned logical time, use a microstep delay (`delay=1`). See [Logical Time](logical_time#after-delays-on-connections).

## What this means for user code

In practice you almost never think about STAT:

- A node that yields (e.g. `yield 5 * ms`) advertises its next reaction time through ENT automatically. Downstream nodes wait until that time.
- A passive relay (a `@reaction` that does not yield) propagates its upstream's ENT through the dict, so any further-downstream node still blocks on the chain's earliest source. No annotation needed.
- A feedback loop with a yield in the loop (e.g. a control-loop period) advances at the rate of that yield, not at the rate of the loop's closure delay.

The only knob you need to turn is the after-delay on connections — and even that is only required to break cycles or model real propagation latency.
