import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Tuple

from des.des import DiscreteEventSimulator
from network_simulation.ip import IPPrefix
from network_simulation.link import Link
from network_simulation.packet import Packet
from network_simulation.port import Port


class NetworkNode(ABC):
    def __init__(self, name: str,
                 ports_count: int,
                 scheduler: DiscreteEventSimulator,
                 message_verbose: bool = False):
        # --- actor basics (formerly Node) ---
        self.name = name
        self.scheduler = scheduler
        self.inbox: List[Packet] = []
        self.message_verbose = message_verbose

        # --- networking ---
        self.ports: List[Port] = [Port(i, self) for i in range(ports_count)]
        self.ip_forward_table: Dict[str, List[int]] = defaultdict(list)

    # called by others, to make this actor receive a packet
    # messages are not handled immediately, but scheduled to be handled at the current time step
    # the reason is to avoid deep recursion when messages are posted in response to receiving messages
    def post(self, packet: Packet) -> None:
        packet.header.ttl -= 1
        if self.message_verbose and packet.tracking_info.verbose_path is not None:
            packet.tracking_info.verbose_path.append(self.name)
        self.inbox.append(packet)
        self.scheduler.schedule_event(0.0, self.handle_message)

    # handling received messages
    # empty the inbox one by one, by scheduling handle_message events to this time step
    def handle_message(self):
        if self.inbox:
            message = self.inbox.pop(0)
            self.on_message(message)
            if self.inbox:
                self.scheduler.schedule_event(0.0, self.handle_message)

    @abstractmethod
    def on_message(self, packet: Packet):
        pass

    def connect(self, port_id: int, link: Link):
        """Connect one of this node's ports to a link.

        Public API uses 1-based port numbering (valid range: 1..len(self.ports)).
        Internally we store ports 0-based.
        """
        assert 1 <= port_id <= len(self.ports)
        index = port_id - 1
        port = self.ports[index]
        assert not port.is_connected
        port.connect(link)
        link.connect(port)

    def connections_count(self):
        return len([p for p in self.ports if p.is_connected])

    def assert_correctly_full(self):
        for port in range(0, len(self.ports)):
            assert self.ports[port].is_connected, f"Node {self.name} port {port} not connected!"

    def port_queue_size(self, port_id: int) -> int:
        """Return the number of queued egress messages on a given port (1-based port_id)."""
        assert 1 <= port_id <= len(self.ports)
        return self.ports[port_id - 1].queue_size()

    def ports_queue_sizes(self) -> Dict[int, int]:
        """Return a mapping port_id -> queued egress messages (1-based port_id)."""
        return {pid + 1: p.queue_size() for pid, p in enumerate(self.ports)}

    def set_ip_routing(self, ip_prefix: str, port_id: int):
        """Register an IP prefix -> port mapping.

        Public API uses 1-based port numbering.

        If the port is attached to a link that has been marked failed, the port will be skipped
        and not added to the forwarding table (as if the route wasn't learned through this
        interface).
        """
        assert 1 <= port_id <= len(self.ports)
        index = port_id - 1
        port = self.ports[index]
        if not getattr(port.link, 'failed'):
            self.ip_forward_table[ip_prefix].append(index)

    def _internal_send_packet(self, packet: Packet) -> None:
        assert not packet.header.dropped

        if packet.is_expired():
            self.handle_expired_packet(packet)
        else:  # normal packet routing
            self.handle_regular_packet(packet)

    def handle_expired_packet(self, packet: Packet):
        if self.message_verbose:
            logging.warning(
                f"{self.name} dropping expired message {packet.tracking_info.global_id} to {packet.header.five_tuple.dst_ip}")
        packet.header.dropped = True

    def handle_regular_packet(self, packet: Packet):
        dst_ip = packet.header.five_tuple.dst_ip

        # Find ports that match prefix to the destination IP
        relevant_ports: List[Tuple[int, int]] = [
            (p_id, IPPrefix.from_string(prefix_str).prefix_len)
            for prefix_str, port_ids in self.ip_forward_table.items()
            if IPPrefix.from_string(prefix_str).contains(dst_ip)
            for p_id in port_ids
        ]

        # If any relevant ports found, apply Longest Prefix Match, since it implies shortest path
        if relevant_ports:
            # Longest Prefix Match: choose the port with the longest matching prefix
            relevant_ports.sort(key=lambda x: x[1], reverse=True)
            longest_mask_len = relevant_ports[0][1]
            best_masked_ports = [p for p in relevant_ports if p[1] == longest_mask_len]
            assert best_masked_ports  # at least one port must exist here

            # If multiple best ports, choose one based on hash of the five-tuple for ECMP:
            # flow sticks to one path to avoid reordering
            port_index = hash(packet.header.five_tuple) % len(best_masked_ports)
            best_port_id = best_masked_ports[port_index][0]

            port = self.ports[best_port_id]
            if self.message_verbose:
                logging.debug(
                    f"{self.name} sending for destination {dst_ip} through port {best_port_id} to link {port.link.name}")
            port.enqueue(packet)
        else:
            if self.message_verbose:
                logging.warning(
                    f"{self.name} has no routing entry for destination IP {dst_ip}, dropping message")
            packet.header.dropped = True

    @property
    def links(self) -> List[Link]:
        return [p.get_link() for p in self.ports]
