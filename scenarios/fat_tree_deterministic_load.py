from __future__ import annotations

from dataclasses import dataclass
import functools

from network_simulation.host import Host
from network_simulation.packet import Protocol
from network_simulation.scenario import Scenario


@dataclass(frozen=True)
class FatTreeDeterministicLoadScenario(Scenario):
    """Deterministic high-load scenario from the original FatTreeTopoNetworkSimulator.

    Each host sends `num_messages` messages to a deterministic destination host.
    """

    name: str = "fat-tree-deterministic-load"
    num_messages: int = 10
    #message_size_bytes: int = int(1e10 / 8)  # 10Gb
    message_size_bytes: int = int(1e5 / 8)  # 1Mb

    def install(self, network) -> None:
        # This scenario expects a fat-tree-like topology where network.k exists.
        k = getattr(network, 'k', None)
        if not isinstance(k, int):
            raise ValueError("FatTreeDeterministicLoadScenario requires a fat-tree topology (network.k missing)")

        hosts_names_list = list(network.hosts.keys())
        index_of_names = {key: i for i, key in enumerate(hosts_names_list)}
        hosts_count = len(hosts_names_list)
        if hosts_count == 0:
            return

        hosts_in_pod_count = (k // 2) ** 2

        def send_message(source: Host, dst_host: Host):
            source.send_message(
                app_id=1,
                session_id=1,
                dst_ip_address=dst_host.ip_address,
                source_port=1000,
                dest_port=2000,
                size_bytes=int(self.message_size_bytes),
                protocol=Protocol.UDP,
                message=f'Message from {source.name} to {dst_host.name}'
            )

        for host_name, i in index_of_names.items():
            host = network.hosts[host_name]
            destination_host_index = (i + hosts_in_pod_count + 17) % hosts_count
            dst_host_name = hosts_names_list[destination_host_index]
            dest_host = network.hosts[dst_host_name]
            for _ in range(int(self.num_messages)):
                network.simulator.schedule_event(0, functools.partial(send_message, host, dest_host))

    def parameters_summary(self):
        out = super().parameters_summary()
        out.update({"num_messages": self.num_messages, "message_size_bytes": self.message_size_bytes})
        return out
