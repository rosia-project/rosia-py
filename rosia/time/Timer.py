from rosia.frontend import OutputPort, Node
from rosia.time import Time
from rosia.time.utils import sleep_until_physical_time


@Node
class Timer:
    output_timer = OutputPort[Time]()

    def __init__(self, interval: Time, offset: Time = Time(0)):
        self.interval = interval
        self.time_current = offset

    def start(self, start_logical_time: Time):
        yield self.time_current
        while True:
            sleep_until_physical_time(self.time_current + start_logical_time)
            self.output_timer(self.time_current)
            yield self.interval
            self.time_current += self.interval
