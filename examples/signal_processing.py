"""Signal processing pipeline visualized with rerun.

Pipeline:
  Timer -> SineGenerator -> NoisyChannel -> LowPassFilter -> Printer

Each node produces a Scalar value with a `to_rerun()` method, so the
rerun viewer shows live plots of the clean sine, noisy signal, and
filtered output side-by-side.
"""

import numpy as np
import rerun as rr
import rerun.blueprint as rrb

from rosia import InputPort, OutputPort, reaction, Node, Application, request_shutdown, log
from rosia.time import Timer, Time, s, ms


class Scalar:
    """A single float value that can be streamed to rerun."""

    def __init__(self, value: float) -> None:
        self.value = value

    def to_rerun(self) -> rr.Scalars:
        return rr.Scalars(self.value)

    def __repr__(self) -> str:
        return f"{self.value:.4f}"


@Node
class SineGenerator:
    """Produces a clean sine wave, one sample per tick."""

    tick = InputPort[Time]()
    output = OutputPort[Scalar]()

    def __init__(self, frequency: float = 0.5, amplitude: float = 1.0):
        self.frequency = frequency
        self.amplitude = amplitude
        self.sample = 0

    @reaction([tick])
    def generate(self):
        t = self.sample * 0.1  # 0.1 s per sample
        value = self.amplitude * np.sin(2 * np.pi * self.frequency * t)
        self.output(Scalar(float(value)))
        self.sample += 1


@Node
class NoisyChannel:
    """Adds Gaussian noise to the signal."""

    input_signal = InputPort[Scalar]()
    output_signal = OutputPort[Scalar]()

    def __init__(self, noise_std: float = 0.3):
        self.noise_std = noise_std

    @reaction([input_signal])
    def add_noise(self):
        clean = self.input_signal.value
        noisy = clean + np.random.normal(0, self.noise_std)
        self.output_signal(Scalar(float(noisy)))


@Node
class LowPassFilter:
    """Exponential moving average filter."""

    input_signal = InputPort[Scalar]()
    output_signal = OutputPort[Scalar]()

    def __init__(self, alpha: float = 0.2):
        self.alpha = alpha
        self.state: float | None = None

    @reaction([input_signal])
    def filter(self):
        x = self.input_signal.value
        if self.state is None:
            self.state = x
        else:
            self.state = self.alpha * x + (1 - self.alpha) * self.state
        self.output_signal(Scalar(float(self.state)))


@Node
class Printer:
    """Logs the final filtered value."""

    input_signal = InputPort[Scalar]()

    def __init__(self, max_samples: int = 100):
        self.count = 0
        self.max_samples = max_samples

    @reaction([input_signal])
    def print_value(self):
        log.info(f"filtered = {self.input_signal}")
        self.count += 1
        if self.count >= self.max_samples:
            request_shutdown()


if __name__ == "__main__":
    app = Application()

    timer = app.create_node(Timer(interval=100 * ms, offset=0 * s))  # 0.1s ticks
    sine = app.create_node(SineGenerator(frequency=0.5, amplitude=1.0))
    noise = app.create_node(NoisyChannel(noise_std=0.3))
    lpf = app.create_node(LowPassFilter(alpha=0.2))
    printer = app.create_node(Printer(max_samples=100))

    timer.output_timer >>= sine.tick
    sine.output >>= noise.input_signal
    noise.output_signal >>= lpf.input_signal
    lpf.output_signal >>= printer.input_signal

    app.diagram()
    rr.send_blueprint(
        rrb.Blueprint(
            rrb.Horizontal(
                rrb.TimeSeriesView(origin="/"),
            )
        )
    )
    app.execute(trace=True, log_level="INFO")
