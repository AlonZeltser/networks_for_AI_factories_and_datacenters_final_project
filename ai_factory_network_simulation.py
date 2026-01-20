"""AI factory network simulation entrypoint (YAML-driven).

Usage:
    python ai_factory_network_simulation.py <path-to-config.yaml>

This is a thin wrapper around the AI Factory simulation runner logic.
"""

import argparse
import logging
import os
import sys
import time
from typing import Any, Dict

import yaml

from log_setup import configure_run_logging
from ai_factory_simulation.scenarios.ai_factory_su_dp_heavy_scenario import AIFactorySUDpHeavyScenario
from ai_factory_simulation.scenarios.mixed_scenario import MixedScenario
from network_simulation.network_node import RoutingMode
from network_simulators.ai_factory_su_network_simulator import AIFactorySUNetworkSimulator
from visualization.experiment_visualizer import visualize_experiment_results


def _require_dict(d: Any, path: str) -> Dict[str, Any]:
    if not isinstance(d, dict):
        raise ValueError(f"Expected mapping at '{path}', got {type(d).__name__}")
    return d


def _get(d: Dict[str, Any], key: str) -> Any:
    return d[key]


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    return _require_dict(data, "/")


def _configure_logging(debug: bool, *, run_tag: str) -> str:
    """Configure logging (console + per-run file) via log_setup."""
    return configure_run_logging(
        run_tag,
        console_level=logging.DEBUG if debug else logging.INFO,
        file_level=logging.DEBUG,
        force=True,
    )


def _parse_routing_mode(raw: Any, *, path: str) -> RoutingMode:
    """Parse a routing mode value from config.

    Accepts: 'ecmp' | 'adaptive' (case-insensitive).
    """

    if not isinstance(raw, str):
        raise ValueError(f"Expected string at '{path}', got {type(raw).__name__}")

    v = raw.strip().lower()
    if v in {"ecmp", "hash"}:
        return RoutingMode.ECMP
    if v in {"adaptive", "adapt"}:
        return RoutingMode.ADAPTIVE

    raise ValueError(f"Invalid routing mode at '{path}': {raw!r}. Valid: ecmp | adaptive")


def _build_network(cfg: Dict[str, Any], *, message_verbose: bool, verbose_route: bool):
    topo = _require_dict(cfg.get("topology", {}), "topology")
    topo_type = str(topo["type"]).lower()
    if topo_type != "ai-factory-su":
        raise ValueError("This runner supports only topology.type='ai-factory-su'")

    routing_cfg = _require_dict(topo.get("routing", {}), "topology.routing")
    routing_mode = _parse_routing_mode(routing_cfg["mode"], path="topology.routing.mode")

    ecmp_flowlet_n_packets = int(routing_cfg["ecmp_flowlet_n_packets"])

    links_cfg = _require_dict(topo.get("links", {}), "topology.links")
    link_failure_percent = float(links_cfg["failure_percent"])

    bandwidth_cfg = _require_dict(links_cfg.get("bandwidth_bps", {}), "topology.links.bandwidth_bps")
    server_to_leaf_bandwidth_bps = float(bandwidth_cfg["server_to_leaf"])
    leaf_to_spine_bandwidth_bps = float(bandwidth_cfg["leaf_to_spine"])

    # Network parameters
    mtu = int(topo["mtu"])
    ttl = int(topo["ttl"])

    return AIFactorySUNetworkSimulator(
        max_path=int(topo["max_path"]),
        link_failure_percent=link_failure_percent,
        routing_mode=routing_mode,
        ecmp_flowlet_n_packets=ecmp_flowlet_n_packets,
        verbose=message_verbose,
        verbose_route=verbose_route,
        server_to_leaf_bandwidth_bps=server_to_leaf_bandwidth_bps,
        leaf_to_spine_bandwidth_bps=leaf_to_spine_bandwidth_bps,
        mtu=mtu,
        ttl=ttl,
    )


def _build_scenario(cfg: Dict[str, Any]):
    scen = _require_dict(cfg.get("scenario", {}), "scenario")
    name = str(scen["name"]).lower()

    params = _require_dict(scen.get("params", {}), "scenario.params")

    if name == "ai-factory-su-workload1-dp-heavy":
        return AIFactorySUDpHeavyScenario(
            steps=int(params["steps"]),
            seed=int(params["seed"]),
            num_buckets=int(params["num_buckets"]),
            bucket_bytes_per_participant=int(params["bucket_bytes_per_participant"]),
            gap_us=float(params["gap_us"]),
            t_fwd_bwd_ms=float(params["t_fwd_bwd_ms"]),
            optimizer_ms=float(params["optimizer_ms"]),
        )

    if name == "ai-factory-su-mixed_scenario":
        # Keep params explicit: no silent defaults.
        return MixedScenario(
            steps=int(params["steps"]),
            seed=int(params["seed"]),
            traffic_scale=float(params["traffic_scale"]),
            allocation_mode=str(params["allocation_mode"]),
            stage_placement_mode=str(params["stage_placement_mode"]),
            jobA_fwd_compute_ms=float(params["jobA_fwd_compute_ms"]),
            jobA_micro_collectives=int(params["jobA_micro_collectives"]),
            jobA_micro_collective_bytes_per_participant=int(params["jobA_micro_collective_bytes_per_participant"]),
            jobA_micro_compute_gap_ms=float(params["jobA_micro_compute_gap_ms"]),
            jobA_final_sync_bytes_per_participant=int(params["jobA_final_sync_bytes_per_participant"]),
            jobA_tail_compute_ms=float(params["jobA_tail_compute_ms"]),
            jobA_gap_us=float(params["jobA_gap_us"]),
            jobB_microbatch_count=int(params["jobB_microbatch_count"]),
            jobB_microbatch_gap_us=float(params["jobB_microbatch_gap_us"]),
            jobB_activation_bytes_per_microbatch=int(params["jobB_activation_bytes_per_microbatch"]),
            jobB_grad_bytes_per_microbatch=int(params["jobB_grad_bytes_per_microbatch"]),
            jobB_dp_sync_bytes_per_participant=int(params["jobB_dp_sync_bytes_per_participant"]),
            jobB_tail_compute_ms=float(params["jobB_tail_compute_ms"]),
            record_first_step_flow_signatures=bool(params["record_first_step_flow_signatures"]),
        )

    raise ValueError(
        "This runner supports only scenario.name='ai-factory-su-workload1-dp-heavy' or 'ai-factory-su-mixed_scenario'"
    )


def _resolve_yaml_arg(arg: str) -> str:
    """Resolve CLI arg into a YAML path.

    Accepts either:
    - a direct path to a .yaml/.yml file
    - a known alias (handled by arg_to_yaml)
    """
    if not isinstance(arg, str) or not arg:
        raise ValueError("config argument must be a non-empty string")

    # If it looks like a YAML path and exists, use it directly.
    if not arg.lower().endswith((".yaml", ".yml")):
        raise ValueError("Config argument must be a YAML file path or a known alias")

    candidate = os.path.abspath(arg)
    if not os.path.exists(candidate):
        raise FileNotFoundError(f"YAML configuration file not found: {candidate}")
    return candidate




def parse_args(argv):
    p = argparse.ArgumentParser(description="AI Factory Network Simulation (YAML-driven)")
    p.add_argument("config", help="Path to YAML configuration file")
    return p.parse_args(argv)


def main(argv) -> int:
    args = parse_args(argv)
    yaml_path = _resolve_yaml_arg(args.config)
    cfg = _load_yaml(yaml_path)

    run_cfg = _require_dict(cfg.get("run", {}), "run")
    debug = bool(run_cfg["debug"])
    message_verbose = bool(run_cfg["message_verbose"])
    verbose_route = bool(run_cfg["verbose_route"])
    visualize = bool(run_cfg["visualize"])

    topo_type = str(_require_dict(cfg.get("topology", {}), "topology")["type"])
    scen_name = str(_require_dict(cfg.get("scenario", {}), "scenario")["name"])
    logfile_path = _configure_logging(debug=debug, run_tag=f"{topo_type}.{scen_name}")
    logging.info("Logging to console and file: %s", logfile_path)

    network = _build_network(cfg, message_verbose=message_verbose, verbose_route=verbose_route)
    scenario = _build_scenario(cfg)

    network.create(visualize)
    network.assign_scenario(scenario)

    logging.info("Starting AI factory simulation")
    start = time.perf_counter()
    network.run()
    elapsed = time.perf_counter() - start
    logging.info("Simulation run time: %.3f seconds", elapsed)

    results = network.get_results()

    # Print a readable results summary to logs (restored behavior).
    try:
        topo_summary = results.get("topology summary", {})
        params_summary = results.get("parameters summary", {})
        stats = results.get("run statistics", {})

        def _fmt_block(d: Any) -> str:
            return "\n".join(f"{k}: {v}" for k, v in d.items()) if isinstance(d, dict) and d else "(empty)"

        logging.info("Results summary - Topology:\n%s", _fmt_block(topo_summary))
        logging.info("Results summary - Parameters:\n%s", _fmt_block(params_summary))
        logging.info("Results summary - Run statistics:\n%s", _fmt_block(stats))
    except Exception:
        logging.exception("Failed to log results summary")

    if visualize:
        visualize_experiment_results([results])

    # Always generate send timeline visualization to show messaging distribution over time
    from visualization.experiment_visualizer import visualize_send_timeline
    packet_timeline = results.get('packet_timeline', [])
    params = results.get('parameters summary', {})
    stats = results.get('run statistics', {})
    routing_mode = params.get('routing_mode', '')
    total_time = stats.get('total run time (simulator time in seconds)', 0)
    if packet_timeline:
        visualize_send_timeline(packet_timeline, total_time, routing_mode, out_dir="results")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
