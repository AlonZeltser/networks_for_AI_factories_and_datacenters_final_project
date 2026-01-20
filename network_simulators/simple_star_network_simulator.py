from network_simulation.network import Network
from network_simulation.network_node import RoutingMode


class SimpleStarNetworkSimulator(Network):
    def __init__(self, max_path: int, link_failure_percent: float, verbose: bool, verbose_route: bool,
                 routing_mode: RoutingMode, ecmp_flowlet_n_packets: int):
        super().__init__(
            "simple star",
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
        h1 = self.create_host('H1', "10.1.1.1", ports_count=1)
        h2 = self.create_host('H2', "10.1.1.2", ports_count=1)
        h3 = self.create_host('H3', "10.2.1.1", ports_count=1)
        h4 = self.create_host('H4', "10.2.1.2", ports_count=1)

        e1 = self.create_switch('E1', 3)
        e2 = self.create_switch('E2', 3)
        s_core = self.create_switch('C', 2)

        h1_e1 = self.create_link('H1E1', bandwidth=1.0e2, delay=2.0e-3)
        h1.connect(1, h1_e1)
        e1.connect(1, h1_e1)

        h2_e1 = self.create_link('H2E1', bandwidth=1.0e2, delay=2.0e-3)
        h2.connect(1, h2_e1)
        e1.connect(2, h2_e1)

        h3_e2 = self.create_link('H3E2', bandwidth=1.0e2, delay=2.0e-3)
        h3.connect(1, h3_e2)
        e2.connect(1, h3_e2)

        h4_e2 = self.create_link('H4E2', bandwidth=1.0e2, delay=2.0e-3)
        h4.connect(1, h4_e2)
        e2.connect(2, h4_e2)

        c_e1 = self.create_link('CE1', bandwidth=2.0e2, delay=1.0e-3)
        c_e2 = self.create_link('CE2', bandwidth=1.0e2, delay=2.0e-3)
        e1.connect(3, c_e1)
        e2.connect(3, c_e2)
        s_core.connect(1, c_e1)
        s_core.connect(2, c_e2)

        #set routing for the created star topology
        h1.set_ip_routing("0.0.0.0/0", 1)
        h2.set_ip_routing("0.0.0.0/0", 1)
        h3.set_ip_routing("0.0.0.0/0", 1)
        h4.set_ip_routing("0.0.0.0/0", 1)

        e1.set_ip_routing("10.1.1.1/32", 1)
        e1.set_ip_routing("10.1.1.2/32", 2)
        e1.set_ip_routing("10.2.0.0/16", 3)

        e2.set_ip_routing("10.2.1.1/32", 1)
        e2.set_ip_routing("10.2.1.2/32", 2)
        e2.set_ip_routing("10.1.0.0/16", 3)

        s_core.set_ip_routing("10.1.0.0/16", 1)
        s_core.set_ip_routing("10.2.0.0/16", 2)
