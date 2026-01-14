import logging
import random
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from des.des import DiscreteEventSimulator
from network_simulation.host import Host
from network_simulation.link import Link
from network_simulation.switch import Switch
from visualization.visualizer import visualize_topology


class SimulatorCreator(ABC):
    def __init__(self, name: str, max_path: int, visualize: bool = False,
                 link_failure_percent: float = 0.0, verbose: bool = False):
        """Base class for topology/scenario creators.

        Parameters:
        name: name of the topology/scenario
        visualize: whether to produce a visualization
        link_failure_percent: percentage (0-100) of links to mark as failed at creation time
        """
        self.simulator = DiscreteEventSimulator()
        self.entities: Dict[str, Any] = {}
        self.hosts: Dict[str, Host] = {}
        self._visualize = visualize
        self.name = name
        self._links: List[Link] = []
        self.switches: List[Switch] = []
        self.link_failure_percent = float(link_failure_percent)
        self.verbose = verbose

    def create_simulator(self) -> DiscreteEventSimulator:
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

        # Build scenario (traffic, flows, etc.)
        logging.debug("Creating scenario...")
        self.create_scenario()
        logging.debug("Scenario created.")

        if self._visualize:
            try:
                visualize_topology(self.name, self.entities, show=self._visualize)
            except Exception:
                # do not break simulator creation if visualization fails
                logging.exception("visualize_topology failed")

        return self.simulator

    def create_host(self, name: str, ip_address: str) -> Host:
        h = Host(name=name, scheduler=self.simulator, ip_address=ip_address, message_verbose=self.verbose)
        assert name not in self.entities and name not in self.hosts
        self.entities[name] = h
        self.hosts[name] = h
        return h

    def create_switch(self, name: str, ports_count: int) -> Switch:
        """Create a switch with the given number of ports."""
        s = Switch(name, ports_count, self.simulator, message_verbose=self.verbose)
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
        path_lengths = [p.tracking_info.path_length for p in self.simulator.packets if p.delivered]
        trans_times = [link.accumulated_transmitting_time for link in self.links]
        links_average_delivery_time = float(sum(trans_times)) / float(len(trans_times))

        run_statistics = {
            'messages count': messages_count,
            'total run time': self.simulator.end_time,
            'delivered straight messages count': messages_delivered_straight_count,
            'delivered straight messages percentage': (
                        messages_delivered_straight_count / messages_count * 100.0) if messages_count > 0 else 0.0,
            'dropped messages count': dropped_message_count,
            'dropped messages percentage': (
                        dropped_message_count / messages_count * 100.0) if messages_count > 0 else 0.0,
            'avg path length': float(sum(path_lengths)) / float(len(path_lengths)) if path_lengths else 0.0,
            'max path length': max(path_lengths) if path_lengths else 0,
            'min path length': min(path_lengths) if path_lengths else 0,
            'links min delivery time': min(trans_times),
            'links max delivery time': max(trans_times),
            'links average delivery time': links_average_delivery_time,
            'link average utilization': links_average_delivery_time / total_time,
            'link_min_bytes_transmitted': min(link.accumulated_bytes_transmitted for link in self.links),
            'link_max_bytes_transmitted': max(link.accumulated_bytes_transmitted for link in self.links),
            'hosts received counts': [host.received_count for host in self.hosts.values()]
        }
        return {'topology summary': topology_summary,
                'parameters summary': parameters_summary,
                'run statistics': run_statistics}

    def get_parameters_summary(self):
        return {
            'link_failure_percent': self.link_failure_percent
        }

    def get_entity(self, name: str) -> Any:
        return self.entities.get(name)

    @abstractmethod
    def create_topology(self):
        pass

    @abstractmethod
    def create_scenario(self):
        pass

    @property
    def links(self):
        return self._links
