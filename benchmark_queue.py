"""Benchmark comparison: RingBuffer vs deque performance."""

import time
from collections import deque
from network_simulation.ring_buffer import RingBuffer


def benchmark_deque(n_operations: int, iterations: int = 5) -> float:
    """Benchmark deque append/popleft operations."""
    times = []
    for _ in range(iterations):
        d = deque()
        start = time.perf_counter()
        for i in range(n_operations):
            d.append(i)
        for i in range(n_operations):
            d.popleft()
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    return sum(times) / len(times)


def benchmark_ring_buffer(n_operations: int, iterations: int = 5) -> float:
    """Benchmark RingBuffer append/popleft operations."""
    times = []
    for _ in range(iterations):
        rb = RingBuffer(n_operations + 100)
        start = time.perf_counter()
        for i in range(n_operations):
            rb.append(i)
        for i in range(n_operations):
            rb.popleft()
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    return sum(times) / len(times)


def benchmark_mixed_operations(n_operations: int, iterations: int = 5):
    """Benchmark mixed append/popleft (more realistic simulation pattern)."""
    # Pattern: append some, pop some, repeat (simulating packet flow)

    # deque
    deque_times = []
    for _ in range(iterations):
        d = deque()
        start = time.perf_counter()
        for batch in range(n_operations // 100):
            for i in range(100):
                d.append(i)
            for i in range(50):
                d.popleft()
        # drain remaining
        while d:
            d.popleft()
        elapsed = time.perf_counter() - start
        deque_times.append(elapsed)

    # ring buffer
    rb_times = []
    for _ in range(iterations):
        rb = RingBuffer(n_operations)
        start = time.perf_counter()
        for batch in range(n_operations // 100):
            for i in range(100):
                rb.append(i)
            for i in range(50):
                rb.popleft()
        # drain remaining
        while rb:
            rb.popleft()
        elapsed = time.perf_counter() - start
        rb_times.append(elapsed)

    return sum(deque_times) / len(deque_times), sum(rb_times) / len(rb_times)


def benchmark_len_check(n_operations: int, iterations: int = 5):
    """Benchmark __len__ and __bool__ calls (used in while loops)."""

    # deque
    deque_times = []
    for _ in range(iterations):
        d = deque()
        for i in range(1000):
            d.append(i)
        start = time.perf_counter()
        for _ in range(n_operations):
            _ = len(d)
            _ = bool(d)
        elapsed = time.perf_counter() - start
        deque_times.append(elapsed)

    # ring buffer
    rb_times = []
    for _ in range(iterations):
        rb = RingBuffer(2000)
        for i in range(1000):
            rb.append(i)
        start = time.perf_counter()
        for _ in range(n_operations):
            _ = len(rb)
            _ = bool(rb)
        elapsed = time.perf_counter() - start
        rb_times.append(elapsed)

    return sum(deque_times) / len(deque_times), sum(rb_times) / len(rb_times)


if __name__ == "__main__":
    print("=" * 60)
    print("RingBuffer vs deque Performance Comparison")
    print("=" * 60)

    for n in [1000, 10000, 100000]:
        print(f"\n--- {n:,} operations ---")

        deque_time = benchmark_deque(n)
        rb_time = benchmark_ring_buffer(n)
        ratio = rb_time / deque_time

        print(f"Sequential append+popleft:")
        print(f"  deque:      {deque_time*1000:.3f} ms")
        print(f"  RingBuffer: {rb_time*1000:.3f} ms")
        print(f"  Ratio (RB/deque): {ratio:.2f}x")

    print(f"\n--- Mixed operations (100k) ---")
    deque_time, rb_time = benchmark_mixed_operations(100000)
    ratio = rb_time / deque_time
    print(f"  deque:      {deque_time*1000:.3f} ms")
    print(f"  RingBuffer: {rb_time*1000:.3f} ms")
    print(f"  Ratio (RB/deque): {ratio:.2f}x")

    print(f"\n--- len/bool checks (1M) ---")
    deque_time, rb_time = benchmark_len_check(1000000)
    ratio = rb_time / deque_time
    print(f"  deque:      {deque_time*1000:.3f} ms")
    print(f"  RingBuffer: {rb_time*1000:.3f} ms")
    print(f"  Ratio (RB/deque): {ratio:.2f}x")

    print("\n" + "=" * 60)
    print("Conclusion: If ratio > 1.0, RingBuffer is slower than deque")
    print("=" * 60)
