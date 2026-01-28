import itertools
import logging
from dataclasses import dataclass

from des.des import DiscreteEventSimulator
from network_simulation.packet import FiveTupleExt, Protocol, PacketL3, PacketTransport, \
    PacketTrackingInfo, Packet
from network_simulation.network_node import NetworkNode, RoutingMode

_logger = logging.getLogger(__name__)

packet_ids = itertools.count()
flow_ids = itertools.count(1)

@dataclass
class Flow:
    flow_id: int
    app_id: int
    session_id: int
    src_ip: str
    dst_ip: str
    size_bytes: int
    start_time: float
    end_time: float | None = None
    bytes_received: int = 0

class Host(NetworkNode):
    def __init__(
        self,
        name: str,
        scheduler: DiscreteEventSimulator,
        ip_address: str,
        message_verbose: bool,
        verbose_route: bool,
        max_path: int | None,
        ports_count: int,
        routing_mode: RoutingMode,
        ecmp_flowlet_n_packets: int,
        mtu: int,
        ttl: int,
    ):
        super().__init__(
            name,
            ports_count,
            scheduler,
            routing_mode=routing_mode,
            message_verbose=message_verbose,
            verbose_route=verbose_route
        )
        self._ip_address: str = ip_address
        self._received_count: int = 0
        self.max_path: int | None = max_path
        self.flows: dict[int, Flow] = {}
        self.ecmp_flowlet_n_packets = ecmp_flowlet_n_packets
        self.mtu = mtu
        self.ttl = ttl

    @property
    def ip_address(self) -> str:
        return self._ip_address


    def send_message(
        self,
        session_id: int,
        dst_ip_address: str,
        source_port: int,
        dest_port: int,
        size_bytes: int,
        protocol: Protocol,
        **_kwargs,
    ) -> None:
        """Send a bulk message from this Host.

        Notes:
        - `session_id` is the value that becomes `PacketTransport.flow_id` and is used by higher layers
          (including the AI-factory layer) to join on flow completion.
        - `app_id` is currently unused (kept only for backward compatibility with older scenarios).
        """
        #logging.debug(f"[t={self.scheduler.get_current_time():.6f}s] Host {self.name} sending message "
        #              f"session_id={session_id} to {dst_ip_address} size={size_bytes}B protocol={protocol.name}")

        packet_count = (size_bytes + self.mtu - 1) // self.mtu
        flowlet_field = self.scheduler.get_current_time()
        flowlet_enabled = self.ecmp_flowlet_n_packets > 0
        for i in range(packet_count):
            packet_size = self.mtu if i < packet_count - 1 else size_bytes - self.mtu * (packet_count - 1)
            packet_global_id: int = next(packet_ids)  # globally unique
            if flowlet_enabled:
                # Update flowlet field every N packets.
                if (i + 1) % self.ecmp_flowlet_n_packets == 0:
                    flowlet_field += 1
            header: PacketL3 = PacketL3(
                five_tuple=FiveTupleExt(self.ip_address, dst_ip_address, source_port, dest_port, protocol, flowlet_field),
                seq_number=i,
                size_bytes=packet_size,
                ttl=self.ttl
            )
            app_header: PacketTransport = PacketTransport(
                flow_id=session_id,
                flow_count=packet_count,
                flow_seq=i
            )
            tracking_info = PacketTrackingInfo(
                global_id=packet_global_id,
                birth_time=self.scheduler.get_current_time(),
                route_length=0,
                verbose_route=None)
            if self.verbose_route:
                tracking_info.verbose_route = [self.name]
            packet = Packet(routing_header=header,
                            transport_header=app_header,
                            tracking_info=tracking_info)
            # Record packet creation in streaming stats
            self.scheduler.packet_stats.record_created()
            # Optionally store packet for debugging (when enabled)
            if self.scheduler._store_packets and self.scheduler.packets is not None:
                self.scheduler.packets.append(packet)
            self._internal_send_packet(packet)


    def on_message(self, packet: Packet):
        now = self.scheduler.get_current_time()
        packet.tracking_info.delivered = True
        packet.tracking_info.arrival_time = now
        self._received_count += 1
        # Record delivery in streaming stats
        self.scheduler.packet_stats.record_delivered(packet.tracking_info.route_length)

        if self.message_verbose and _logger.isEnabledFor(logging.DEBUG):
            _logger.debug(
                f"[sim_t={now:012.6f}s] Packet received    host={self.name} packet_id={packet.tracking_info.global_id}")

    @property
    def received_count(self) -> int:
        return self._received_count

