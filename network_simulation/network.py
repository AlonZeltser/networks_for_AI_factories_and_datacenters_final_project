import logging
import random
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from des.des import DiscreteEventSimulator
from network_simulation.host import Host
from network_simulation.link import Link
from network_simulation.switch import Switch
from network_simulation.scenario import Scenario
from network_simulation.network_node import RoutingMode
from visualization.visualizer import visualize_topology

_logger = logging.getLogger(__name__)


class Network(ABC):
    def __init__(self, name: str, max_path: int,
                 link_failure_percent: float,
                 routing_mode: RoutingMode,
                 verbose: bool, verbose_route: bool,
                 ecmp_flowlet_n_packets: int,
                 mtu: int,
                 ttl: int):
        """Base class for topology/scenario network_simulators.

        Parameters:
        name: name of the topology/scenario
        link_failure_percent: percentage (0-100) of links to mark as failed at creation time
        routing_mode: forwarding selection policy for equal-cost next hops
        mtu: maximum transmission unit in bytes
        ttl: time to live (max hops for packets)
        """
        self.simulator = DiscreteEventSimulator()
        self.entities: Dict[str, Any] = {}
        self.hosts: Dict[str, Host] = {}
        self.name = name
        self._links: list[Link] = []
        self.switches: List[Switch] = []
        self.max_path = int(max_path)
        self.link_failure_percent = float(link_failure_percent)
        self.routing_mode = routing_mode
        self.ecmp_flowlet_n_packets = int(ecmp_flowlet_n_packets)
        self.verbose = verbose
        self.verbose_route = verbose_route
        self._scenario: Scenario | None = None
        self.mtu = int(mtu)
        self.ttl = int(ttl)


    def create(self, visualize:bool) -> None:
        # Build topology
        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug("Creating topology...")
        self.create_topology()
        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug("topology created.")

        # After topology created, log a short summary of failed links (if any)
        if self.link_failure_percent and self.link_failure_percent > 0.0:
            failed = [l.name for l in self._links if getattr(l, 'failed', False)]
            if failed:
                logging.info(f"Link failure summary: {len(failed)} links marked as failed")
            else:
                logging.info("Link failure summary: 0 links marked as failed")

        if visualize:
            try:
                visualize_topology(self.name, self.entities, show=False)
            except Exception:
                # do not break simulator creation if visualization fails
                logging.exception("visualize_topology failed")


    def assign_scenario(self, scenario: Scenario) -> None:
        logging.info("Creating scenario...")
        self._scenario = scenario
        self._scenario.install(self)
        logging.info("Scenario created.")

    def create_host(self, name: str, ip_address: str, ports_count: int) -> Host:
        h = Host(
            name=name,
            scheduler=self.simulator,
            ip_address=ip_address,
            routing_mode=self.routing_mode,
            ecmp_flowlet_n_packets=self.ecmp_flowlet_n_packets,
            message_verbose=self.verbose,
            verbose_route=self.verbose_route,
            ports_count=ports_count,
            max_path=None,
            mtu=self.mtu,
            ttl=self.ttl,
        )
        assert name not in self.entities and name not in self.hosts
        self.entities[name] = h
        self.hosts[name] = h
        return h

    def create_switch(self, name: str, ports_count: int) -> Switch:
        """Create a switch with the given number of ports."""
        s = Switch(
            name,
            ports_count,
            self.simulator,
            routing_mode=self.routing_mode,
            message_verbose=self.verbose,
            verbose_route=self.verbose_route,
        )
        assert name not in self.entities
        self.entities[name] = s
        self.switches.append(s)
        return s

    def create_link(self, name: str, bandwidth: float, delay: float) -> Link:
        l = Link(name, self.simulator, bandwidth, delay)
        assert name not in self.entities
        self.entities[name] = l
        # decide at creation time whether this link is a failed one according to the configured percentage
        if self.link_failure_percent and self.link_failure_percent > 0.0:
            # probability p = link_failure_percent / 100.0
            p = max(0.0, min(100.0, self.link_failure_percent)) / 100.0
            l.failed = random.random() < p
        else:
            l.failed = False
        # track created links for reporting
        self._links.append(l)
        return l

    def get_results(self):
        topology_summary = {
            'hosts count': len(self.hosts),
            'switches count': len(self.switches),
            'links count': len(self.links),
            'failed_links': len([link for link in self.links if getattr(link, 'failed')]),
            'affected switches': len([s for s in self.switches if any(link for link in s.links if link.failed)])
        }

        parameters_summary = self.get_parameters_summary()

        total_time = self.simulator.end_time
        packets_count = len(self.simulator.packets)
        delivered_packets_count = len([m for m in self.simulator.packets if m.delivered])
        dropped_packets_count = len([p for p in self.simulator.packets if p.routing_header.dropped])
        route_lengths = [p.tracking_info.route_length for p in self.simulator.packets if p.delivered]
        trans_times = [link.accumulated_transmitting_time for link in self.links]
        links_average_delivery_time = float(sum(trans_times)) / float(len(trans_times)) if len(trans_times) > 0 else 0.0
        total_data = sum(link.accumulated_bytes_transmitted for link in self.links)
        total_bandwidth_time = sum((link.bandwidth_bps / 8) * total_time * 2 for link in self.links)
        links_average_utilization_percentage = (float(total_data) / float(total_bandwidth_time))*100 if total_bandwidth_time > 0 else 0.0

        # --- Queue statistics (packets) ---
        nodes = list(self.hosts.values()) + list(self.switches)
        global_max_port_peak_queue_len = 0
        node_peak_queue_lens: list[int] = []
        for n in nodes:
            # Some code paths/tests may construct nodes without ports populated; be defensive.
            ports = getattr(n, 'ports', None)
            if not ports:
                continue
            node_peak = 0
            for p in ports:
                peak = int(getattr(p, 'peak_queue_len', 0))
                if peak > global_max_port_peak_queue_len:
                    global_max_port_peak_queue_len = peak
                if peak > node_peak:
                    node_peak = peak
            node_peak_queue_lens.append(node_peak)
        avg_node_peak_egress_queue_len = (
            float(sum(node_peak_queue_lens)) / float(len(node_peak_queue_lens))
            if node_peak_queue_lens else 0.0
        )

        run_statistics = {
            'total packets count': packets_count,
            'total run time (simulator time in seconds)': self.simulator.end_time,
            'delivered packets count': delivered_packets_count,
            'delivered packets percentage': (
                        delivered_packets_count / packets_count * 100.0) if packets_count > 0 else 0.0,
            'dropped packets count': dropped_packets_count,
            'dropped packets percentage': (
                        dropped_packets_count / packets_count * 100.0) if packets_count > 0 else 0.0,
            'avg route length': float(sum(route_lengths)) / float(len(route_lengths)) if route_lengths else 0.0,
            'max route length': max(route_lengths) if route_lengths else 0,
            'min route length': min(route_lengths) if route_lengths else 0,
            'links min delivery time': min(trans_times),
            'links max delivery time': max(trans_times),
            'links average delivery time (2 directions)': links_average_delivery_time,
            'link average utilization percentage': links_average_utilization_percentage,
            'link_min_bytes_transmitted': min(link.accumulated_bytes_transmitted for link in self.links),
            'link_max_bytes_transmitted': max(link.accumulated_bytes_transmitted for link in self.links),
            'hosts received counts': [host.received_count for host in self.hosts.values()],
            'global_max_port_peak_queue_len (packets)': global_max_port_peak_queue_len,
            'avg_node_peak_egress_queue_len (packets)': avg_node_peak_egress_queue_len,
        }

        # --- AI-factory app metrics (if present) ---
        try:
            from ai_factory_simulation.core.runner import _compute_step_stats  # type: ignore

            job_metrics = self.entities.get("ai_factory_job_metrics")
            if job_metrics is not None:
                per_job: dict[str, dict[str, float]] = {}

                # Single-job scenarios store a JobMetrics object;
                # mixed scenarios store a dict like {"jobA": JobMetrics, "jobB": JobMetrics}.
                if isinstance(job_metrics, dict):
                    items = job_metrics.items()
                else:
                    items = [("job", job_metrics)]

                for name, jm in items:
                    steps = getattr(jm, "steps", None)
                    if not steps:
                        continue
                    stats = _compute_step_stats(list(steps))
                    per_job[name] = {
                        "step_time_avg_ms": float(stats["avg"]) * 1000.0,
                        "step_time_p95_ms": float(stats["p95"]) * 1000.0,
                        "step_time_p99_ms": float(stats["p99"]) * 1000.0,
                    }

                if per_job:
                    run_statistics["ai_factory_step_time_ms_per_job"] = per_job
        except Exception:
            # Never break results collection because of optional AI-factory metrics.
            pass

        # --- Mice flow metrics (if present) ---
        try:
            mice_summary = self.entities.get("mice_flow_summary")
            if isinstance(mice_summary, dict) and mice_summary:
                run_statistics.update(mice_summary)
        except Exception:
            pass

        # Collect packet timeline data for visualization (birth_time, size_bytes)
        packet_timeline = [
            (p.tracking_info.birth_time, p.routing_header.size_bytes)
            for p in self.simulator.packets
        ]

        return {
            'topology summary': topology_summary,
            'parameters summary': parameters_summary,
            'run statistics': run_statistics,
            'packet_timeline': packet_timeline,
        }

    def get_parameters_summary(self):
        params = {
            'link_failure_percent': self.link_failure_percent,
            'routing_mode': self.routing_mode.name.lower(),
            'ecmp_flowlet_n_packets': self.ecmp_flowlet_n_packets,
            'max_path': self.max_path,
        }
        if self._scenario is not None:
            try:
                params.update(self._scenario.parameters_summary())
            except Exception:
                # keep results usable even if scenario summary fails
                params['scenario'] = getattr(self._scenario, 'name', self._scenario.__class__.__name__)
        return params

    def get_entity(self, name: str) -> Any:
        return self.entities.get(name)

    def run(self):
        assert self.simulator is not None
        self.simulator.run()

    @abstractmethod
    def create_topology(self):
        pass

    @property
    def links(self):
        return self._links
