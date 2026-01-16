from __future__ import annotations

from network_simulation.simulator_creator import SimulatorCreator


class CircleCreator(SimulatorCreator):
    """A simple ring topology.

    Physical topology (ports-aware and matching Host=1 port constraint):

      - 5 switches in a ring.
      - 5 hosts, each attached to exactly one switch.

    Visually:

        H1--S1--S2--S3--S4--S5--(back to S1)
             |    |    |    |    |
            H2   H3   H4   H5   H1 (hosts are spokes, one per switch)

    Ring order of hosts is defined by the clockwise order of their attached switches.

    Scenario:
        All hosts simultaneously send a UDP message to the host immediately to their right
        (clockwise in the ring of switches).
    """

    def __init__(self, visualize: bool, max_path: int, link_failure_percent: float = 0.0, verbose: bool = False):
        super().__init__("circle", max_path=max_path, visualize=visualize, link_failure_percent=link_failure_percent,
                         verbose=verbose)
        self._identifier = {"link failure percent": link_failure_percent}

    def create_topology(self):
        # Entities
        hosts = [self.create_host(f"H{i}", f"10.0.0.{i}") for i in range(1, 6)]

        # Switch ports:
        #   port 1: attached host
        #   port 2: clockwise to next switch
        #   port 3: counter-clockwise to previous switch
        switches = [self.create_switch(f"S{i}", ports_count=3) for i in range(1, 6)]

        # Attach each host to its switch (spokes)
        for i in range(5):
            h = hosts[i]
            s = switches[i]
            l = self.create_link(f"L_{h.name}_{s.name}")
            h.connect(1, l)
            s.connect(1, l)

        # Connect switches in a ring
        for i in range(5):
            s = switches[i]
            s_next = switches[(i + 1) % 5]
            l = self.create_link(f"L_{s.name}_{s_next.name}")
            s.connect(2, l)
            s_next.connect(3, l)

        # Routing:
        # Hosts default route to their attached switch.
        for h in hosts:
            h.set_ip_routing("0.0.0.0/0", 1)

        # Switches: route each host IP either to local port (1), or around the ring.
        for sw_i in range(5):
            sw = switches[sw_i]
            for h_i, h in enumerate(hosts):
                if h_i == sw_i:
                    sw.set_ip_routing(f"{h.ip_address}/32", 1)
                    continue

                # Distance in switch-hops when going clockwise from sw_i to h_i.
                cw = (h_i - sw_i) % 5
                ccw = (sw_i - h_i) % 5
                # ring ports: 2 is clockwise, 3 is counter-clockwise
                port_id = 2 if cw <= ccw else 3
                sw.set_ip_routing(f"{h.ip_address}/32", port_id)

    def create_scenario(self):
        # At time t=0, every host sends a single message to the host to the right.
        def send_all_once():
            for i in range(1, 6):
                src = self.get_entity(f"H{i}")
                dst = self.get_entity(f"H{(i % 5) + 1}")
                src.send_to_ip(dst.ip_address, f"{src.name} -> {dst.name}", size_bytes=512)

        self.simulator.schedule_event(0.0, send_all_once)


if __name__ == '__main__':
    # Tiny manual runner for quick local sanity-check.
    creator = CircleCreator(visualize=True, max_path=32, link_failure_percent=0.0, verbose=False)
    sim = creator.create_simulator()
    sim.run()
    results = creator.get_results()
    print(results['topology summary'])
    print(results['run statistics'])
