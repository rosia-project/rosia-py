from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from rosia.time import Time

T = TypeVar("T")


class InputPort(Generic[T]):
    def __init__(self) -> None:
        self.name = None
        self.owner = None
        self.trigger_functions: List[Callable] = []
        self.affected_output_port_names: List[str] = []

    def __set_name__(self, owner: type, name: str) -> None:
        self.owner = owner
        self.name = name

    def __set__(self, args: List[Any], kwargs: Dict[str, Any]) -> None:
        raise TypeError("InputPort value is immutable")

    def _add_trigger_function(self, function: Callable) -> None:
        if function in self.trigger_functions:
            raise ValueError(f"Function {function} is already a trigger for {self.name}")
        self.trigger_functions.append(function)

    def __str__(self) -> str:
        return f"{self.owner}.{self.name}"

    # get the value of the port, this will be overridden in runtime, this is just to make the compiler happy
    def __get__(self, instance: Any, owner: type) -> T:  # type: ignore
        pass


class OutputPort(Generic[T]):
    def __init__(self) -> None:
        self.owner = None
        self.name = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.owner = owner
        self.name = name

    # () shorthand for send. The port object will be overridden in runtime, this is just to make the compiler happy
    def __call__(
        self,
        value: T,
        timestamp: Optional["Time"] = None,
        STAT: Optional["Time"] = None,
    ) -> None:
        pass

    # this is just to make the compiler happy. This function will never be called. Actual code is in rosia.coordinate.Port
    def connect(self, other: T) -> "OutputPort[T]":
        return self

    def set_STAT(self, first_timestamp: "Time") -> None:
        pass

    # >> shorthand for connect
    def __rshift__(self, other: T) -> "OutputPort[T]":
        return self.connect(other)

    # >>= shorthand for connect
    def __irshift__(self, other: T) -> "OutputPort[T]":
        return self.connect(other)

    def __ifloordiv__(self, other: T) -> "OutputPort[T]":
        return self.connect(other)
