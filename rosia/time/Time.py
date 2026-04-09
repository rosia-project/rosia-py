TIME_DIVISOR = 1000


class Time:
    def __init__(
        self,
        value: int,
    ):
        self.value = value

    def to_seconds(self) -> float:
        return self.value / s.value

    def to_unix_time(self) -> float:
        return self.value / (TIME_DIVISOR * 1e9)

    @staticmethod
    def from_unix_time(unix_time: float) -> "Time":
        return Time(int(unix_time * TIME_DIVISOR * 1e9))

    def __add__(self, other) -> "Time":
        assert isinstance(other, Time), "Cannot add Time to non-Time"
        if other == never or self == never:
            return never
        if other == forever or self == forever:
            return forever
        return Time(self.value + other.value)

    def __sub__(self, other) -> "Time":
        assert isinstance(other, Time), "Cannot subtract Time from non-Time"
        if other == never or self == never:
            return never
        if other == forever or self == forever:
            return forever
        return Time(self.value - other.value)

    def __mul__(self, other) -> "Time":
        raise ValueError("Cannot multiply Time by Time")

    def __rmul__(self, other) -> "Time":
        assert isinstance(other, int) or isinstance(other, float), "You can only multiply Time by int or float"
        if self == never:
            return never
        if self == forever:
            return forever
        assert other >= 0, "You can only multiply Time by non-negative int or float"
        return Time(int(other * self.value))

    def __lmul__(self, other) -> "Time":
        assert isinstance(other, int) or isinstance(other, float), "You can only multiply Time by int or float"
        assert other > 0, "You can only multiply Time by non-negative int or float"
        if self == never:
            return never
        if self == forever:
            return forever
        return Time(int(other * self.value))

    def __truediv__(self, other) -> "Time":
        assert isinstance(other, int) or isinstance(other, float), "You can only divide Time by int or float"
        assert other > 0, "You can only divide Time by non-negative int or float"
        if self == never:
            return never
        if self == forever:
            return forever
        return Time(int(self.value / other))

    def __floordiv__(self, other) -> "Time":
        assert isinstance(other, int) or isinstance(other, float), "You can only floor divide Time by int or float"
        assert other > 0, "You can only floor divide Time by non-negative int or float"
        if self == never:
            return never
        if self == forever:
            return forever
        return Time(int(self.value // other))

    def __le__(self, other) -> bool:
        assert isinstance(other, Time), "Cannot compare Time to non-Time"
        return self.value <= other.value

    def __lt__(self, other) -> bool:
        assert isinstance(other, Time), "Cannot compare Time to non-Time"
        return self.value < other.value

    def __ge__(self, other) -> bool:
        assert isinstance(other, Time), "Cannot compare Time to non-Time"
        return self.value >= other.value

    def __gt__(self, other) -> bool:
        assert isinstance(other, Time), "Cannot compare Time to non-Time"
        return self.value > other.value

    def __eq__(self, other) -> bool:
        assert isinstance(other, Time), f"Cannot compare Time to non-Time {other}"
        return self.value == other.value

    def __ne__(self, other) -> bool:
        assert isinstance(other, Time), "Cannot compare Time to non-Time"
        return self.value != other.value

    def __str__(self) -> str:
        if self == never:
            return "never"
        if self == forever:
            return "forever"
        if self >= s:
            return f"{self.value / s.value: .3f}s"
        elif self >= ms:
            return f"{self.value / ms.value: .3f}ms"
        elif self >= us:
            return f"{self.value / us.value: .3f}us"
        else:
            return f"{self.value / ns.value: .3f}ns"

    def __repr__(self):
        return self.__str__()

    def __hash__(self) -> int:
        return hash(self.value)


s = Time(1_000_000_000 * TIME_DIVISOR)
ms = Time(1_000_000 * TIME_DIVISOR)
us = Time(1_000 * TIME_DIVISOR)
ns = Time(1 * TIME_DIVISOR)
never = Time(-1)
forever = Time(int(1e18))

if __name__ == "__main__":
    x = 1 * s
    print(99 * s)
    print(99 * ms)
    print(99 * us)
    print(99 * ns)
    print(min(10 * s, 12 * s))
