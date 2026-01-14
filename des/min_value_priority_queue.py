import heapq
from typing import Any, List


class MinValuePriorityQueue:

    def __init__(self):
        self._heap: List[Any] = []

    def enqueue(self, item: Any) -> None:
        """Insert a new item into the queue."""
        heapq.heappush(self._heap, item)

    def dequeue(self) -> Any:
        """Pop and return the smallest item."""
        # Print only the 'time' attribute for events in the heap and the selected event
        """Helper function to extract time attribute if it exists."""
        """
        def _get_time(item: Any):
            try:
                return getattr(item, "time")
            except Exception:
                return item
        """

        # heap_times = [ _get_time(it) for it in self._heap ]
        result = heapq.heappop(self._heap)
        # selected_time = _get_time(result)
        # print("heap times:", heap_times)
        # print("selected time:", selected_time)
        return result

    def peek(self) -> Any:
        """Return the smallest item without removing it."""
        return self._heap[0] if self._heap else None

    def empty(self) -> bool:
        """True if the queue is empty."""
        return not self._heap

    def __len__(self) -> int:
        """Return number of elements."""
        return len(self._heap)

    def clear(self) -> None:
        """Remove all elements."""
        self._heap.clear()
