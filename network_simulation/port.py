from __future__ import annotations

import logging
from collections import deque
from typing import Deque, TYPE_CHECKING

if TYPE_CHECKING:
    from network_simulation.link import Link
from network_simulation.packet import Packet

if TYPE_CHECKING:
    from network_simulation.network_node import NetworkNode


class Port:
    """A network node port with an egress queue.

    The NetworkNode decides *which* port to send on; the Port decides *when* it can
    hand the next queued packet to the Link.

    Current model:
    - The Link already tracks full-duplex availability via `next_available_time`.
    - The Port enforces FIFO ordering per port and schedules a drain attempt at the
      earliest time the attached link is available.
    """
    def __init__(self, id: int, owner:NetworkNode):
        self.port_id: int = id
        self.owner:NetworkNode = owner
        self.link: Link | None = None
        self.egress_queue: Deque[Packet] = deque()
        self.peak_queue_len: int = 0
        self._drain_scheduled: bool = False
        self.is_connected: bool = False

    def connect(self, link: Link) -> None:
        self.link = link
        self.is_connected = True


    def enqueue(self, packet: Packet) -> None:
        """Queue a packet for transmission and schedule a drain attempt."""
        if getattr(self.link, "failed", False):
            # Should normally be filtered by routing logic. But be defensive.
            packet.routing_header.dropped = True
            return

        self.egress_queue.append(packet)
        qlen = len(self.egress_queue)
        if qlen > self.peak_queue_len:
            self.peak_queue_len = qlen
        self._ensure_drain_scheduled()

    def queue_size(self) -> int:
        return len(self.egress_queue)

    def _ensure_drain_scheduled(self) -> None:
        if self._drain_scheduled:
            return
        self._drain_scheduled = True
        self.owner.scheduler.schedule_event(0.0, self._drain_once)

    def _drain_once(self) -> None:
        """Attempt to transmit exactly one packet, then reschedule if needed."""
        self._drain_scheduled = False

        if not self.egress_queue:
            return
        if getattr(self.link, "failed", False):
            # Drop everything queued if link fails.
            while self.egress_queue:
                self.egress_queue.popleft().dropped = True
            return

        now = self.owner.scheduler.get_current_time()
        link_index = self._link_index()
        next_avail = self.link.next_available_time[link_index]

        if next_avail > now:
            # Link busy in this direction. Try again exactly when it becomes free.
            self._drain_scheduled = True
            self.owner.scheduler.schedule_event(next_avail - now, self._drain_once)
            return

        packet = self.egress_queue.popleft()
        if self.owner.message_verbose:
            now = self.owner.scheduler.get_current_time()
            logging.debug(
                f"[sim_t={now:012.6f}s] Packet transmit    node={self.owner.name} port={self.port_id} packet_id={packet.tracking_info.global_id} link={self.link.name}"
            )

        self.link.transmit(packet, self)

        # If more messages waiting, schedule another attempt. Link.transmit updates
        # next_available_time, so we can schedule at that point for efficiency.
        if self.egress_queue:
            next_avail_after = self.link.next_available_time[link_index]
            delay = max(0.0, next_avail_after - self.owner.scheduler.get_current_time())
            self._drain_scheduled = True
            self.owner.scheduler.schedule_event(delay, self._drain_once)

    def _link_index(self) -> int:
        assert self.link.port1 is not None and self.link.port2 is not None
        if self == self.link.port1:
            return 0
        if self == self.link.port2:
            return 1
        raise AssertionError("Port must be connected to its link")

    def get_link(self) -> Link | None:
        return self.link
