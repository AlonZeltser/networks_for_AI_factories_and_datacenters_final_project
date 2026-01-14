from network_simulation.network_node import NetworkNode


class Switch(NetworkNode):

    def __init__(self, name: str, ports_count, scheduler, message_verbose: bool = False):
        super().__init__(name, ports_count, scheduler, message_verbose=message_verbose)

    def on_message(self, packet):
        self._internal_send_packet(packet)
