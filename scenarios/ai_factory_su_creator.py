from __future__ import annotations

import logging

from network_simulation.simulator_creator import SimulatorCreator


class AIFactorySUCreator(SimulatorCreator):
    """A topology inspired by NVIDIA's AI-Factory Scalable Unit (SU).

    We simulate everything over Ethernet.

    Topology (single SU / POD):
      - 8 leaf switches (ToRs).
      - 4 spine switches.
      - 4 servers per leaf.
      - Each server connects to its leaf using 8 x 400GbE links.
      - Leaf <-> Spine fabric: each leaf has 32 uplinks total, each spine has 64 downlinks.
        Implemented as 8 uplinks from each leaf to each spine (8 leaves * 8 = 64 per spine).

    Routing:
      - Servers are addressed in per-leaf /24 subnets: 10.<pod_id>.<leaf_id>.<server_id>
      - Leaves route:
          * local /24 -> host-facing ports
          * pod /16 (10.<pod_id>.0.0/16) -> uplinks (ECMP across spines)
      - Spines route:
          * per-leaf /24 -> downlinks to that leaf

    Scenario:
      - No traffic by default (topology-only). Visualization can be enabled.
    """

    POD_ID = 1
    LEAVES = 8
    SPINES = 4
    SERVERS_PER_LEAF = 4

    SERVER_PARALLEL_LINKS = 8  # 8x400G per server to leaf
    LEAF_TO_SPINE_PARALLEL_LINKS = 8  # per (leaf, spine)

    BW_400G = 400e9

    def __init__(self, visualize: bool, max_path: int,
                 link_failure_percent: float = 0.0, verbose: bool = False):
        super().__init__(
            name="ai-factory-su",
            max_path=max_path,
            visualize=visualize,
            link_failure_percent=link_failure_percent,
            verbose=verbose,
        )
        self._identifier = {
            "topology": "ai-factory-su",
            "leaves": self.LEAVES,
            "spines": self.SPINES,
            "servers_per_leaf": self.SERVERS_PER_LEAF,
            "server_parallel_links": self.SERVER_PARALLEL_LINKS,
            "leaf_to_spine_parallel_links": self.LEAF_TO_SPINE_PARALLEL_LINKS,
            "link failure percent": link_failure_percent,
        }

    def create_topology(self):
        bw = self.BW_400G
        delay = 1e-6  # 1us per hop propagation (toy value, but non-zero)

        # Switches
        # Leaf ports: 4 servers * 8 links = 32 downlinks, plus 32 uplinks = 64 ports
        leaf_ports = self.SERVERS_PER_LEAF * self.SERVER_PARALLEL_LINKS + (self.SPINES * self.LEAF_TO_SPINE_PARALLEL_LINKS)
        spine_ports = self.LEAVES * self.LEAF_TO_SPINE_PARALLEL_LINKS  # 64

        leaves = [
            self.create_switch(f"su{self.POD_ID}_leaf{leaf_i}", ports_count=leaf_ports)
            for leaf_i in range(self.LEAVES)
        ]
        spines = [
            self.create_switch(f"su{self.POD_ID}_spine{spine_i}", ports_count=spine_ports)
            for spine_i in range(self.SPINES)
        ]

        # Hosts and Host<->Leaf links
        # Addressing: 10.<POD_ID>.<leaf_id+1>.<server_id+1>
        for leaf_i, leaf in enumerate(leaves):
            leaf_subnet_third_octet = leaf_i + 1

            for srv_i in range(self.SERVERS_PER_LEAF):
                host_name = f"su{self.POD_ID}_leaf{leaf_i}_srv{srv_i}"
                ip = f"10.{self.POD_ID}.{leaf_subnet_third_octet}.{srv_i + 1}"
                host = self.create_host(host_name, ip, ports_count=self.SERVER_PARALLEL_LINKS)

                for k in range(self.SERVER_PARALLEL_LINKS):
                    link = self.create_link(
                        f"su{self.POD_ID}_l_leaf{leaf_i}_srv{srv_i}_nic{k}",
                        bandwidth=bw,
                        delay=delay,
                    )
                    # Host port ids are 1..8
                    host.connect(k + 1, link)
                    # Leaf host-facing ports are 1..32
                    leaf_port_id = (srv_i * self.SERVER_PARALLEL_LINKS) + k + 1
                    leaf.connect(leaf_port_id, link)

                # Host routing: route the whole POD via any NIC (ECMP across NICs)
                pod_prefix_16 = f"10.{self.POD_ID}.0.0/16"
                for k in range(self.SERVER_PARALLEL_LINKS):
                    host.set_ip_routing(pod_prefix_16, k + 1)

            # Leaf routing: per-server /32 routes for local delivery (ECMP across the 8 ports to that server)
            # and a /24 shortcut for "this leaf".
            leaf_prefix_24 = f"10.{self.POD_ID}.{leaf_subnet_third_octet}.0/24"
            for srv_i in range(self.SERVERS_PER_LEAF):
                ip = f"10.{self.POD_ID}.{leaf_subnet_third_octet}.{srv_i + 1}"
                for k in range(self.SERVER_PARALLEL_LINKS):
                    leaf_port_id = (srv_i * self.SERVER_PARALLEL_LINKS) + k + 1
                    leaf.set_ip_routing(f"{ip}/32", leaf_port_id)

                # Also include the per-leaf /24 routed to all local host-facing ports (readable subnet entry)
                for k in range(self.SERVER_PARALLEL_LINKS):
                    leaf_port_id = (srv_i * self.SERVER_PARALLEL_LINKS) + k + 1
                    leaf.set_ip_routing(leaf_prefix_24, leaf_port_id)

        # Leaf<->Spine links
        # Leaf uplink ports start after host-facing ports.
        leaf_uplink_base = self.SERVERS_PER_LEAF * self.SERVER_PARALLEL_LINKS  # 32
        for leaf_i, leaf in enumerate(leaves):
            for spine_i, spine in enumerate(spines):
                for k in range(self.LEAF_TO_SPINE_PARALLEL_LINKS):
                    link = self.create_link(
                        f"su{self.POD_ID}_l_leaf{leaf_i}_spine{spine_i}_{k}",
                        bandwidth=bw,
                        delay=delay,
                    )

                    leaf_port_id = leaf_uplink_base + (spine_i * self.LEAF_TO_SPINE_PARALLEL_LINKS) + k + 1
                    spine_port_id = (leaf_i * self.LEAF_TO_SPINE_PARALLEL_LINKS) + k + 1

                    leaf.connect(leaf_port_id, link)
                    spine.connect(spine_port_id, link)

        # Fabric routing
        # Leaves: route the entire POD /16 to all uplinks (ECMP across spines and parallel links).
        pod_prefix_16 = f"10.{self.POD_ID}.0.0/16"
        for leaf in leaves:
            for spine_i in range(self.SPINES):
                for k in range(self.LEAF_TO_SPINE_PARALLEL_LINKS):
                    leaf_port_id = leaf_uplink_base + (spine_i * self.LEAF_TO_SPINE_PARALLEL_LINKS) + k + 1
                    leaf.set_ip_routing(pod_prefix_16, leaf_port_id)

        # Spines: route each leaf /24 to the downlinks to that leaf
        for spine_i, spine in enumerate(spines):
            for leaf_i in range(self.LEAVES):
                leaf_prefix_24 = f"10.{self.POD_ID}.{leaf_i + 1}.0/24"
                for k in range(self.LEAF_TO_SPINE_PARALLEL_LINKS):
                    spine_port_id = (leaf_i * self.LEAF_TO_SPINE_PARALLEL_LINKS) + k + 1
                    spine.set_ip_routing(leaf_prefix_24, spine_port_id)

        # Sanity: check all switch ports connected (unless link failures prevented it).
        # We still physically connect failed links, so ports will be connected.
        for sw in leaves + spines:
            try:
                sw.assert_correctly_full()
            except AssertionError:
                logging.exception(f"Switch {sw.name} isn't fully connected")
                raise

        logging.info(
            f"AI-Factory SU topology created: leaves={self.LEAVES}, spines={self.SPINES}, "
            f"servers={self.LEAVES * self.SERVERS_PER_LEAF}, links={len(self.links)}"
        )

    def create_scenario(self):
        # Topology-only: intentionally no traffic.
        return

    @property
    def identifier(self):
        return self._identifier
