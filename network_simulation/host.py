import itertools
import logging
from dataclasses import dataclass

from des.des import DiscreteEventSimulator
from network_simulation.Environment import ENV
from network_simulation.packet import FiveTuple, Protocol, PacketL3, PacketTransport, \
    PacketTrackingInfo, Packet
from network_simulation.network_node import NetworkNode

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
    def __init__(self, name: str, scheduler: DiscreteEventSimulator, ip_address: str, message_verbose: bool = False, verbose_route: bool = False, max_path: int | None = None, ports_count: int = 1):
        super().__init__(name, ports_count, scheduler, message_verbose=message_verbose, verbose_route=verbose_route)
        self._ip_address: str = ip_address
        self._received_count: int = 0
        self.max_path: int | None = max_path
        self.flows: dict[int, Flow] = {}

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

        packet_count = (size_bytes + ENV.mtu - 1) // ENV.mtu
        for i in range(packet_count):
            packet_size = ENV.mtu if i < packet_count - 1 else size_bytes - ENV.mtu * (packet_count - 1)
            packet_global_id: int = next(packet_ids)  # globally unique
            header: PacketL3 = PacketL3(
                five_tuple=FiveTuple(self.ip_address, dst_ip_address, source_port, dest_port, protocol),
                seq_number=i,
                size_bytes=packet_size,
                ttl=ENV.ttl
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
            self.scheduler.packets.append(packet)
            self._internal_send_packet(packet)


    def on_message(self, packet: Packet):
        now = self.scheduler.get_current_time()
        packet.tracking_info.delivered = True
        packet.tracking_info.arrival_time = now
        self._received_count += 1

        if self.message_verbose:
            now = self.scheduler.get_current_time()
            logging.debug(
                f"[t={now:.6f}s] Host {self.name} received message {packet.tracking_info.global_id} ")

    @property
    def received_count(self) -> int:
        return self._received_count
