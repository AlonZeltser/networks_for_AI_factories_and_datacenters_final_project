import logging
from typing import Optional

from des.des import DiscreteEventSimulator
from network_simulation.packet import Packet
from network_simulation.port import Port


class Link:
    def __init__(self, name: str, scheduler: DiscreteEventSimulator, bandwidth_bps: float,
                 propagation_time: float):
        self.name = name
        self.scheduler = scheduler
        self.bandwidth_bps = bandwidth_bps
        self.propagation_time = propagation_time
        self.next_available_time = [0.0, 0.0]  # in seconds, full duplex link
        self.port1: Port | None = None
        self.port2: Port | None = None
        # whether this link is failed (physically down). Default: False
        self.failed: bool = False

        # for statistics
        self.accumulated_transmitting_time: float = 0.0
        self.accumulated_bytes_transmitted: int = 0

    def connect(self, port: Port) -> None:
        if self.port1 is None:
            self.port1 = port
        elif self.port2 is None:
            self.port2 = port
        else:
            raise Exception("Link can only connect two nodes")

    def transmit(self, packet: Packet, sender: Port) -> None:
        assert self.port1 is not None and self.port2 is not None and (sender == self.port1 or sender == self.port2)
        assert not self.failed
        dst = self.port2 if sender == self.port1 else self.port1
        link_index = 0 if sender == self.port1 else 1
        now = self.scheduler.get_current_time()
        """
        if now < self.next_available_time[link_index]:
            print(f"error in link {self.name} from port {sender.port_id} of node {sender.owner.name} transmit: now={now}, next_available_time={self.next_available_time[link_index]}")
            exit()
            """
        #assert now == self.next_available_time[link_index], f"Link {self.name} transmit called too early on port {sender.port_id} of {sender.owner.name}"
        actual_start_time = now
        serialization_duration = packet.routing_header.size_bytes * 8.0 / self.bandwidth_bps  # in seconds
        self.accumulated_transmitting_time += serialization_duration
        self.accumulated_bytes_transmitted += packet.routing_header.size_bytes
        finish_serialization_time = actual_start_time + serialization_duration
        self.next_available_time[link_index] = finish_serialization_time
        arrival_time = finish_serialization_time + self.propagation_time

        def deliver():
            dst.owner.post(packet)

        # at arrival nominal time, the packet will be posted on the destination Host / Switch
        self.scheduler.schedule_event(arrival_time - now, deliver)
