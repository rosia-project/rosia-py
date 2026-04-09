from dataclasses import dataclass, field
from functools import total_ordering
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import heapq
from rosia.time import Time, forever

if TYPE_CHECKING:
    from rosia.frontend.Connection import InputPortConnector


class TerminateReactionException(Exception):
    pass


@total_ordering
@dataclass
class Event:
    """Base event class. Lower priority value = processed first at the same timestamp."""

    timestamp: Time
    priority: int

    def __lt__(self, other: "Event") -> bool:
        if self.timestamp == other.timestamp:
            return self.priority < other.priority
        return self.timestamp < other.timestamp

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Event):
            return NotImplemented
        return self.timestamp == other.timestamp and self.priority == other.priority


@dataclass
class InputPortEvent(Event):
    priority: int = 0
    input_port_values: Dict["InputPortConnector[Any]", Any] = field(default_factory=dict)


@dataclass
class ShutdownEvent(Event):
    priority: int = 1
    status_code: int = 0


class EventQueue:
    """Priority queue of events ordered by (timestamp, priority).

    InputPortEvents at the same timestamp are merged automatically.
    At the same timestamp, InputPortEvent is processed before ShutdownEvent.

    Uses a heap for ordered extraction and a dict index for O(1) merge lookups.
    """

    def __init__(self) -> None:
        self._heap: List[Event] = []
        self._input_events: Dict[Time, InputPortEvent] = {}

    def push_input_port_event(self, timestamp: Time, input_port: "InputPortConnector[Any]", value: Any) -> None:
        existing = self._input_events.get(timestamp)
        if existing is not None:
            if input_port in existing.input_port_values:
                raise ValueError(
                    f"Duplicate message at timestamp {timestamp} for port {input_port.name}. "
                    f"A port cannot send multiple messages at the same timestamp."
                )
            existing.input_port_values[input_port] = value
            return
        event = InputPortEvent(
            timestamp=timestamp,
            input_port_values={input_port: value},
        )
        self._input_events[timestamp] = event
        heapq.heappush(self._heap, event)

    def push_shutdown_event(self, timestamp: Time, status_code: int = 0) -> None:
        heapq.heappush(self._heap, ShutdownEvent(timestamp=timestamp, status_code=status_code))

    def pop(self) -> Event:
        event = heapq.heappop(self._heap)
        if isinstance(event, InputPortEvent):
            self._input_events.pop(event.timestamp, None)
        return event

    def peek_time(self) -> Optional[Time]:
        if not self._heap:
            return None
        return self._heap[0].timestamp

    def peek_data_time(self) -> Time:
        """Earliest InputPortEvent timestamp, ignoring ShutdownEvents."""
        for event in self._heap:
            if isinstance(event, InputPortEvent):
                return event.timestamp
        return forever

    def __bool__(self) -> bool:
        return len(self._heap) > 0

    def __len__(self) -> int:
        return len(self._heap)
