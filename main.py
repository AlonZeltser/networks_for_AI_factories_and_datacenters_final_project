import random
import logging
import argparse
import sys
import time
from typing import List
import os


from network_simulation.network import Network
from network_simulators.fat_tree_topo_network_simulator import FatTreeTopoNetworkSimulator
from network_simulators.hsh_network_simulator import HSHNetworkSimulator
from network_simulators.simple_star_network_simulator import SimpleStarNetworkSimulator
from network_simulators.ai_factory_su_network_simulator import AIFactorySUNetworkSimulator
from visualization.experiment_visualizer import visualize_experiment_results
from scenarios.none_scenario import NoneScenario
from scenarios.hsh_pingpong import HSHPingPongScenario
from scenarios.simple_star_all_to_all import SimpleStarAllToAllScenario
from scenarios.fat_tree_deterministic_load import FatTreeDeterministicLoadScenario



def _scenario_from_args(args):
    name = (getattr(args, 'scenario', None) or 'none').lower()
    if name == 'none':
        return NoneScenario()
    if name == 'hsh-pingpong':
        return HSHPingPongScenario()
    if name == 'simple-star-all-to-all':
        return SimpleStarAllToAllScenario(repeats=50, message_size_bytes=1000)
    if name == 'fat-tree-deterministic-load':
        return FatTreeDeterministicLoadScenario(num_messages=100)
    raise ValueError(
        f"Unknown scenario '{name}'. Valid options: none, hsh-pingpong, simple-star-all-to-all, fat-tree-deterministic-load"
    )


def create_network_from_arg(args) -> List[Network]:
    results: list[Network] = []
    topology = args.t.lower()
    verbose = args.message_verbose
    verbose_route = args.verbose_route
    link_failures = args.link_failure
    if link_failures is None or len(link_failures) == 0:
        link_failures = [0.0]

    if topology == 'fat-tree':
        k = args.k
        if k is None:
            raise ValueError("k parameter must be supplied for fat-tree topology")
        if len(k) == 0:
            raise ValueError("k parameter list cannot be empty for fat-tree topology")
        for k in args.k:
            if k < 1 or (k % 2) != 0:
                raise ValueError("k must be >=1 and even for fat-tree topologies")
        for k in args.k:
            for link_failure in link_failures:
                logging.debug(f"Creating Fat-Tree topology with k={k} ports per switch and link-failure={link_failure}%")
                results.append(
                    FatTreeTopoNetworkSimulator(
                        k=k,
                        max_path=1000000,
                        link_failure_percent=link_failure,
                        verbose=verbose,
                        verbose_route=verbose_route,
                    )
                )
    elif topology == 'hsh':
        for link_failure in link_failures:
            logging.info(f"Creating HSH topology with link-failure={link_failure}%")
            results.append(
                HSHNetworkSimulator(
                    max_path=3,
                    link_failure_percent=link_failure,
                    verbose=verbose,
                    verbose_route=verbose_route,
                )
            )
    elif topology == 'simple-star':
        for link_failure in link_failures:
            logging.info(f"Creating Simple Star topology with link-failure={link_failure}%")
            results.append(
                SimpleStarNetworkSimulator(
                    max_path=6,
                    link_failure_percent=link_failure,
                    verbose=verbose,
                    verbose_route=verbose_route,
                )
            )
    elif topology == 'ai-factory-su':
        for link_failure in link_failures:
            logging.info(f"Creating AI-Factory SU topology with link-failure={link_failure}%")
            results.append(
                AIFactorySUNetworkSimulator(
                    max_path=64,
                    link_failure_percent=link_failure,
                    verbose=verbose,
                    verbose_route=verbose_route,
                )
            )
    else:
        raise ValueError(f"Unknown topology '{args.t}'. Valid options: fat-tree, hsh, simple-star, ai-factory-su")

    return results


def parse_args(argv):
    parser = argparse.ArgumentParser(description='Network simulator runner')
    parser.add_argument(
        '-t',
        default='fat-tree',
        help='Type of topology: fat-tree, hsh (simplest, for demo), simple-star (simple tree with 2 levels, for demo and debugging), ai-factory-su'
    )
    parser.add_argument('-k', nargs='+', type=int, default=[4],
                        help='(fat-tree only) list of number of ports per switch (must be even)')
    parser.add_argument('-link-failure', nargs='+', type=float, default=[0.0],
                        help='list of probability of links to fail in each test. Fraction (0-100) of links to fail')
    parser.add_argument('-message_verbose', required=False, action='store_true', dest='message_verbose', default=False,
                        help='Enable message_verbose logging output to console')
    parser.add_argument('-verbose_route', required=False, action='store_true', dest='verbose_route', default=False,
                        help='Enable per-packet verbose route tracking (stores hop-by-hop route for delivered packets)')
    parser.add_argument('-scenario', default='none',
                        help='Traffic scenario to run on top of the topology: none, hsh-pingpong, simple-star-all-to-all, fat-tree-deterministic-load')
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)

    # Re-configure the file logger now that we know which run we're doing.
    # Keep console logging as-is.
    set_logger(topology=args.t, scenario=args.scenario)

    logging.info(
        f"Starting network simulation. topology={args.t}, scenario={args.scenario}, k={args.k}, message_verbose={args.message_verbose}, verbose_route={args.verbose_route}, link-failure={args.link_failure}"
    )

    scenario = _scenario_from_args(args)

    networks = create_network_from_arg(args)
    aggregated_results = []
    for network in networks:
        network.create()
        network.assign_scenario(scenario)

        logging.info(f"Starting simulation")
        start = time.perf_counter()
        network.run()
        elapsed = time.perf_counter() - start
        logging.info(f"Simulation run time: {elapsed:.3f} seconds")
        results = network.get_results()
        stats = results['run statistics']
        message = "\n".join(f"{k}: {v}" for k, v in stats.items() if not isinstance(v, List))
        logging.info(f"Simulation stats: \n {message}")
        aggregated_results.append(results)

    visualize_experiment_results(aggregated_results)


def _sanitize_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(name))


class _AlignedPrefixFormatter(logging.Formatter):
    """Formatter that keeps log message bodies aligned by padding *after* the line number.

    We want this layout:
        time [LEVEL] filename.py:123<spaces> message

    Padding after the line number ensures the filename stays "tight" (no trailing spaces)
    while the message body starts at a stable column.
    """

    def __init__(self, prefix_width: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prefix_width = prefix_width

    def format(self, record: logging.LogRecord) -> str:
        # Compute once per record. logging can call format() multiple times.
        file_line = f"{record.filename}:{record.lineno}"  # includes the line number
        pad_len = max(1, self._prefix_width - len(file_line))
        record.lineno_pad = " " * pad_len
        return super().format(record)


def set_logger(topology: str | None = None, scenario: str | None = None):
    logger = logging.getLogger()
    # set root logger to DEBUG so handlers themselves decide what to record
    logger.setLevel(logging.DEBUG)

    # remove any existing handlers so we don't duplicate output when reloading
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    # Always install a console handler (so early errors are visible).
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(logging.INFO)

    formatter = _AlignedPrefixFormatter(
        prefix_width=24,
        fmt="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d%(lineno_pad)s%(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # If topology isn't known yet (bootstrap), don't create a file handler.
    if not topology:
        logging.getLogger('matplotlib').setLevel(logging.WARNING)
        logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)
        return

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Log path: always under results/, named by topology (and scenario).
    results_dir = os.path.join(base_dir, "results")
    try:
        os.makedirs(results_dir, exist_ok=True)
    except Exception:
        pass

    topo_part = _sanitize_filename(topology)
    scen_part = _sanitize_filename(scenario) if scenario else None

    if scen_part:
        log_filename = f"simulation_{topo_part}__{scen_part}.log"
    else:
        log_filename = f"simulation_{topo_part}.log"

    log_path = os.path.join(results_dir, log_filename)

    file_handler = logging.FileHandler(log_path, mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)


if __name__ == '__main__':
    # Initialize console-only logging early; main() will reconfigure with a file handler once args are parsed.
    set_logger(topology=None)
    random.seed(1972)
    try:
        main(sys.argv[1:])
    except Exception as e:
        logging.exception("Simulation failed with an exception")
        raise
