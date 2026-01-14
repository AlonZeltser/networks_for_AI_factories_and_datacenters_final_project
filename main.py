import random
import logging
import argparse
import sys
from typing import List
import os


from network_simulation.simulator_creator import SimulatorCreator
from scenarios.fat_tree_topo_creator import FatTreeTopoCreator
from scenarios.hsh_creator import HSHCreator
from scenarios.simple_star_creator import SimpleStarCreator
from visualization.experiment_visualizer import visualize_experiment_results



def create_creators_from_args(args) -> List[SimulatorCreator]:
    results: List[SimulatorCreator] = []
    visualize = args.visualize
    topology = args.t.lower()
    verbose = args.message_verbose
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
                results.append(FatTreeTopoCreator(k=k, max_path=1000000, visualize=visualize, link_failure_percent=link_failure, verbose=verbose))
    elif topology == 'hsh':
        for link_failure in link_failures:
            logging.info(f"Creating HSH topology with link-failure={link_failure}%")
            results.append(HSHCreator(visualize, link_failure_percent=link_failure, max_path=3, verbose=verbose))
    elif topology == 'simple-star':
        for link_failure in link_failures:
            logging.info(f"Creating Simple Star topology with link-failure={link_failure}%")
            results.append(SimpleStarCreator(visualize, link_failure_percent=link_failure, max_path=6, verbose=verbose))
    else:
        raise ValueError(f"Unknown topology '{args.t}'. Valid options: fat-tree, hsh, simple-star")

    return results


def parse_args(argv):
    parser = argparse.ArgumentParser(description='Network simulator runner')
    parser.add_argument('-t', default='fat-tree',
                        help='Type of topology: fat-tree, hsh (simplest, for demo), simple-star (simple tree with 2 levels, for demo and debugging)')
    parser.add_argument('-k', nargs='+', type=int, default=[4],
                        help='(fat-tree only) list of number of ports per switch (must be even)')
    parser.add_argument('-visualize', action='store_true', dest='visualize',
                        help='Enable topology on screen visualization (single boolean flag). If not set, visualizations are still saved to files.')
    parser.add_argument('-link-failure', nargs='+', type=float, default=[0.0],
                        help='list of probability of links to fail in each test. Fraction (0-100) of links to fail')
    parser.add_argument('-message_verbose', required=False, action='store_true', dest='message_verbose', default=False,
                        help='Enable message_verbose logging output to console')
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    logging.info(f"Starting network simulation. topology={args.t}, k={args.k}, visualize={args.visualize}, message_verbose={args.message_verbose}, link-failure={args.link_failure}")

    creators = create_creators_from_args(args)
    aggregated_results = []
    for creator in creators:
        simulator = creator.create_simulator()
        logging.info(f"Starting simulation")
        simulator.run()
        logging.info(f"Simulation finished. collecting results")
        results = creator.get_results()
        stats = results['run statistics']
        message = "\n".join(f"{k}: {v}" for k, v in stats.items() if not isinstance(v, List))
        logging.info(f"Simulation stats: \n {message}")
        aggregated_results.append(results)


    # pass the single boolean visualize flag so the visualizer can choose
    # whether to open plots (non-blocking) or only save them
    visualize_experiment_results(aggregated_results)




def set_logger():
    logger = logging.getLogger()
    # set root logger to DEBUG so handlers themselves decide what to record
    logger.setLevel(logging.DEBUG)

    # remove any existing handlers so we don't duplicate output when reloading
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    # make log path absolute (script directory) so running from other CWD still creates the file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base_dir, "simulation.log")

    # File handler: keep INFO and above in file to avoid noisy debug output
    file_handler = logging.FileHandler(log_path, mode="w")
    file_handler.setLevel(logging.DEBUG)

    # Console-only logging at INFO
    # IMPORTANT: StreamHandler() defaults to sys.stderr, which many consoles/IDEs display in red.
    # Use stdout so INFO logs don't look like errors.
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
        datefmt="%H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Silence matplotlib font_manager and other message_verbose matplotlib debug messages
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)


if __name__ == '__main__':
    set_logger()
    random.seed(1972)
    try:
        main(sys.argv[1:])
    except Exception as e:
        logging.exception("Simulation failed with an exception")
        raise
