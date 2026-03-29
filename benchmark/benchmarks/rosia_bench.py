import time
import json
import os
import numpy as np
from typing import List, Dict, Tuple

from rosia import (
    Node,
    InputPort,
    OutputPort,
    reaction,
    Application,
    request_shutdown,
    advance_time,
)
from rosia.time import ms, s


@Node
class Multiplier:
    input_data = InputPort[Tuple[np.ndarray, float]]()
    output_result = OutputPort[np.ndarray]()

    @reaction([input_data])
    def multiply(self):
        array, multiplier = self.input_data
        self.output_result(array * multiplier)


@Node
class Sender:
    result_in = InputPort[np.ndarray]()
    data_out = OutputPort[Tuple[np.ndarray, float]]()

    def __init__(
        self,
        array_sizes: List[int],
        multiplier_value: float,
        num_iterations: int,
        results_path: str,
        warmup_steps: int = 20,
    ):
        self.array_sizes = array_sizes
        self.multiplier_value = multiplier_value
        self.num_iterations = num_iterations
        self.results_path = results_path
        self.warmup_steps = warmup_steps
        self.all_results: Dict[int, List[float]] = {}
        self.result_received = False

    @reaction([result_in])
    def on_result(self):
        self.result_received = True

    def start(self):
        for size in self.array_sizes:
            array = np.random.rand(size).astype(np.float64)

            # Warmup
            for _ in range(self.warmup_steps):
                self.result_received = False
                self.data_out((array, self.multiplier_value))
                advance_time(1 * ms)

            times: List[float] = []
            for _ in range(self.num_iterations):
                self.result_received = False
                t0 = time.perf_counter()
                self.data_out((array, self.multiplier_value))
                advance_time(1 * ms)
                elapsed = time.perf_counter() - t0
                times.append(elapsed)

            self.all_results[size] = times
            avg = np.mean(times) * 1000
            std = np.std(times) * 1000
            print(f"  Size {size:>10}: {avg:.3f} ms ± {std:.3f} ms")

        os.makedirs(os.path.dirname(self.results_path), exist_ok=True)
        with open(self.results_path, "w") as f:
            json.dump({str(k): v for k, v in self.all_results.items()}, f, indent=2)
        print(f"  Results saved to {self.results_path}")
        request_shutdown(0 * s)


def benchmark_rosia(
    array_sizes: List[int], multiplier_value: float = 2.0, num_iterations: int = 10
) -> Dict[int, List[float]]:
    print("\n=== Benchmarking rosia ===")

    results_path = os.environ.get("RESULTS_DIR", "/results") + "/rosia_results.json"

    app = Application()
    sender = app.create_node(
        Sender(array_sizes, multiplier_value, num_iterations, results_path)
    )
    multiplier = app.create_node(Multiplier())

    sender.data_out >>= multiplier.input_data
    multiplier.output_result >>= sender.result_in

    app.execute()

    if os.path.exists(results_path):
        with open(results_path, "r") as f:
            raw = json.load(f)
        return {int(k): v for k, v in raw.items()}
    return {}
