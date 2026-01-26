# Network Simulator Optimization Suggestions

This document outlines performance optimization opportunities for the network simulator, prioritized by expected impact. All suggestions maintain single-threaded Python execution.

---

## 1. High Impact Optimizations

### 1.1 Use `__slots__` on Hot-Path Classes

**Problem:** Python dictionaries for instance attributes have memory and lookup overhead.

**Solution:** Add `slots=True` to frequently instantiated dataclasses (Python 3.10+):

```python
# packet.py
@dataclass(slots=True)
class FiveTupleExt:
    src_ip: str
    dst_ip: str
    # ... existing fields

@dataclass(slots=True)  
class Packet:
    routing_header: PacketL3
    transport_header: PacketTransport
    tracking_info: PacketTrackingInfo

# des.py
@dataclass(order=True, slots=True)
class DESEvent:
    time: float
    seq: int
    action: Callable[[], None] = field(compare=False)
```

**Note:** For dataclasses with `field(init=False)` computed attributes that need to be set in `__post_init__`, use `object.__setattr__(self, 'attr', value)` to bypass the slot restrictions.

**Impact:** 20-40% memory reduction, 10-20% faster attribute access for packet-heavy simulations.

---

### 1.2 Batch Logging Calls

**Problem:** Each `logging.debug/info` call has overhead even when disabled.

**Solution:** Guard log calls with level checks:

```python
# Instead of:
logging.debug(f"[sim_t={now:012.6f}s] Packet forwarding ...")

# Use:
if logging.getLogger().isEnabledFor(logging.DEBUG):
    logging.debug(f"[sim_t={now:012.6f}s] Packet forwarding ...")

# Or set logger level at module load:
_logger = logging.getLogger(__name__)
_DEBUG_ENABLED = _logger.isEnabledFor(logging.DEBUG)

# Then use:
if _DEBUG_ENABLED:
    _logger.debug(...)
```

**Impact:** 30-50% speedup when logging is at INFO level or higher (most production runs).

---

### 1.3 Avoid Repeated `get_current_time()` Calls

**Problem:** Multiple calls to `self.scheduler.get_current_time()` within the same event handler.

**Solution:** Cache the time at the start of event handling:

```python
# In NetworkNode.handle_message:
def handle_message(self):
    now = self.scheduler.get_current_time()  # Cache once
    while self.inbox:
        message = self.inbox.popleft()
        self.on_message(message, now)  # Pass as parameter

# In Port._drain_once:
def _drain_once(self) -> None:
    now = self.owner.scheduler.get_current_time()  # Use cached value throughout
    # ... rest of method uses `now` instead of repeated calls
```

**Impact:** 5-10% speedup in event processing.

---

## 2. Medium Impact Optimizations

### 2.1 Optimize IP Routing Table Lookups

**Problem:** Current LPM (Longest Prefix Match) scans all prefix lengths.

**Solution:** Use a trie or compressed radix tree for faster lookups:

```python
# Simple optimization: cache routing decisions per destination
class NetworkNode:
    def __init__(self, ...):
        # ... existing code
        self._routing_cache: dict[int, list[int]] = {}  # dst_ip_int -> port_indices
    
    def select_port_for_packet(self, packet: Packet) -> int | None:
        dst_int = packet.routing_header.five_tuple.dst_ip_int
        
        # Check cache first
        if dst_int in self._routing_cache:
            best_ports = self._routing_cache[dst_int]
        else:
            # Existing LPM logic...
            best_ports = self._compute_best_ports(dst_int)
            self._routing_cache[dst_int] = best_ports
        
        # ... rest of selection logic
```

**Impact:** 20-40% speedup in routing for repeated flows to same destinations.

---

### 2.2 Use `array.array` for Numeric Data

**Problem:** Python lists have per-element overhead.

**Solution:** For collections of integers/floats, use `array.array`:

```python
import array

# In Link:
class Link:
    def __init__(self, ...):
        # ... existing code
        # Instead of: self.next_available_time = [0.0, 0.0]
        self.next_available_time = array.array('d', [0.0, 0.0])
```

**Impact:** Minor memory savings, slight speedup for numeric operations.

---

### 2.3 Avoid `getattr()` with Default in Hot Paths

**Problem:** `getattr(obj, 'attr', default)` is slower than direct attribute access.

**Solution:** Use direct attribute access or `hasattr` checks:

```python
# Instead of:
if getattr(self.link, "failed", False):

# Use (if attribute always exists):
if self.link.failed:

# Or if you must check existence:
if hasattr(self.link, 'failed') and self.link.failed:
```

**Impact:** 5-10% speedup in packet forwarding paths.

---

### 2.4 Pre-compute Static Hash Values

**Problem:** `FiveTupleExt` computes hash via `xxhash.xxh64(str(self))` - string conversion is expensive.

**Solution:** Hash the tuple components directly:

```python
def __post_init__(self) -> None:
    self.src_ip_int = IPAddress.parse(self.src_ip).to_int()
    self.dst_ip_int = IPAddress.parse(self.dst_ip).to_int()
    # Hash numeric values directly instead of string conversion
    self._hash = hash((
        self.src_ip_int, self.dst_ip_int,
        self.src_protocol_port, self.dst_protocol_port,
        self.protocol.value, self.flowlet_field
    ))
```

**Impact:** 10-20% speedup in packet hashing (used for ECMP selection).

---

## 3. Lower Impact / Structural Optimizations

### 3.1 Lazy Packet Tracking

**Problem:** `PacketTrackingInfo` fields like `verbose_route` are always allocated.

**Solution:** Make tracking info optional and allocate only when needed:

```python
@dataclass
class Packet:
    routing_header: PacketL3
    transport_header: PacketTransport
    tracking_info: PacketTrackingInfo | None = None  # Only allocate when verbose
```

**Impact:** Memory reduction when verbose tracking is disabled.

---

### 3.2 Event Pool / Object Reuse

**Problem:** Each `DESEvent` is created and garbage collected.

**Solution:** Implement object pooling for `DESEvent`:

```python
class DESEventPool:
    __slots__ = ('_pool',)
    
    def __init__(self, initial_size: int = 1000):
        self._pool = [DESEvent(0.0, 0, lambda: None) for _ in range(initial_size)]
    
    def acquire(self, time: float, seq: int, action) -> DESEvent:
        if self._pool:
            event = self._pool.pop()
            event.time = time
            event.seq = seq
            event.action = action
            return event
        return DESEvent(time, seq, action)
    
    def release(self, event: DESEvent) -> None:
        event.action = None  # Allow callback GC
        self._pool.append(event)
```

**Impact:** Reduced GC pressure for long simulations with millions of events.

---

### 3.3 Use `bisect` for Priority Queue Alternatives

**Problem:** While `heapq` is good, for certain workloads calendar queues or bucket-based structures may be faster.

**Solution:** For simulations where event times cluster, consider a calendar queue:

```python
from collections import defaultdict
import bisect

class CalendarQueue:
    """Efficient for clustered event times."""
    
    def __init__(self, bucket_width: float = 1e-6):
        self.bucket_width = bucket_width
        self.buckets: dict[int, list] = defaultdict(list)
        self.min_bucket = float('inf')
    
    def enqueue(self, event):
        bucket_id = int(event.time / self.bucket_width)
        bisect.insort(self.buckets[bucket_id], event)
        self.min_bucket = min(self.min_bucket, bucket_id)
    
    def dequeue(self):
        while self.min_bucket < float('inf'):
            bucket = self.buckets.get(self.min_bucket)
            if bucket:
                return bucket.pop(0)
            self.min_bucket += 1
        raise IndexError("Empty queue")
```

**Impact:** Potentially 10-30% speedup for time-clustered workloads.

---

### 3.4 Compile Regex/Format Strings Once

**Problem:** f-strings are efficient, but the `_sim_time_prefix` helper is called repeatedly.

**Solution:** Pre-format common prefixes or use cached formatters:

```python
# Use a memoized version
from functools import lru_cache

@lru_cache(maxsize=10000)
def _format_time(t: float) -> str:
    return f"[sim_t={t:012.6f}s]"

def _sim_time_prefix(sim: DiscreteEventSimulator) -> str:
    return _format_time(sim.get_current_time())
```

**Impact:** Minor speedup for logging-heavy runs.

---

## 4. Profiling-Guided Optimizations

### 4.1 Add Profiling Hooks

Before implementing any optimization, measure actual bottlenecks:

```python
import cProfile
import pstats

# In main simulation runner:
def run_with_profiling(network):
    profiler = cProfile.Profile()
    profiler.enable()
    
    network.run()
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(30)  # Top 30 functions
```

### 4.2 Use `line_profiler` for Hot Functions

```bash
pip install line_profiler
```

```python
# Decorate hot functions:
@profile  # when running with kernprof
def select_port_for_packet(self, packet):
    ...
```

Run with: `kernprof -l -v script.py`

---

## 5. Memory Optimizations

### 5.1 Limit Packet History

**Problem:** `DiscreteEventSimulator.packets` stores ALL packets indefinitely.

**Solution:** Use a bounded collection or periodic cleanup:

```python
class DiscreteEventSimulator:
    def __init__(self, max_packet_history: int = 100_000):
        self.packets = deque(maxlen=max_packet_history)
        # ... or stream to disk for very large simulations
```

### 5.2 Intern Common Strings

**Problem:** Repeated string allocations for node names, IP addresses.

**Solution:** Use `sys.intern()` for frequently used strings:

```python
import sys

def create_host(self, name: str, ip_address: str, ...):
    name = sys.intern(name)
    ip_address = sys.intern(ip_address)
    # ...
```

---

## 6. Implementation Priority

Recommended implementation order based on effort vs. impact:

| Priority | Optimization | Effort | Impact | Status |
|----------|-------------|--------|--------|--------|
| 1 | Guard logging calls (1.2) | Low | High | ✅ Done |
| 2 | Cache routing decisions (2.1) | Low | High | |
| 3 | Cache current time (1.3) | Low | Medium | |
| 4 | Use `__slots__` (1.1) | Medium | High | ✅ Done |
| 5 | Optimize hash computation (2.4) | Low | Medium | |
| 6 | Remove getattr overhead (2.3) | Low | Medium | |
| 7 | Add profiling (4.1) | Low | Diagnostic | |
| 8 | Object pooling (3.2) | Medium | Medium | |
| 9 | Limit packet history (5.1) | Low | Memory | |

---

## 7. Benchmarking Recommendations

Create a standard benchmark suite:

```python
# benchmark.py
import time
from network_simulators.ai_factory_su_network_simulator import AIFactorySUNetworkSimulator

def benchmark_topology_creation():
    start = time.perf_counter()
    for _ in range(10):
        sim = AIFactorySUNetworkSimulator(...)
        sim.create(visualize=False)
    elapsed = time.perf_counter() - start
    print(f"Topology creation: {elapsed/10:.3f}s avg")

def benchmark_packet_processing():
    # Create topology, inject N packets, measure time
    ...

if __name__ == "__main__":
    benchmark_topology_creation()
    benchmark_packet_processing()
```

---

## Summary

The most impactful optimizations for a single-threaded Python DES are:

1. **Reduce logging overhead** - guards around log calls
2. **Cache routing decisions** - avoid repeated LPM lookups
3. **Use `__slots__`** - reduce memory and attribute access time
4. **Avoid repeated method calls** - cache `get_current_time()` values

Before implementing, **profile your specific workloads** to identify the actual hotspots. The 80/20 rule applies: 80% of time is often spent in 20% of the code.
