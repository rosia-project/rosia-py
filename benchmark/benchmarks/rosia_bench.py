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
)


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
        self.array_sizes = list(array_sizes)
        self.multiplier_value = multiplier_value
        self.num_iterations = num_iterations
        self.results_path = results_path
        self.warmup_steps = warmup_steps
        self.all_results: Dict[int, List[float]] = {}

        self.size_idx = 0
        self.iteration = 0
        self.warmup = True
        self.times: List[float] = []
        self.t0 = 0.0
        self.current_array = np.empty(0)

    def start(self):
        self.current_array = np.random.rand(self.array_sizes[0]).astype(np.float64)
        if not self.warmup:
            self.t0 = time.perf_counter()
        self.data_out((self.current_array, self.multiplier_value))

    @reaction([result_in])
    def on_result(self):
        if self.warmup:
            self.iteration += 1
            if self.iteration >= self.warmup_steps:
                self.warmup = False
                self.iteration = 0
            if not self.warmup:
                self.t0 = time.perf_counter()
            self.data_out((self.current_array, self.multiplier_value))
            return

        elapsed = time.perf_counter() - self.t0
        self.times.append(elapsed)
        self.iteration += 1

        if self.iteration >= self.num_iterations:
            size = self.array_sizes[self.size_idx]
            self.all_results[size] = self.times
            avg = np.mean(self.times) * 1000
            std = np.std(self.times) * 1000
            print(f"  Size {size:>10}: {avg:.3f} ms ± {std:.3f} ms")

            self.size_idx += 1
            if self.size_idx >= len(self.array_sizes):
                self.save_results()
                return
            self.current_array = np.random.rand(self.array_sizes[self.size_idx]).astype(
                np.float64
            )
            self.warmup = True
            self.iteration = 0
            self.times = []

        if not self.warmup:
            self.t0 = time.perf_counter()
        self.data_out((self.current_array, self.multiplier_value))

    def save_results(self):
        os.makedirs(os.path.dirname(self.results_path), exist_ok=True)
        with open(self.results_path, "w") as f:
            json.dump({str(k): v for k, v in self.all_results.items()}, f, indent=2)
        print(f"  Results saved to {self.results_path}")
        request_shutdown()


def benchmark_rosia(
    array_sizes: List[int], multiplier_value: float = 2.0, num_iterations: int = 10
) -> Dict[int, List[float]]:
    print("\n=== Benchmarking rosia ===")

    default_results_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "results"
    )
    results_path = (
        os.environ.get("RESULTS_DIR", default_results_dir) + "/rosia_results.json"
    )

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
