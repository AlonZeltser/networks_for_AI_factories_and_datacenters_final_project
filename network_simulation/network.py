import logging
import random
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from des.des import DiscreteEventSimulator
from network_simulation.host import Host
from network_simulation.link import Link
from network_simulation.switch import Switch
from network_simulation.scenario import Scenario
from visualization.visualizer import visualize_topology


class Network(ABC):
    def __init__(self, name: str, max_path: int,
                 link_failure_percent: float = 0.0, verbose: bool = False, verbose_route: bool = False):
        """Base class for topology/scenario network_simulators.

        Parameters:
        name: name of the topology/scenario
        link_failure_percent: percentage (0-100) of links to mark as failed at creation time
        """
        self.simulator = DiscreteEventSimulator()
        self.entities: Dict[str, Any] = {}
        self.hosts: Dict[str, Host] = {}
        self.name = name
        self._links: list[Link] = []
        self.switches: List[Switch] = []
        self.link_failure_percent = float(link_failure_percent)
        self.verbose = verbose
        self.verbose_route = verbose_route
        self._scenario: Scenario | None = None


    def create(self) -> None:
        # Build topology
        logging.debug("Creating topology...")
        self.create_topology()
        logging.debug("topology created.")

        # After topology created, log a short summary of failed links (if any)
        if self.link_failure_percent and self.link_failure_percent > 0.0:
            failed = [l.name for l in self._links if getattr(l, 'failed', False)]
            if failed:
                logging.info(f"Link failure summary: {len(failed)} links marked as failed")
            else:
                logging.info("Link failure summary: 0 links marked as failed")

        # Always save topology to file (never open a GUI window)
        try:
            visualize_topology(self.name, self.entities, show=False)
        except Exception:
            # do not break simulator creation if visualization fails
            logging.exception("visualize_topology failed")

        # Build scenario (traffic, flows, etc.)
        logging.debug("Creating scenario...")
        if self._scenario is not None:
            self._scenario.install(self)
        logging.debug("Scenario created.")

    def assign_scenario(self, scenario: Scenario) -> None:
        self._scenario = scenario
        self._scenario.install(self)
        logging.info("Scenario created.")

    def create_host(self, name: str, ip_address: str, ports_count: int = 1) -> Host:
        h = Host(name=name, scheduler=self.simulator, ip_address=ip_address,
                 message_verbose=self.verbose, verbose_route=self.verbose_route,
                 ports_count=ports_count)
        assert name not in self.entities and name not in self.hosts
        self.entities[name] = h
        self.hosts[name] = h
        return h

    def create_switch(self, name: str, ports_count: int) -> Switch:
        """Create a switch with the given number of ports."""
        s = Switch(name, ports_count, self.simulator, message_verbose=self.verbose, verbose_route=self.verbose_route)
        assert name not in self.entities
        self.entities[name] = s
        self.switches.append(s)
        return s

    def create_link(self, name: str, bandwidth: float = 1e6, delay: float = 1e-3) -> Link:
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
        messages_count = len(self.simulator.packets)
        messages_delivered_straight_count = len([m for m in self.simulator.packets if m.delivered])
        dropped_message_count = len([p for p in self.simulator.packets if p.header.dropped])
        route_lengths = [p.tracking_info.route_length for p in self.simulator.packets if p.delivered]
        trans_times = [link.accumulated_transmitting_time for link in self.links]
        links_average_delivery_time = float(sum(trans_times)) / float(len(trans_times)) if len(trans_times) > 0 else 0.0
        total_data = sum(link.accumulated_bytes_transmitted for link in self.links)
        total_bandwidth_time = sum((link.bandwidth_bps / 8) * total_time * 2 for link in self.links)
        links_average_utilization_percentage = (float(total_data) / float(total_bandwidth_time))*100 if total_bandwidth_time > 0 else 0.0

        run_statistics = {
            'messages count': messages_count,
            'total run time (simulator time in seconds)': self.simulator.end_time,
            'delivered messages count': messages_delivered_straight_count,
            'delivered messages percentage': (
                        messages_delivered_straight_count / messages_count * 100.0) if messages_count > 0 else 0.0,
            'dropped messages count': dropped_message_count,
            'dropped messages percentage': (
                        dropped_message_count / messages_count * 100.0) if messages_count > 0 else 0.0,
            'avg route length': float(sum(route_lengths)) / float(len(route_lengths)) if route_lengths else 0.0,
            'max route length': max(route_lengths) if route_lengths else 0,
            'min route length': min(route_lengths) if route_lengths else 0,
            'links min delivery time': min(trans_times),
            'links max delivery time': max(trans_times),
            'links average delivery time (2 directions)': links_average_delivery_time,
            'link average utilization percentage': links_average_utilization_percentage,
            'link_min_bytes_transmitted': min(link.accumulated_bytes_transmitted for link in self.links),
            'link_max_bytes_transmitted': max(link.accumulated_bytes_transmitted for link in self.links),
            'hosts received counts': [host.received_count for host in self.hosts.values()]
        }
        return {'topology summary': topology_summary,
                'parameters summary': parameters_summary,
                'run statistics': run_statistics}

    def get_parameters_summary(self):
        params = {
            'link_failure_percent': self.link_failure_percent
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
