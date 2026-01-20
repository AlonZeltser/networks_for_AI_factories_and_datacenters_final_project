import logging
import random
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from enum import Enum
from typing import Deque, Dict, List, Tuple

from des.des import DiscreteEventSimulator
from network_simulation.ip import IPPrefix
from network_simulation.link import Link
from network_simulation.packet import Packet
from network_simulation.port import Port

class RoutingMode(Enum):
    ECMP = 1
    ADAPTIVE = 2


class NetworkNode(ABC):
    def __init__(self, name: str,
                 ports_count: int,
                 scheduler: DiscreteEventSimulator,
                 routing_mode: RoutingMode,
                 message_verbose: bool,
                 verbose_route: bool):
        # --- actor basics (formerly Node) ---
        self.name = name
        self.scheduler = scheduler
        self.inbox: Deque[Packet] = deque()
        self._handle_scheduled: bool = False
        self.message_verbose = message_verbose
        self.verbose_route = verbose_route

        # --- networking ---
        self.ports: List[Port] = [Port(i, self) for i in range(ports_count)]

        # Backward-compatible map (kept mostly for debugging/introspection).
        self.ip_forward_table: Dict[str, List[int]] = defaultdict(list)

        # Fast-path compiled table for routing lookups.
        # Bucketed by prefix_len so we can stop early on first match.
        # prefix_len -> list[(net_int, mask_int, port_index)]
        self._ip_forward_compiled_by_len: dict[int, list[Tuple[int, int, int]]] = defaultdict(list)
        self._compiled_prefix_lens_desc: list[int] = []
        self._compiled_prefix_lens_set: set[int] = set()

        self.routing_mode = routing_mode

    # called by others, to make this actor receive a packet
    # messages are not handled immediately, but scheduled to be handled at the current time step
    # the reason is to avoid deep recursion when messages are posted in response to receiving messages
    def post(self, packet: Packet) -> None:
        packet.routing_header.ttl -= 1
        packet.tracking_info.route_length += 1
        if self.verbose_route and packet.tracking_info.verbose_route is not None:
            packet.tracking_info.verbose_route.append(self.name)
        self.inbox.append(packet)
        if not self._handle_scheduled:
            self._handle_scheduled = True
            self.scheduler.schedule_event(0.0, self.handle_message)

    # handling received messages
    # empty the inbox one by one, by scheduling handle_message events to this time step
    def handle_message(self):
        # Drain the inbox for this time slice.
        while self.inbox:
            message = self.inbox.popleft()
            self.on_message(message)
        self._handle_scheduled = False

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
        assert port.link is not None
        if getattr(port.link, 'failed'):
            return


        # Keep the old structure for introspection.
        self.ip_forward_table[ip_prefix].append(index)

        # Compile the prefix once for fast matching.
        pfx = IPPrefix.from_string(ip_prefix)
        net_int = pfx.network.to_int()
        mask_int = IPPrefix._mask_from_prefix(pfx.prefix_len)
        self._ip_forward_compiled_by_len[pfx.prefix_len].append((net_int, mask_int, index))

        # Maintain descending list of prefix lengths for LPM scan.
        if pfx.prefix_len not in self._compiled_prefix_lens_set:
            self._compiled_prefix_lens_set.add(pfx.prefix_len)
            self._compiled_prefix_lens_desc.append(pfx.prefix_len)
            self._compiled_prefix_lens_desc.sort(reverse=True)

    def select_port_for_packet(self, packet: Packet) -> int | None:
        # Use cached integer dst-ip to avoid parsing at every hop.
        dst_int = packet.routing_header.five_tuple.dst_ip_int

        # Longest-prefix match by scanning prefix lengths descending.
        best_ports: list[int] = []
        for plen in self._compiled_prefix_lens_desc:
            entries = self._ip_forward_compiled_by_len.get(plen)
            if not entries:
                continue

            for net_int, mask_int, port_idx in entries:
                if (dst_int & mask_int) == net_int:
                    best_ports.append(port_idx)

            if best_ports:
                break

        if not best_ports:
            return None

        if self.routing_mode == RoutingMode.ECMP:
            # Standard ECMP: stable hash selection among equal-cost next hops.
            return best_ports[hash(packet.routing_header.five_tuple) % len(best_ports)]

        # ADAPTIVE: pick uniformly among the ports with the smallest current queue.
        min_len = None
        min_ports: list[int] = []
        for p in best_ports:
            q_length = self.ports[p].queue_size()
            if (min_len is None) or (q_length < min_len):
                min_len = q_length
                min_ports = [p]
            elif q_length == min_len:
                min_ports.append(p)

        return random.choice(min_ports)


    def _internal_send_packet(self, packet: Packet) -> None:
        best_port_id = self.select_port_for_packet(packet)
        if best_port_id is not None:
            port = self.ports[best_port_id]
            if self.message_verbose:
                now = self.scheduler.get_current_time()
                logging.debug(
                    f"[sim_t={now:012.6f}s] Packet enqueue     node={self.name} packet_id={packet.tracking_info.global_id} port={best_port_id + 1}")
            port.enqueue(packet)
        else:
            if self.message_verbose:
                now = self.scheduler.get_current_time()
                logging.warning(
                    f"[sim_t={now:012.6f}s] Packet no route    node={self.name} packet_id={packet.tracking_info.global_id} dst={packet.routing_header.five_tuple.dst_ip}")
            packet.routing_header.dropped = True


    @property
    def links(self) -> List[Link]:
        return [p.get_link() for p in self.ports]
