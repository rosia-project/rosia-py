---
sidebar_position: 1
---

# Time

## Time Representation

Rosia uses the discrete time model. In `rosia/time/Time.py`, all time values are represented by a int value. Each nanosecond is subdivided into `TIME_DIVISOR = 1000` microsteps. Rosia provides built-in time units `s`, `ms`, `us` and `ns`:

- 1 `ns` = 1000 microsteps
- 1 `us` = 1000 `ns`
- 1 `ms` = 1000 `us`
- 1 `s` = 1000 `ms`

All time values are treated as intervals, so you can add, subtract and multiply time. For example, to denote an interval of 3 seconds, you can use `3 * s`.

There's also `never` that represents the smallest time value, and `forever` that represents the largest time value. Adding or subtracting time to `never` and `forever` will yield `never` or `forever`.

## Logical Time

For every message, there is a timestamp associated with the message assigned by the sender.

Logical time is used to synchronize messages from different ports. If a reaction has two input ports, Rosia will guarantee that every time the reaction is triggered, all input ports have the same logical time.

## Physical Time

Physical time is the current clock time since Unix epoch, converted into Rosia's `Time` format.
