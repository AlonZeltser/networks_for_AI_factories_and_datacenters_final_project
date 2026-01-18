"""AI factory network simulation entrypoint (YAML-driven).

Usage:
    python ai_factory_network_simulation.py <path-to-config.yaml>

This is a thin wrapper around the AI Factory simulation runner logic.
"""

import argparse
import logging
import sys
import time
from typing import Any, Dict

import yaml

from ai_factory_simulation.scenarios.ai_factory_su_scenario import AIFactorySUDpHeavyScenario
from network_simulators.ai_factory_su_network_simulator import AIFactorySUNetworkSimulator
from visualization.experiment_visualizer import visualize_experiment_results


def _require_dict(d: Any, path: str) -> Dict[str, Any]:
    if not isinstance(d, dict):
        raise ValueError(f"Expected mapping at '{path}', got {type(d).__name__}")
    return d


def _get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    return d.get(key, default)


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    return _require_dict(data, "/")


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)


def _build_network(cfg: Dict[str, Any], *, message_verbose: bool, verbose_route: bool):
    topo = _require_dict(cfg.get("topology", {}), "topology")
    topo_type = str(_get(topo, "type", "ai-factory-su")).lower()
    if topo_type != "ai-factory-su":
        raise ValueError("This runner supports only topology.type='ai-factory-su'")

    links_cfg = _require_dict(topo.get("links", {}), "topology.links")
    link_failure_percent = float(_get(links_cfg, "failure_percent", 0.0))

    return AIFactorySUNetworkSimulator(
        max_path=int(_get(topo, "max_path", 64)),
        link_failure_percent=link_failure_percent,
        verbose=message_verbose,
        verbose_route=verbose_route,
    )


def _build_scenario(cfg: Dict[str, Any]):
    scen = _require_dict(cfg.get("scenario", {}), "scenario")
    name = str(_get(scen, "name", "ai-factory-su-workload1-dp-heavy")).lower()

    if name != "ai-factory-su-workload1-dp-heavy":
        raise ValueError("This runner supports only scenario.name='ai-factory-su-workload1-dp-heavy'")

    params = _require_dict(scen.get("params", {}), "scenario.params")
    return AIFactorySUDpHeavyScenario(
        steps=int(_get(params, "steps", 2)),
        seed=int(_get(params, "seed", 1972)),
        num_buckets=int(_get(params, "num_buckets", 2)),
        bucket_bytes_per_participant=int(_get(params, "bucket_bytes_per_participant", 8 * 1024 * 1024)),
        gap_us=float(_get(params, "gap_us", 0.0000001)),
    )


def parse_args(argv):
    p = argparse.ArgumentParser(description="AI Factory Network Simulation (YAML-driven)")
    p.add_argument("config", help="Path to YAML configuration file")
    return p.parse_args(argv)


def main(argv) -> int:
    args = parse_args(argv)
    cfg = _load_yaml(args.config)

    run_cfg = _require_dict(cfg.get("run", {}), "run")
    debug = bool(_get(run_cfg, "debug", False))
    message_verbose = bool(_get(run_cfg, "message_verbose", False))
    verbose_route = bool(_get(run_cfg, "verbose_route", False))
    visualize = bool(_get(run_cfg, "visualize", True))

    _configure_logging(debug=debug)

    network = _build_network(cfg, message_verbose=message_verbose, verbose_route=verbose_route)
    scenario = _build_scenario(cfg)

    network.create()
    network.assign_scenario(scenario)

    logging.info("Starting AI factory simulation")
    start = time.perf_counter()
    network.run()
    elapsed = time.perf_counter() - start
    logging.info("Simulation run time: %.3f seconds", elapsed)

    results = network.get_results()

    if visualize:
        visualize_experiment_results([results])

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

