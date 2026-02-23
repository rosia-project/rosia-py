from rosia.frontend import OutputPort, Node
from rosia.time import Time
from rosia.time.utils import sleep_until_physical_time


@Node
class Timer:
    output_timer = OutputPort[Time]()

    def __init__(self, interval: Time, offset: Time = Time(0)):
        self.interval = interval
        self.time_current = offset
        self.output_timer.set_next_timestamp(self.time_current)

    def start(self, start_logical_time: Time):
        self.start_logical_time = start_logical_time
        while True:
            self.output_timer(
                self.time_current,
                timestamp=self.time_current,
                next_timestamp=self.time_current + self.interval,
            )
            self.time_current += self.interval
            sleep_until_physical_time(self.time_current + self.start_logical_time)
