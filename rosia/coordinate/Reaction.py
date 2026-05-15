"""Reaction queue for scheduling and executing triggered reactions."""

import heapq
import inspect
import threading
from typing import Any, Callable, Optional, Generator

from rosia.time import Time
from rosia.coordinate.Events import TerminateReactionException


class Reaction:
    def __init__(
        self,
        function: Callable[..., Any] | Generator[Time, None, None],
        timestamp: Time,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self.generator: Optional[Generator[Time, None, None]] = None
        self.function: Optional[Callable[..., Any]] = None
        if isinstance(function, Generator):
            self.generator = function
        else:
            self.function = function
        self.timestamp = timestamp
        self.args = args
        self.kwargs = kwargs

    def execute(self) -> Optional["Reaction"]:
        if self.generator is not None:
            try:
                delta = next(self.generator)
                if not isinstance(delta, Time):
                    raise TypeError(f"Expected yield of Time, got {type(delta).__name__}: {delta}")
                target_time = self.timestamp + delta
                return Reaction(self.generator, target_time)
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
                        return Reaction(result, self.timestamp + delta)
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
        # Protects heap mutations. Triggers (see frontend.Annotators.trigger)
        # call enqueue from arbitrary threads, while the node event loop
        # dequeues and peeks. Lock is uncontended in the common single-thread
        # case but required for correctness when triggers are in use.
        self._lock = threading.Lock()

    def __getstate__(self) -> dict:
        # NodeRuntime is cloudpickled across to a worker process by the
        # executor; threading.Lock isn't picklable, so drop it and recreate
        # in __setstate__. The heap/counter are typed but always empty at
        # serialization time (this happens before execute()).
        state = self.__dict__.copy()
        state.pop("_lock", None)
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._lock = threading.Lock()

    def enqueue(self, reaction: Reaction, is_shutdown: bool = False) -> None:
        with self._lock:
            heapq.heappush(self._heap, (reaction.timestamp, self._counter, reaction, is_shutdown))
            self._counter += 1

    def dequeue(self) -> tuple[Optional[Reaction], bool]:
        with self._lock:
            if self._heap:
                _, _, reaction, is_shutdown = heapq.heappop(self._heap)
                return reaction, is_shutdown
            return None, False

    def peek_time(self) -> Optional[Time]:
        with self._lock:
            if self._heap:
                return self._heap[0][0]
            return None

    def has_pending(self) -> bool:
        with self._lock:
            return bool(self._heap)
