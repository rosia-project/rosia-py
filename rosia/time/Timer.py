from rosia.frontend import OutputPort, Node
from rosia.time import Time


@Node
class Timer:
    output_timer = OutputPort[Time]()

    def __init__(self, interval: Time, offset: Time = Time(0)):
        self.interval = interval
        self.time_current = offset

    def start(self):
        yield self.time_current
        while True:
            self.output_timer(self.time_current)
            yield self.interval
            self.time_current += self.interval
