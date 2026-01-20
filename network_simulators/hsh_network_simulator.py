from network_simulation.network import Network
from network_simulation.network_node import RoutingMode


class HSHNetworkSimulator(Network):
    def __init__(self, max_path: int, link_failure_percent: float, verbose: bool, verbose_route: bool,
                 routing_mode: RoutingMode, ecmp_flowlet_n_packets: int):
        super().__init__(
            "hsh",
            max_path,
            link_failure_percent=link_failure_percent,
            routing_mode=routing_mode,
            verbose=verbose,
            verbose_route=verbose_route,
            ecmp_flowlet_n_packets=ecmp_flowlet_n_packets,
            mtu=4096,
            ttl=64,
        )
        self._identifier = {"link failure percent": link_failure_percent}

    def create_topology(self):
        h1 = self.create_host('Host1', "10.1.1.1", ports_count=1)
        h2 = self.create_host('Host2', "10.1.1.2", ports_count=1)
        s1 = self.create_switch('Switch1', 2)

        l1 = self.create_link("h1_s1", bandwidth=1e3, delay=0.01)
        l2 = self.create_link('h2_s1', bandwidth=1e3, delay=0.01)

        # physical connection of h1 <-> l1 <-> s1 <-> l2 <-> h2
        h1.connect(1, l1)
        h2.connect(1, l2)
        s1.connect(1, l1)
        s1.connect(2, l2)

        h1.set_ip_routing("10.0.0.0/8", 1)
        h2.set_ip_routing("10.0.0.0/8", 1)
        s1.set_ip_routing("10.1.1.1/32", 1)
        s1.set_ip_routing("10.1.1.2/32", 2)
