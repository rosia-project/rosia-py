---
sidebar_position: 4
---

# Node Execution

After startup completes, each node enters its main event loop. The loop processes incoming messages, recomputes STAT from upstream ENT updates, and fires reactions when it is safe to do so.

## Event loop

```
last_propagated_ENTs = build_outgoing_ENTs()   # baseline = current state
while True:
    drain_message_queue()
    update_STAT()

    current_ENTs = build_outgoing_ENTs()
    if current_ENTs != last_propagated_ENTs:
        send_messages()                        # eager ENT broadcast
        last_propagated_ENTs = build_outgoing_ENTs()

    if has_work:
        advance_to_STAT()
        last_propagated_ENTs = build_outgoing_ENTs()
    elif check_natural_shutdown():
        return
    else:
        wait_for_message()
```

The eager send after every drain is what enforces "all events at the same logical time are processed at the same logical time" across the network: as soon as our queue has new pending events (so our local ENT drops below `forever`),
downstream nodes learn about it immediately and refuse to advance past those timestamps.

A node has work when there is an event in the event queue or a reaction in the reaction queue with timestamp $t < \text{STAT}$.

## Message draining

`drain_message_queue()` pulls all available messages from the transport without blocking. Each message type is handled differently:

| Message type                        | Effect                                                                                                                                                                                                                                                                                 |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Message` (timestamped)             | Pushed to the event queue at the message's logical timestamp (if `data` is non-`None`). The attached ENT dict is merged into `self.ENTs`: the sender's own entry is overwritten (sender is authoritative); other entries are merged with `max`. `update_STAT()` runs after each merge. |
| `Message` (physical, no timestamp)  | Sets the input port value immediately and enqueues a reaction at the current logical time.                                                                                                                                                                                             |
| `NoMoreMessage`                     | Decrements `active_upstream_count` for the input port. When all of a direct upstream's connections to this node are done, sets that upstream's entry in `self.ENTs` to `forever`, so it stops constraining STAT and downstream learns about it via subsequent dict propagation.        |
| `ShutdownMessage`                   | Sets the shutdown barrier and pushes a `ShutdownEvent` at the shutdown timestamp. If the timestamp is already in the past, shuts down immediately.                                                                                                                                     |
| `ApplicationRequestShutdownMessage` | Part of shutdown negotiation. The node responds with the later of its current logical time and the requested time.                                                                                                                                                                     |

## STAT computation

`update_STAT()` recomputes STAT from the transitive upstream ENT dict:

$$
\text{STAT} \;=\; \min\Bigl(\min_{X \in \text{upstream}(\text{self})}\bigl(\text{ENTs}[X] + d(X \to \text{self})\bigr),\;\text{shutdown\_time\_barrier}\Bigr)
$$

`upstream(self)` is computed once during `_compute_upstream_topology()` at init time via a Bellman-Ford-style BFS. It includes every transitive upstream node (excluding `self`) and the minimum total delay along any path. An entry defaults
to `never` if no upstream message has yet reported it, so STAT starts at `never` and advances as upstream nodes broadcast their ENTs.

## ENT computation

`_compute_self_ENT()` returns the smallest of:

- `event_queue.peek_data_time()` — earliest unprocessed input event.
- `reaction_queue.peek_time()` — earliest yield-scheduled reaction.
- `self.STAT` — earliest possible incoming external event, **only included when `self.in_cycle` is `False`**.

The cycle exclusion is what breaks the chase pattern in feedback loops. If `self` is part of a cycle, `STAT` itself depends recursively on `self`'s ENT through the loop, so including it would make ENT increase by the cycle delay on every
round-trip. Restricting to the queue values lets the node with the real schedule (the one that yields a long delay) drive the cycle's pace.

For nodes outside any cycle, the STAT inclusion makes a passive relay (no yield) propagate its source's chain bound, so multi-input downstream receivers wait for the chain to catch up.

The result is bumped up to `self.logical_time` if it would otherwise be in the past.

## ENT propagation

Every outgoing message carries `ENTs = build_outgoing_ENTs()`, which is the node's own ENT plus everything it has learned from upstream. This dict propagation is what lets a downstream node know about ENTs of indirect upstream nodes — the
ones it doesn't directly receive from. Without it, a chain like `Source → Relay → Sink` would leave `Sink` unable to learn `Source`'s real ENT (the relay reports `forever` after each pass).

## Advancing to STAT

`advance_to_STAT()` processes events and reactions whose timestamps fall within the STAT boundary. It loops through:

1. **Drain and update**: re-drain messages and recompute STAT (new messages may have arrived during processing).
2. **Pick the next timestamp**: the earliest across both the event queue and reaction queue.
3. **Boundary check**: if the next timestamp is at or beyond STAT, return and wait.
4. **Advance logical time** to the chosen timestamp.
5. **Process events** at this timestamp:
   - `InputPortEvent`: sets port values from the event and collects the associated trigger functions.
   - `ShutdownEvent`: enqueues a shutdown reaction.
6. **Enqueue reactions** for every collected trigger function, **deduped across all iterations of this loop at the same timestamp** so a function fires at most once per logical timestamp even when its triggering events arrive in multiple
   drain batches.
7. **Execute reactions** at this timestamp.
8. **Update STAT and send messages** to broadcast the new ENT.

The cross-iteration trigger-function dedup is what stops cascading multi-firing in cycles: if a late-arriving event at the same logical time slips into the next iteration, its trigger function is recognized as already having fired and is
skipped.

All reactions at timestamp $t$ complete before any event at $t' > t$ is processed, preserving causal order.

## Reaction execution

`execute_reactions()` dequeues and runs all reactions at a given timestamp:

- **Regular reactions**: the reaction's function is called on the node instance. If the function is a generator (uses `yield`), the yielded time delta determines when the reaction resumes — it is re-enqueued at `timestamp + delta`.
- **Shutdown reactions**: when a shutdown reaction is dequeued, `send_messages()` is called first to flush any pending output and ENT updates, then `shutdown()` is called and the node exits.

Reactions that raise `TerminateReactionException` are silently terminated without propagating the error.

## Physical messages

Physical messages (messages with no timestamp) bypass the event queue entirely. When a physical message arrives during `drain_message_queue()`, the input port value is set immediately and a reaction is enqueued at the node's current logical
time. This is used for out-of-band communication that does not participate in logical time ordering.
