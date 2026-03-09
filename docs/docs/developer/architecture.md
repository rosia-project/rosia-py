---
sidebar_position: 2
---

# Architecture

Rosia is designed to be distributed. Since performance is one of our primary goals, we rely on a minimal coordination mechenism.

## Executor

Each node is run in a separate process with `Executor`. Currently distributed execution is not yet supported, but we will add it in the near future.

## Transport

Nodes communicate with each other via ZeroMQ transports. This enables fast communication and zero-copy support when processes are on the same machine. Currently we use the ZeroMQ pipeline push / pull pattern.

## Serializer

Python object are first serilized into bytes with `cloudpickle` before sending through the transport, and deserialized at the receiving node. The architecture is not tied to any specific serializer, and we intend to add support for custom
serializers.

## Ports

Each node can have several input ports and output ports. However, for performance reasons, all input ports share the same ZeroMQ PULL endpoint, and each output port has it's own ZeroMQ PUSH endpoint.
