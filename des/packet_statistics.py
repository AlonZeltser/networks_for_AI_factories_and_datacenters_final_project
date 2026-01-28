"""Streaming packet statistics - computed without storing packets."""

from dataclasses import dataclass


@dataclass
class PacketStatistics:
    """Accumulates packet statistics incrementally without storing packet objects.

    This enables memory-efficient simulation runs with millions of packets.
    Statistics are updated as packets are created, delivered, or dropped.
    """

    total_count: int = 0
    delivered_count: int = 0
    dropped_count: int = 0

    # Route length statistics
    route_length_sum: int = 0
    route_length_min: int = 999999
    route_length_max: int = 0

    def record_created(self) -> None:
        """Called when a packet is created."""
        self.total_count += 1

    def record_delivered(self, route_length: int) -> None:
        """Called when a packet is successfully delivered."""
        self.delivered_count += 1
        self.route_length_sum += route_length
        if route_length < self.route_length_min:
            self.route_length_min = route_length
        if route_length > self.route_length_max:
            self.route_length_max = route_length

    def record_dropped(self) -> None:
        """Called when a packet is dropped."""
        self.dropped_count += 1

    @property
    def avg_route_length(self) -> float:
        """Average route length of delivered packets."""
        return (
            self.route_length_sum / self.delivered_count
            if self.delivered_count > 0
            else 0.0
        )

    @property
    def min_route_length(self) -> int:
        """Minimum route length of delivered packets."""
        return self.route_length_min if self.route_length_min != 999999 else 0

    @property
    def max_route_length(self) -> int:
        """Maximum route length of delivered packets."""
        return self.route_length_max
# packet_statistics.py placeholder
