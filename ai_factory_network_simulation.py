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
from network_simulators.ai_factory_su_network_simulator import AIFactorySUNetworkSimulator, AIFactorySUTopologyConfig
from visualization.experiment_visualizer import visualize_experiment_results
from ai_factory_simulation.scenarios.mice_flow_injector import MiceConfig


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


def _configure_logging(file_debug: bool, *, run_tag: str) -> str:
    """Configure logging (console + per-run file) via log_setup.

    Console is always at INFO level.
    File is at DEBUG level if file_debug=True, else INFO.
    """
    return configure_run_logging(
        run_tag,
        console_level=logging.INFO,
        file_level=logging.DEBUG if file_debug else logging.INFO,
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

    # Topology sizing (required)
    su_cfg = _require_dict(_get(topo, "ai_factory_su"), "topology.ai_factory_su")
    topology_config = AIFactorySUTopologyConfig.from_mapping(su_cfg)

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
        topology_config=topology_config,
    )


def _build_scenario(cfg: Dict[str, Any]):
    scen = _require_dict(cfg.get("scenario", {}), "scenario")
    name = str(scen["name"]).lower()

    params = _require_dict(scen.get("params", {}), "scenario.params")

    # Optional mice config (shared by scenarios)
    topo = _require_dict(cfg.get("topology", {}), "topology")
    mtu = int(topo.get("mtu", 4096))
    mice_cfg = params.get("mice")
    mice = None
    if mice_cfg is not None:
        mice_cfg = _require_dict(mice_cfg, "scenario.params.mice")
        mice = MiceConfig(
            enabled=bool(mice_cfg.get("enabled", False)),
            seed=int(mice_cfg.get("seed", int(params.get("seed", 0)) ^ 0xC0FFEE)),
            start_delay_s=float(mice_cfg.get("start_delay_s", 0.0)),
            end_time_s=float(mice_cfg.get("end_time_s", float("inf"))),
            interarrival_s=float(mice_cfg.get("interarrival_s", 0.001)),
            min_packets=int(mice_cfg.get("min_packets", 1)),
            max_packets=int(mice_cfg.get("max_packets", 4)),
            mtu_bytes=int(mice_cfg.get("mtu_bytes", mtu)),
            force_cross_rack=bool(mice_cfg.get("force_cross_rack", True)),
        )

    if name == "ai-factory-su-workload1-dp-heavy":
        return AIFactorySUDpHeavyScenario(
            steps=int(params["steps"]),
            seed=int(params["seed"]),
            num_buckets=int(params["num_buckets"]),
            bucket_bytes_per_participant=int(params["bucket_bytes_per_participant"]),
            gap_us=float(params["gap_us"]),
            t_fwd_bwd_ms=float(params["t_fwd_bwd_ms"]),
            optimizer_ms=float(params["optimizer_ms"]),
            mice=mice,
        )

    if name == "ai-factory-su-mixed_scenario":
        # Backward compatible:
        # - old: params.steps
        # - old per-job: params.jobs.jobA.steps / params.jobs.jobB.steps
        # - new per-job: params.jobs.tp_heavy.steps / params.jobs.pp_dp.steps
        # - old job params: jobA_* / jobB_*
        # - new job params: tp_heavy_* / pp_dp_*
        jobs_cfg = params.get("jobs", {})
        jobs_cfg = _require_dict(jobs_cfg, "scenario.params.jobs") if jobs_cfg is not None else {}

        # Prefer new keys, fall back to old.
        tp_cfg = jobs_cfg.get("tp_heavy", jobs_cfg.get("jobA", {}))
        pp_cfg = jobs_cfg.get("pp_dp", jobs_cfg.get("jobB", {}))
        tp_cfg = _require_dict(tp_cfg, "scenario.params.jobs.tp_heavy") if tp_cfg is not None else {}
        pp_cfg = _require_dict(pp_cfg, "scenario.params.jobs.pp_dp") if pp_cfg is not None else {}

        def _p(*keys: str):
            for k in keys:
                if k in params:
                    return params[k]
            raise KeyError(f"Missing required scenario.params key. Tried: {keys}")

        return MixedScenario(
            steps=int(params["steps"]),
            tp_heavy_steps=(int(tp_cfg["steps"]) if "steps" in tp_cfg else None),
            pp_dp_steps=(int(pp_cfg["steps"]) if "steps" in pp_cfg else None),
            seed=int(params["seed"]),
            traffic_scale=float(params["traffic_scale"]),
            allocation_mode=str(params["allocation_mode"]),
            stage_placement_mode=str(params["stage_placement_mode"]),
            tp_heavy_fwd_compute_ms=float(_p("tp_heavy_fwd_compute_ms", "jobA_fwd_compute_ms")),
            tp_heavy_micro_collectives=int(_p("tp_heavy_micro_collectives", "jobA_micro_collectives")),
            tp_heavy_micro_collective_bytes_per_participant=int(
                _p("tp_heavy_micro_collective_bytes_per_participant", "jobA_micro_collective_bytes_per_participant")
            ),
            tp_heavy_micro_compute_gap_ms=float(_p("tp_heavy_micro_compute_gap_ms", "jobA_micro_compute_gap_ms")),
            tp_heavy_final_sync_bytes_per_participant=int(
                _p("tp_heavy_final_sync_bytes_per_participant", "jobA_final_sync_bytes_per_participant")
            ),
            tp_heavy_tail_compute_ms=float(_p("tp_heavy_tail_compute_ms", "jobA_tail_compute_ms")),
            tp_heavy_gap_us=float(_p("tp_heavy_gap_us", "jobA_gap_us")),
            pp_dp_microbatch_count=int(_p("pp_dp_microbatch_count", "jobB_microbatch_count")),
            pp_dp_microbatch_gap_us=float(_p("pp_dp_microbatch_gap_us", "jobB_microbatch_gap_us")),
            pp_dp_activation_bytes_per_microbatch=int(_p("pp_dp_activation_bytes_per_microbatch", "jobB_activation_bytes_per_microbatch")),
            pp_dp_grad_bytes_per_microbatch=int(_p("pp_dp_grad_bytes_per_microbatch", "jobB_grad_bytes_per_microbatch")),
            pp_dp_dp_sync_bytes_per_participant=int(_p("pp_dp_dp_sync_bytes_per_participant", "jobB_dp_sync_bytes_per_participant")),
            pp_dp_tail_compute_ms=float(_p("pp_dp_tail_compute_ms", "jobB_tail_compute_ms")),
            record_first_step_flow_signatures=bool(params["record_first_step_flow_signatures"]),
            mice=mice,
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
    file_debug = bool(run_cfg.get("file_debug", run_cfg.get("debug", False)))  # Backward compat with old 'debug' key
    message_verbose = bool(run_cfg["message_verbose"])
    verbose_route = bool(run_cfg["verbose_route"])
    visualize = bool(run_cfg["visualize"])

    topo_type = str(_require_dict(cfg.get("topology", {}), "topology")["type"])
    scen_name = str(_require_dict(cfg.get("scenario", {}), "scenario")["name"])
    logfile_path = _configure_logging(file_debug=file_debug, run_tag=f"{topo_type}.{scen_name}")
    logging.info("Logging to console and file: %s", logfile_path)
    logging.info(f"Loaded configuration from: {yaml_path}")

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
