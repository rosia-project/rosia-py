---
sidebar_position: 4
---

# Node Execution

This document describes the internal execution design of a single Rosia node. For the model of computation and desired behavior, see [Model of Computation](model.md).

## Overview

Each node runs an independent execution loop that processes events in timestamp order. The core mechanism is:

1. Messages arrive on input ports via the transport layer.
2. Messages are organized into events on the event queue, ordered by timestamp.
3. The node advances its logical time and triggers reactions when it is safe to do so.

## Node State

Each node maintains the following state:

| Variable                | Type                            | Description                                                                                                                                                         | Initial Value    |
| ----------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| `logical_time`          | `Time`                          | The timestamp currently being processed ($t_{node}$).                                                                                                               | `Time(0)`        |
| `STAT`                  | `Time`                          | Safe To Advance To ($g_{node}$).                                                                                                                                    | `forever`        |
| `event_queue`           | `EventQueue`                    | Priority queue of events ordered by `(timestamp, priority)`. At the same timestamp, `InputPortEvent` (priority 0) is processed before `ShutdownEvent` (priority 1). | empty            |
| `input_port_connectors` | `Dict[str, InputPortConnector]` | Input ports on this node, keyed by name. Each input port tracks its own `safe_to_advance_to` as the min of the STATs of its upstream output ports.                  | from declaration |
| `shutdown_requested`    | `bool`                          | Whether shutdown has been requested.                                                                                                                                | `false`          |

## Node Functions

| Function                   | Description                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `__init__()`               | Constructs the `NodeRuntime`, creates port connectors and runtime objects from the node class annotations.                                                                                                                                                                                                                                                                                                                                        |
| `init_remote()`            | Sets up the receiver transport and logger.                                                                                                                                                                                                                                                                                                                                                                                                        |
| `init_output_transports()` | Creates sender transports to downstream nodes.                                                                                                                                                                                                                                                                                                                                                                                                    |
| `init_node_instance()`     | Calls the user's `__init__` on the node instance.                                                                                                                                                                                                                                                                                                                                                                                                 |
| `execute()`                | Entry point: calls `self.node_instance.start()`, then enters the main event loop. Calls `self.node_instance.shutdown()` after loop exits, then `sys.exit()`.                                                                                                                                                                                                                                                                                      |
| `drain_message_queue()`    | Drains transport into `event_queue`, updates port STATs. Creates `InputPortEvent` or `ShutdownEvent` objects.                                                                                                                                                                                                                                                                                                                                     |
| `update_STAT()`            | Computes STAT as min of input port `safe_to_advance_to` values.                                                                                                                                                                                                                                                                                                                                                                                   |
| `advance_to_STAT()`        | Processes events and reactions from queues up to STAT. For each `InputPortEvent`: sets port values, fires reactions, recomputes STAT, and sends STAT updates to affected output ports. Port values are retained (not cleared) so that each port always holds its most recent value. Returns early if a `ShutdownEvent` is encountered or if advancing would exceed STAT. For eager reactions, the STAT bound is inclusive ($t \leq \text{STAT}$). |
| `request_shutdown()`       | Sends a `ApplicationShutdownRequestMessage` to the coordinator.                                                                                                                                                                                                                                                                                                                                                                                   |

## Lifecycle Execution

The coordinator synchronizes lifecycle stages across all nodes via barriers. No node proceeds to the next stage until all nodes have completed the current stage.

### 1. Initialize

The user's `__init__` function runs before any communication. Nodes set up internal state, load models, and configure STAT defaults. No messages are sent or received.

### 2. Startup

The user's `start` function is the first function called during execution. `logical_time` is `Time(0)` at this point. Some nodes (e.g. Timer) run an infinite loop in `start()` and never enter the event loop — these nodes send messages with
explicit timestamps and receive shutdown via `drain_message_queue()` in the send path.

### 3. Execution (Main Loop)

The main loop drains messages, updates STAT, and processes events up to STAT. If no events are ready, it blocks waiting for new messages.

### 4. Shutdown

When `request_shutdown()` is called, the coordinator signals all nodes to shut down by sending a `ShutdownMessage`. In `drain_message_queue()`, this pushes a `ShutdownEvent` into the event queue. The node continues processing all events
with timestamps at or before the shutdown timestamp. When `advance_to_STAT` pops the `ShutdownEvent`, the shutdown reaction is enqueued and the main loop exits. Then `self.node_instance.shutdown()` is called and the process terminates.

For nodes running in `start()` (e.g. Timer), the send path calls `drain_message_queue()` and checks `shutdown_requested` before each send.

## Message Reception

Messages are drained from the transport layer and inserted into the event queue:

1. Receive a message from the transport.
2. If it is a `ShutdownMessage`, push a `ShutdownEvent` to the event queue.
3. Otherwise, update the STAT on the source output port and the `safe_to_advance_to` on the destination input port.
4. Push into the event queue via `event_queue.push_input_port_event()`, which merges with an existing `InputPortEvent` at the same timestamp. Sending multiple messages at the same timestamp from the same port raises an error.

## Event Queue

The event queue is a priority queue (`EventQueue`) backed by a min-heap (`heapq`), ordered by `(timestamp, priority)`.

The `EventQueue` class (defined in `rosia/coordinate/Events.py`) provides:

- `push_input_port_event(timestamp, port, value)` — merges into an existing `InputPortEvent` at the same timestamp, or creates a new one.
- `push_shutdown_event(timestamp, status_code)` — pushes a `ShutdownEvent`.
- `pop()` — removes and returns the event with the smallest `(timestamp, priority)`.
- `peek_time()` — returns the minimum timestamp without popping. Returns `forever` if empty.
- `peek_data_time()` — returns the minimum `InputPortEvent` timestamp, ignoring `ShutdownEvent`s. Used for STAT computation since STAT is a promise about future data messages, not system events.

There are two event types:

- **`InputPortEvent`** (priority 0): contains `input_port_values: Dict[InputPortConnector, Any]` — all messages that arrived at timestamp $t$. Multiple messages on different ports are merged into the same `InputPortEvent`.
- **`ShutdownEvent`** (priority 1): signals that the node should shut down at timestamp $t$. Contains `status_code: int` (0 for clean exit, non-zero for error).

## STAT Computation

STAT (Safe To Advance To) determines the maximum time the node can safely advance to. It is the minimum `safe_to_advance_to` across all input ports:

$$\text{STAT} = \min_{p \in \text{input\_ports}} p.\text{safe\_to\_advance\_time}$$

Each input port's `safe_to_advance_to` is the min of the STATs of its upstream output ports.

## Main Execution Loop

The main loop processes events in timestamp order, advancing logical time up to a given time. For each `InputPortEvent`, it sets port values, fires reactions, recomputes STAT, and sends STAT updates (using
`min(STAT, event_queue.peek_data_time())`) to affected output ports. If a `ShutdownEvent` is encountered, it sets `shutdown_requested` and returns.

## Sending Messages

When a node sends a message via an output port, the send path first drains the message queue and checks for shutdown. This is necessary for nodes that send from `start()` (e.g. Timer), which never enter the event loop and would otherwise
never receive shutdown messages. For nodes sending from reactions inside the event loop, the drain is redundant since it already happened at the top of the loop.

The `timestamp` is always the node's current `logical_time`. If STAT is not specified, it defaults to `min(STAT, event_queue.peek_data_time())` — the minimum of the upstream STAT constraint and the next pending data event.
`peek_data_time()` excludes `ShutdownEvent`s since STAT is a promise about future data, not system events.

## Reaction Triggering

A reaction fires during event processing if **any** of its trigger ports has a message in the current event. The reaction can read all input ports; ports without a message at the current timestamp return `None`.

Port values are **retained** after reactions execute — each port always holds its most recent value. A reaction can read any input port to get the latest value, even if that port was not part of the current event.
