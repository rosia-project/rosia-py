---
sidebar_position: 5
---

# Architecture

Rosia is designed to be distributed. Since performance is one of our primary goals, we rely on a minimal coordination mechanism.

## Executor

Each node is run in a separate process with `Executor`. Currently distributed execution is not yet supported, but we will add it in the near future.

## Transport

Nodes communicate with each other via ZeroMQ transports. This enables fast communication and zero-copy support when processes are on the same machine. Currently we use the ZeroMQ pipeline push / pull pattern.

## Serializer

Python objects are first serialized into bytes with `cloudpickle` before sending through the transport, and deserialized at the receiving node. The architecture is not tied to any specific serializer, and we intend to add support for custom
serializers.

## Ports

Each node can have several input ports and output ports. However, for performance reasons, all input ports share the same ZeroMQ PULL endpoint, and each output port has its own ZeroMQ PUSH endpoint.

## Synchronization

There is no central coordinator for logical-time advancement. Each node decides locally how far it can advance based on a `Dict[str, Time]` of [ENTs](../handbook/STAT) — the earliest next emission timestamp of every transitive upstream
node. Each outgoing message carries this dict; receivers merge it into their own and recompute STAT. The transitive upstream set and the minimum delay along any path from each upstream are computed once at startup via a Bellman-Ford-style
BFS, so STAT is just a `min` over those entries at runtime.
