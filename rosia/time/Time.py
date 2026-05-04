class Time:
    def __init__(
        self,
        value: int,
        microstep: int = 0,
    ):
        self.value = value
        self.microstep = microstep

    def to_seconds(self) -> float:
        return self.value / s.value

    def to_unix_time(self) -> float:
        return self.value / (1e9)

    @staticmethod
    def from_unix_time(unix_time: float) -> "Time":
        return Time(int(unix_time * 1e9))

    def __add__(self, other) -> "Time":
        assert isinstance(other, Time), "Cannot add Time to non-Time"
        if other == never or self == never:
            return never
        if other == forever or self == forever:
            return forever
        return Time(self.value + other.value, self.microstep + other.microstep)

    def __sub__(self, other) -> "Time":
        assert isinstance(other, Time), "Cannot subtract Time from non-Time"
        if other == never or self == never:
            return never
        if other == forever or self == forever:
            return forever
        return Time(self.value - other.value, self.microstep - other.microstep)

    def __mul__(self, other) -> "Time":
        raise ValueError("Cannot multiply Time by Time")

    def __rmul__(self, other) -> "Time":
        assert isinstance(other, int) or isinstance(other, float), "You can only multiply Time by int or float"
        if self == never:
            return never
        if self == forever:
            return forever
        assert other >= 0, "You can only multiply Time by non-negative int or float"
        return Time(int(other * self.value), int(other * self.microstep))

    def __lmul__(self, other) -> "Time":
        assert isinstance(other, int) or isinstance(other, float), "You can only multiply Time by int or float"
        assert other > 0, "You can only multiply Time by non-negative int or float"
        if self == never:
            return never
        if self == forever:
            return forever
        return Time(int(other * self.value), int(other * self.microstep))

    def __truediv__(self, other) -> "Time":
        assert isinstance(other, int) or isinstance(other, float), "You can only divide Time by int or float"
        assert other > 0, "You can only divide Time by non-negative int or float"
        if self == never:
            return never
        if self == forever:
            return forever
        return Time(int(self.value / other), int(self.microstep / other))

    def __floordiv__(self, other) -> "Time":
        assert isinstance(other, int) or isinstance(other, float), "You can only floor divide Time by int or float"
        assert other > 0, "You can only floor divide Time by non-negative int or float"
        if self == never:
            return never
        if self == forever:
            return forever
        return Time(int(self.value // other), int(self.microstep // other))

    def __le__(self, other) -> bool:
        assert isinstance(other, Time), "Cannot compare Time to non-Time"
        return (self.value, self.microstep) <= (other.value, other.microstep)

    def __lt__(self, other) -> bool:
        assert isinstance(other, Time), "Cannot compare Time to non-Time"
        return (self.value, self.microstep) < (other.value, other.microstep)

    def __ge__(self, other) -> bool:
        assert isinstance(other, Time), "Cannot compare Time to non-Time"
        return (self.value, self.microstep) >= (other.value, other.microstep)

    def __gt__(self, other) -> bool:
        assert isinstance(other, Time), "Cannot compare Time to non-Time"
        return (self.value, self.microstep) > (other.value, other.microstep)

    def __eq__(self, other) -> bool:
        assert isinstance(other, Time), f"Cannot compare Time to non-Time {other}"
        return self.value == other.value and self.microstep == other.microstep

    def __ne__(self, other) -> bool:
        assert isinstance(other, Time), "Cannot compare Time to non-Time"
        return self.value != other.value or self.microstep != other.microstep

    def __str__(self) -> str:
        if self.value == never.value:
            return "never"
        if self.value == forever.value:
            return "forever"
        if self.value % s.value == 0:
            base = f"{self.value / s.value}s"
        elif self.value % ms.value == 0:
            base = f"{self.value / ms.value}ms"
        elif self.value % us.value == 0:
            base = f"{self.value / us.value}us"
        else:
            base = f"{self.value / ns.value}ns"
        if self.microstep != 0:
            return f"{base}+{self.microstep}"
        return base

    def __repr__(self):
        return self.__str__()

    def __hash__(self) -> int:
        return hash((self.value, self.microstep))


s = Time(1_000_000_000)
ms = Time(1_000_000)
us = Time(1_000)
ns = Time(1)
never = Time(-1)
forever = Time(int(1e18))

if __name__ == "__main__":
    x = 1 * s
    print(99 * s)
    print(99 * ms)
    print(99 * us)
    print(99 * ns)
    print(min(10 * s, 12 * s))
    print(Time(0, microstep=5))
    print(1 * s + Time(0, microstep=3))
