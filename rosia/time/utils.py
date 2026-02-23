from rosia.time import Time, TIME_DIVISOR
import time
import ctypes
from ctypes.util import find_library

libc_path = find_library("c")
if not libc_path:
    raise OSError("Could not find the standard C library.")
libc = ctypes.CDLL(libc_path, use_errno=True)


def get_physical_time() -> Time:
    return Time(time.time_ns() * TIME_DIVISOR)


class Timespec(ctypes.Structure):
    _fields_ = [
        ("tv_sec", ctypes.c_long),  # Seconds
        ("tv_nsec", ctypes.c_long),  # Nanoseconds
    ]


libc.nanosleep.argtypes = [ctypes.POINTER(Timespec), ctypes.POINTER(Timespec)]
libc.nanosleep.restype = ctypes.c_int


def sleep_until_physical_time(target_physical_time: Time):
    while True:
        delta = target_physical_time - get_physical_time()
        if delta <= Time(0):
            break

        delta_unix = delta.to_unix_time()
        seconds = int(delta_unix)
        nanoseconds = int((delta_unix - seconds) * 1e9)
        req = Timespec(seconds, nanoseconds)
        rem = Timespec(0, 0)

        result = libc.nanosleep(ctypes.byref(req), ctypes.byref(rem))

        if result == 0:
            break
        print(f"Failed to sleep until physical time: {result}")
