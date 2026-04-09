import time
import numpy as np
import threading
import queue
from typing import List, Dict
from run_benchmarks import run_benchmark_loop_sync

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray, MultiArrayDimension, MultiArrayLayout


def pack_array_and_scalar(array: np.ndarray, multiplier: float) -> Float64MultiArray:
    """Pack array and scalar multiplier into a single message. Last element is the multiplier."""
    msg = Float64MultiArray()
    msg.layout = MultiArrayLayout(
        dim=[MultiArrayDimension(label="array_size", size=array.size, stride=array.size)],
        data_offset=0,
    )
    msg.data = array.ravel().tolist() + [multiplier]
    return msg


def unpack_array_and_scalar(msg: Float64MultiArray):
    """Unpack array and scalar multiplier from a single message."""
    n = msg.layout.dim[0].size
    data = np.array(msg.data, dtype=np.float64)
    return data[:n], data[n]


def numpy_to_msg(array: np.ndarray) -> Float64MultiArray:
    msg = Float64MultiArray()
    msg.layout = MultiArrayLayout(
        dim=[MultiArrayDimension(label="data", size=array.size, stride=array.size)],
        data_offset=0,
    )
    msg.data = array.ravel().tolist()
    return msg


def msg_to_numpy(msg: Float64MultiArray) -> np.ndarray:
    return np.array(msg.data, dtype=np.float64)


class ReceiverNode(Node):  # type: ignore
    def __init__(self):
        super().__init__("receiver_node")
        self.data_sub = self.create_subscription(
            Float64MultiArray,
            "array_data",
            self.data_callback,
            10,  # type: ignore
        )
        self.result_pub = self.create_publisher(
            Float64MultiArray,
            "array_result",
            10,  # type: ignore
        )

    def data_callback(self, msg: Float64MultiArray):  # type: ignore
        try:
            array, multiplier = unpack_array_and_scalar(msg)
            result = array * multiplier
            self.result_pub.publish(numpy_to_msg(result))
        except Exception as e:
            self.get_logger().error(f"Error processing data: {e}")


class SenderNode(Node):  # type: ignore
    def __init__(self):
        super().__init__("sender_node")
        self.result_queue: queue.Queue = queue.Queue()  # type: ignore
        self.data_pub = self.create_publisher(
            Float64MultiArray,
            "array_data",
            10,  # type: ignore
        )
        self.result_sub = self.create_subscription(
            Float64MultiArray,
            "array_result",
            self.result_callback,
            10,  # type: ignore
        )

    def result_callback(self, msg: Float64MultiArray):  # type: ignore
        self.result_queue.put(msg)  # type: ignore

    def send_and_receive(self, array: np.ndarray, multiplier: float, timeout: float = 5.0) -> np.ndarray:
        self.data_pub.publish(pack_array_and_scalar(array, multiplier))
        try:
            result_msg = self.result_queue.get(timeout=timeout)  # type: ignore
            return msg_to_numpy(result_msg)
        except queue.Empty:  # type: ignore
            raise TimeoutError("Timeout waiting for result")


def benchmark_rclpy(
    array_sizes: List[int], multiplier_value: float = 2.0, num_iterations: int = 10
) -> Dict[int, List[float]]:
    print("\n=== Benchmarking rclpy ===")

    if rclpy is None:
        print("rclpy not installed, skipping.")
        return {}

    try:
        rclpy.init()  # type: ignore
    except RuntimeError:
        pass

    receiver_node = ReceiverNode()  # type: ignore
    receiver_executor = rclpy.executors.SingleThreadedExecutor()  # type: ignore
    receiver_executor.add_node(receiver_node)
    receiver_thread = threading.Thread(  # type: ignore
        target=lambda: receiver_executor.spin(), daemon=True
    )
    receiver_thread.start()

    time.sleep(0.5)

    sender_node = SenderNode()  # type: ignore
    sender_executor = rclpy.executors.SingleThreadedExecutor()  # type: ignore
    sender_executor.add_node(sender_node)
    sender_thread = threading.Thread(  # type: ignore
        target=lambda: sender_executor.spin(), daemon=True
    )
    sender_thread.start()

    time.sleep(0.5)

    def call_fn(array: np.ndarray, multiplier: float) -> np.ndarray:
        try:
            return sender_node.send_and_receive(array, multiplier)
        except (TimeoutError, queue.Empty):  # type: ignore
            raise

    def warmup_fn(array: np.ndarray, multiplier: float):
        try:
            call_fn(array, multiplier)
        except (TimeoutError, queue.Empty):  # type: ignore
            pass

    def cleanup_fn():
        receiver_executor.shutdown()
        sender_executor.shutdown()
        receiver_node.destroy_node()
        sender_node.destroy_node()
        try:
            rclpy.shutdown()  # type: ignore
        except Exception as e:
            print(f"Error shutting down rclpy: {e}")

    return run_benchmark_loop_sync(
        array_sizes,
        multiplier_value,
        num_iterations,
        call_fn,
        warmup_fn=warmup_fn,
        cleanup_fn=cleanup_fn,
    )
