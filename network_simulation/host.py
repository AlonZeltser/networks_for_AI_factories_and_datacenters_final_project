import itertools
import logging

from des.des import DiscreteEventSimulator
from network_simulation.Environment import ENV
from network_simulation.packet import FiveTuple, Protocol, PacketHeader, AppPacketHeader, \
    PacketTrackingInfo, Packet
from network_simulation.network_node import NetworkNode

packet_ids = itertools.count()
flow_ids = itertools.count(1)


class Host(NetworkNode):
    def __init__(self, name: str, scheduler: DiscreteEventSimulator, ip_address: str, message_verbose: bool = False, verbose_route: bool = False, max_path: int | None = None, ports_count: int = 1):
        super().__init__(name, ports_count, scheduler, message_verbose=message_verbose, verbose_route=verbose_route)
        self._ip_address: str = ip_address
        self._received_count: int = 0
        self.max_path: int | None = max_path

    @property
    def ip_address(self) -> str:
        return self._ip_address



    def send_message(self, app_id:int, session_id:int, dst_ip_address: str, source_port: int, dest_port: int, size_bytes, protocol:Protocol, message: str | None) -> None:
        packet_count = (size_bytes + ENV.mtu - 1) // ENV.mtu
        for i in range(packet_count):
            packet_size = ENV.mtu if i < packet_count - 1 else size_bytes - ENV.mtu * (packet_count - 1)
            payload = message if i == 0 else None
            packet_global_id: int = next(packet_ids)  # globally unique
            header: PacketHeader = PacketHeader(
                five_tuple=FiveTuple(self.ip_address, dst_ip_address, source_port, dest_port, protocol),
                seq_number=i,
                size_bytes=packet_size,
                ttl=ENV.ttl
            )
            app_header: AppPacketHeader = AppPacketHeader(
                app_session_id=session_id,
                app_session_packets_count=packet_count
            )
            tracking_info = PacketTrackingInfo(
                global_id = packet_global_id,
                sender = self.name,
                birth_time = self.scheduler.get_current_time(),
                route_length = 0,
                verbose_route = None)
            if self.verbose_route:
                tracking_info.verbose_route = [self.name]
            packet = Packet(header=header,
                            app_info=app_header,
                            tracking_info=tracking_info,
                            content=payload)
            self.scheduler.packets.append(packet)
            self._internal_send_packet(packet)


    def on_message(self, packet: Packet):
        packet.tracking_info.delivered = True
        packet.tracking_info.arrival_time = self.scheduler.get_current_time()
        self._received_count += 1
        if self.message_verbose:
            now = self.scheduler.get_current_time()
            logging.debug(
                f"[t={now:.6f}s] Host {self.name} received message {packet.tracking_info.global_id} "
                f"from {packet.tracking_info.sender} with content: {packet.content} (packet={packet})")

    @property
    def received_count(self) -> int:
        return self._received_count
