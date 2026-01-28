import logging

from network_simulation.network_node import NetworkNode, RoutingMode

_logger = logging.getLogger(__name__)


class Switch(NetworkNode):

    def __init__(
        self,
        name: str,
        ports_count,
        scheduler,
        message_verbose: bool,
        verbose_route: bool,
        routing_mode: RoutingMode,
    ):
        super().__init__(
            name,
            ports_count,
            scheduler,
            routing_mode=routing_mode,
            message_verbose=message_verbose,
            verbose_route=verbose_route,
        )

    def on_message(self, packet):
        if packet.is_expired():
            if self.message_verbose:
                now = self.scheduler.get_current_time()
                logging.warning(
                    f"[sim_t={now:012.6f}s] Packet expired     switch={self.name} packet_id={packet.tracking_info.global_id} dst={packet.routing_header.five_tuple.dst_ip}")
            packet.routing_header.dropped = True
            self.scheduler.packet_stats.record_dropped()
        else:
            if self.message_verbose and _logger.isEnabledFor(logging.DEBUG):
                now = self.scheduler.get_current_time()
                _logger.debug(
                    f"[sim_t={now:012.6f}s] Packet forwarding  switch={self.name} packet_id={packet.tracking_info.global_id} dst={packet.routing_header.five_tuple.dst_ip}")
            self._internal_send_packet(packet)
