import itertools
from dataclasses import field, dataclass
from typing import Callable

# Use package-relative import so tests and imports from `infra` work correctly
from des.min_value_priority_queue import MinValuePriorityQueue


@dataclass(order=True)
class DESEvent:
    time: float
    seq: int
    action: Callable[[], None] = field(compare=False)


class DiscreteEventSimulator:

    def __init__(self):
        self.current_time = 0.0
        self.event_queue: MinValuePriorityQueue = MinValuePriorityQueue()
        self.scheduling_counter = itertools.count()
        self.packets = []
        self.end_time: float | None = None

    @property
    def messages(self):
        """Backward-compatible alias for `packets`."""
        return self.packets

    def schedule_event(self, delay: float, action: Callable[[], None]) -> None:
        """Schedule an event to occur after a certain delay."""
        assert delay >= 0
        event_time = self.current_time + delay
        event = DESEvent(event_time, next(self.scheduling_counter), action)
        self.event_queue.enqueue(event)

    def run(self) -> None:
        """Run the simulation until there are no more events."""
        while self.event_queue:
            event = self.event_queue.dequeue()
            self.current_time = event.time
            event.action()
        self.end_time = self.current_time

    def get_current_time(self) -> float:
        return self.current_time
