---
sidebar_position: 3
---

# Startup

There are two stages in rosia's coordinated startup: initialization and startup.

## Initialization

The initialization stage is orchestrated by the `Application.execute()` method. It sets up all nodes before execution begins. No inter-node communication happens during this stage. The steps are:

1. **Remote node setup**: For each node, the executor calls `init_remote()`, which sets up a ZeroMQ PULL endpoint for receiving messages and stores its endpoint string for other nodes to push to. `init_remote()` also runs
   `_compute_upstream_topology()`, which BFS-walks the upstream graph to collect every transitive upstream node and the minimum cumulative delay from each one to `self`. The same routine detects whether `self` is in a cycle (via a
   downstream BFS) and stores the result in `self.in_cycle`.

2. **Output transport initialization**: Each node is updated with the endpoints of all downstream nodes. ZeroMQ PUSH sockets are created for each output port connection, so nodes can send messages to their downstream recipients.

3. **Node instance initialization**: The user's `__init__` method is called on each node. Nodes load models, allocate resources, and set internal state. Nodes do not communicate during this step.

There is no separate STAT-propagation step. STAT is computed lazily during the event loop from the [ENT](../../handbook/STAT) entries that arrive in messages. A node's initial view of every transitive upstream's ENT defaults to `never`
(meaning "no information yet"), so its STAT is `never` until the first upstream message arrives.

## Startup

After initialization completes, all nodes begin execution simultaneously:

1. **Start logical time**: The coordinator records the current physical time as the start time and sends it to all nodes via `execute(start_logical_time)`.

2. **`start()` call**: If a node defines a `start()` method, it is called before the event loop begins. This is the first user-controlled function called during execution. Nodes can write to output ports in `start()`, and `start()` may
   yield to schedule a future reaction. Logical time is `Time(0)` throughout `start()`.

3. **Initial broadcast**: After `start()` returns, the node calls `send_messages()` only if it actually has something to broadcast — either an output value written during `start()` or a reaction scheduled by a `yield`. Nodes with neither
   (typical pure relays) skip the initial send. Their downstreams' default `ENT[self] = never` keeps STAT pinned until the node later receives an upstream message and naturally has something to report.

   Skipping the empty-startup broadcast prevents a relay from prematurely telling downstream "I have no scheduled work" before it has even drained its first upstream message. Without this, multi-input downstream receivers could race past
   pending events.
