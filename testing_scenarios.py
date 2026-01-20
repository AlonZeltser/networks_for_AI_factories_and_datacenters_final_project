# Ensure logging is configured before importing modules that may alter logging behavior
from log_setup import ensure_logging
from network_simulation.network_node import RoutingMode

ensure_logging()

import argparse
import logging
import random
import sys
import time

from network_simulation.network import Network
from network_simulators.hsh_network_simulator import HSHNetworkSimulator
from network_simulators.simple_star_network_simulator import SimpleStarNetworkSimulator
from visualization.experiment_visualizer import visualize_experiment_results
from scenarios.none_scenario import NoneScenario
from scenarios.hsh_pingpong import HSHPingPongScenario
from scenarios.simple_star_all_to_all import SimpleStarAllToAllScenario


def _scenario_from_name(name: str):
    name = (name or "none").lower()
    if name == "none":
        return NoneScenario()
    if name == "hsh-pingpong":
        return HSHPingPongScenario()
    if name == "simple-star-all-to-all":
        # Keep defaults explicit here so this file stays "simple" (no extra args besides topology+scenario).
        return SimpleStarAllToAllScenario(repeats=50, message_size_bytes=1000)
    raise ValueError("Unknown scenario. Valid: none, hsh-pingpong, simple-star-all-to-all")


def _network_from_topology(topology: str, *, link_failure_percent: float, message_verbose: bool, verbose_route: bool) -> Network:
    topology = (topology or "hsh").lower()
    if topology == "hsh":
        return HSHNetworkSimulator(
            max_path=3,
            link_failure_percent=link_failure_percent,
            verbose=message_verbose,
            verbose_route=verbose_route,
            routing_mode=RoutingMode.ECMP,
            ecmp_flowlet_n_packets=1,
        )
    if topology == "simple-star":
        return SimpleStarNetworkSimulator(
            max_path=6,
            link_failure_percent=link_failure_percent,
            verbose=message_verbose,
            verbose_route=verbose_route,
            routing_mode=RoutingMode.ECMP,
            ecmp_flowlet_n_packets=1,
        )
    raise ValueError("Unknown topology. Valid: hsh, simple-star")


def parse_args(argv):
    p = argparse.ArgumentParser(
        description=(
            "Quick testing runner (HSH + Simple-Star only). "
            "For AI-Factory SU (including bucket params like num_buckets), use ai_factory_network_simulation.py + YAML."
        )
    )
    p.add_argument("topology", help="Topology name: hsh or simple-star")
    p.add_argument("scenario", help="Scenario name: none, hsh-pingpong, simple-star-all-to-all")
    # These flags are optional but useful for local debugging without reintroducing a huge CLI surface.
    p.add_argument("--link-failure", type=float, default=0.0, help="Percent (0-100) of links to fail")
    p.add_argument("--message-verbose", action="store_true", default=False)
    p.add_argument("--verbose-route", action="store_true", default=False)
    return p.parse_args(argv)


def main(argv) -> int:
    args = parse_args(argv)

    # Configure per-run logging: INFO+ to console, DEBUG to a per-run logfile.
    try:
        from log_setup import configure_run_logging

        run_tag = f"{args.topology}.{args.scenario}"
        logfile_path = configure_run_logging(run_tag)
        logging.info("Logging to console and file: %s", logfile_path)
    except Exception:
        # Fall back to console-only logging.
        pass

    scenario = _scenario_from_name(args.scenario)
    network = _network_from_topology(
        args.topology,
        link_failure_percent=args.link_failure,
        message_verbose=args.message_verbose,
        verbose_route=args.verbose_route,
    )

    network.create(True)
    network.assign_scenario(scenario)

    logging.info("Starting simulation")
    start = time.perf_counter()
    network.run()
    elapsed = time.perf_counter() - start
    logging.info("Simulation run time: %.3f seconds", elapsed)

    results = network.get_results()

    # Print a readable summary.
    stats = results.get("run statistics", {})
    if isinstance(stats, dict) and stats:
        message = "\n".join(f"{k}: {v}" for k, v in stats.items())
        logging.info("Simulation stats:\n%s", message)

    # Always visualize in this test runner.
    visualize_experiment_results([results])
    return 0


if __name__ == "__main__":
    random.seed(1972)
    raise SystemExit(main(sys.argv[1:]))
