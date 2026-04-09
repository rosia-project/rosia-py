"""Reaction queue for scheduling and executing triggered reactions."""

import heapq
import inspect
from typing import Any, Callable, Optional, Generator

from rosia.time import Time
from rosia.coordinate.Events import TerminateReactionException


class Reaction:
    def __init__(
        self,
        function: Callable[..., Any] | Generator[Time, None, None],
        timestamp: Time,
        *args: Any,
        eager: bool = False,
        **kwargs: Any,
    ) -> None:
        self.generator: Optional[Generator[Time, None, None]] = None
        self.function: Optional[Callable[..., Any]] = None
        if isinstance(function, Generator):
            self.generator = function
        else:
            self.function = function
        self.timestamp = timestamp
        # Detect eager from the function's _rosia_eager attribute if not explicitly set
        if not eager and self.function is not None:
            eager = getattr(self.function, "_rosia_eager", False)
        self.eager = eager
        self.args = args
        self.kwargs = kwargs

    def execute(self) -> Optional["Reaction"]:
        if self.generator is not None:
            try:
                delta = next(self.generator)
                if not isinstance(delta, Time):
                    raise TypeError(f"Expected yield of Time, got {type(delta).__name__}: {delta}")
                target_time = self.timestamp + delta
                return Reaction(self.generator, target_time, eager=self.eager)
            except StopIteration:
                return None
            except TerminateReactionException:
                # The reaction is terminated normally. We don't need to enqueue it again.
                return None
        else:
            assert self.function is not None
            try:
                result = self.function(*self.args, **self.kwargs)
                if inspect.isgenerator(result):
                    try:
                        delta = next(result)
                        return Reaction(result, self.timestamp + delta, eager=self.eager)
                    except StopIteration:
                        return None
            except TerminateReactionException:
                return None
            return None


class ReactionQueue:
    """Priority queue of pending reactions, ordered by timestamp then FIFO.

    When an InputPortEvent is processed, its triggered reactions are
    enqueued here.  ``advance_to_STAT`` always drains this queue
    before popping the next event, guaranteeing that all reactions at
    timestamp T complete before any event at T' > T is processed.
    This keeps ``logical_time`` monotonically non-decreasing.
    """

    def __init__(self) -> None:
        self._heap: list[tuple[Time, int, Reaction, bool]] = []
        self._counter: int = 0

    def enqueue(self, reaction: Reaction, is_shutdown: bool = False) -> None:
        heapq.heappush(self._heap, (reaction.timestamp, self._counter, reaction, is_shutdown))
        self._counter += 1

    def dequeue(self) -> tuple[Optional[Reaction], bool]:
        if self._heap:
            _, _, reaction, is_shutdown = heapq.heappop(self._heap)
            return reaction, is_shutdown
        return None, False

    def peek_time(self) -> Optional[Time]:
        if self._heap:
            return self._heap[0][0]
        return None

    def peek_is_eager(self) -> bool:
        if self._heap:
            return self._heap[0][2].eager
        return False

    def has_pending(self) -> bool:
        return bool(self._heap)
