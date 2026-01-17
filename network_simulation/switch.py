import logging

from network_simulation.network_node import NetworkNode


class Switch(NetworkNode):

    def __init__(self, name: str, ports_count, scheduler, message_verbose: bool = False, verbose_route: bool = False):
        super().__init__(name, ports_count, scheduler, message_verbose=message_verbose, verbose_route=verbose_route)

    def on_message(self, packet):
        if packet.is_expired():
            if self.message_verbose:
                now = self.scheduler.get_current_time()
                logging.warning(
                    f"[t={now:.6f}s] Switch {self.name} dropping expired message {packet.tracking_info.global_id} to {packet.header.five_tuple.dst_ip}")
            packet.header.dropped = True
        else:
            if self.message_verbose:
                now = self.scheduler.get_current_time()
                logging.debug(
                    f"[t={now:.6f}s] Switch {self.name} received message {packet.tracking_info.global_id} to {packet.header.five_tuple.dst_ip}")
            self._internal_send_packet(packet)
