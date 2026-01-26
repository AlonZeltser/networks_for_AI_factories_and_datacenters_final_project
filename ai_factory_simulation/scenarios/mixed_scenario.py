from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import hashlib

from network_simulation.scenario import Scenario

from ai_factory_simulation.core.runner import JobRunner
from ai_factory_simulation.scenarios.network_flow_injector import NetworkFlowInjector
from ai_factory_simulation.scenarios.mice_flow_injector import MiceConfig, MiceFlowInjector
from ai_factory_simulation.traffic.collective import CollectiveAlgorithm
from ai_factory_simulation.workloads.mixed_scenario import (
    MixedScenarioTpHeavyConfig,
    MixedScenarioPpDpConfig,
    build_mixed_scenario_tp_heavy,
    build_mixed_scenario_pp_dp,
)
from ai_factory_simulation.scenarios.rack_utils import default_rack_key


AllocationMode = Literal["rack_balanced", "contiguous"]
StagePlacementMode = Literal["topology_aware", "topology_unaware"]


def _default_rack_key(host_id: str) -> int:
    return default_rack_key(host_id)


def _sha1_tuples(rows: list[tuple]) -> str:
    h = hashlib.sha1()
    for r in rows:
        h.update(repr(r).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


@dataclass(frozen=True)
class MixedScenario(Scenario):
    """Mixed scenario: two concurrent jobs (tp_heavy=TP-heavy, pp_dp=PP+DP) on the AI-factory SU topology."""

    name: str = "ai-factory-su-mixed_scenario"

    # General
    steps: int = 400
    # Per-job steps (if not provided, fall back to `steps`).
    tp_heavy_steps: int | None = None
    pp_dp_steps: int | None = None

    seed: int = 1234
    traffic_scale: float = 1.0

    allocation_mode: AllocationMode = "rack_balanced"
    stage_placement_mode: StagePlacementMode = "topology_aware"

    # tp_heavy (TP-heavy)
    tp_heavy_fwd_compute_ms: float = 5.0
    tp_heavy_micro_collectives: int = 32
    tp_heavy_micro_collective_bytes_per_participant: int = 1_048_576  # 1 MiB
    tp_heavy_micro_compute_gap_ms: float = 0.5
    tp_heavy_final_sync_bytes_per_participant: int = 16 * 1024 * 1024
    tp_heavy_tail_compute_ms: float = 2.0
    tp_heavy_gap_us: float = 100.0  # affects ring step timing internal to collective

    # pp_dp (PP+DP)
    pp_dp_microbatch_count: int = 8
    pp_dp_microbatch_gap_us: float = 75.0
    pp_dp_activation_bytes_per_microbatch: int = 2 * 1024 * 1024
    pp_dp_grad_bytes_per_microbatch: int = 2 * 1024 * 1024
    pp_dp_dp_sync_bytes_per_participant: int = 32 * 1024 * 1024
    pp_dp_tail_compute_ms: float = 3.0

    # Debug / determinism
    record_first_step_flow_signatures: bool = True

    # Optional background mice traffic
    mice: MiceConfig | None = None

    def install(self, network) -> None:
        all_hosts = sorted(network.hosts.keys())
        if len(all_hosts) % 2 != 0:
            raise ValueError("mixed_scenario requires an even number of hosts")

        racks: dict[int, list[str]] = {}
        for h in all_hosts:
            rack = _default_rack_key(h)
            racks.setdefault(rack, []).append(h)
        for r in racks.values():
            r.sort()

        half_total = len(all_hosts) // 2

        if self.allocation_mode == "contiguous":
            tp_heavy_nodes = all_hosts[:half_total]
            pp_dp_nodes = all_hosts[half_total:]
        elif self.allocation_mode == "rack_balanced":
            tp_heavy_nodes = []
            pp_dp_nodes = []

            # If rack parsing doesn't match expectations, fall back to simple deterministic split.
            rack_ids = sorted(racks.keys())
            uniform_racks = len(rack_ids) > 0 and all(len(racks[r]) == len(racks[rack_ids[0]]) for r in rack_ids)
            expected_half_per_rack = (len(racks[rack_ids[0]]) // 2) if rack_ids else 0

            if (not uniform_racks) or expected_half_per_rack == 0:
                tp_heavy_nodes = all_hosts[:half_total]
                pp_dp_nodes = all_hosts[half_total:]
            else:
                # Deterministic, rack-balanced split.
                for rack_id in rack_ids:
                    nodes = sorted(racks[rack_id])
                    a_cnt = len(nodes) // 2
                    tp_heavy_nodes.extend(nodes[:a_cnt])
                    pp_dp_nodes.extend(nodes[a_cnt:])

                # Fix globally to exact half if any rack sizes are odd.
                if len(tp_heavy_nodes) != half_total:
                    combined = sorted(tp_heavy_nodes + pp_dp_nodes)
                    tp_heavy_nodes = combined[:half_total]
                    pp_dp_nodes = combined[half_total:]
        else:
            raise ValueError("allocation_mode must be 'rack_balanced' or 'contiguous'")

        if len(tp_heavy_nodes) != half_total or len(pp_dp_nodes) != half_total:
            raise AssertionError("Expected equal split between jobs")

        # Stage placement for pp_dp into 4 stages.
        stage_nodes: list[list[str]] = _assign_stages(
            pp_dp_nodes,
            racks=racks,
            mode=self.stage_placement_mode,
            seed=int(self.seed),
        )

        tp_steps = int(self.tp_heavy_steps) if self.tp_heavy_steps is not None else int(self.steps)
        pp_steps = int(self.pp_dp_steps) if self.pp_dp_steps is not None else int(self.steps)

        tp_heavy_cfg = MixedScenarioTpHeavyConfig(
            steps=tp_steps,
            seed=int(self.seed) ^ 0xA5A5,
            traffic_scale=float(self.traffic_scale),
            fwd_compute_ms=float(self.tp_heavy_fwd_compute_ms),
            micro_collectives=int(self.tp_heavy_micro_collectives),
            micro_collective_bytes_per_participant=int(self.tp_heavy_micro_collective_bytes_per_participant),
            micro_compute_gap_ms=float(self.tp_heavy_micro_compute_gap_ms),
            final_sync_bytes_per_participant=int(self.tp_heavy_final_sync_bytes_per_participant),
            tail_compute_ms=float(self.tp_heavy_tail_compute_ms),
            gap_us=float(self.tp_heavy_gap_us),
            algorithm=CollectiveAlgorithm.RING,
        )

        pp_dp_cfg = MixedScenarioPpDpConfig(
            steps=pp_steps,
            seed=int(self.seed) ^ 0x5A5A,
            traffic_scale=float(self.traffic_scale),
            microbatch_count=int(self.pp_dp_microbatch_count),
            microbatch_gap_us=float(self.pp_dp_microbatch_gap_us),
            activation_bytes_per_microbatch=int(self.pp_dp_activation_bytes_per_microbatch),
            grad_bytes_per_microbatch=int(self.pp_dp_grad_bytes_per_microbatch),
            dp_sync_bytes_per_participant=int(self.pp_dp_dp_sync_bytes_per_participant),
            tail_compute_ms=float(self.pp_dp_tail_compute_ms),
        )

        tp_heavy = build_mixed_scenario_tp_heavy(participants=tp_heavy_nodes, config=tp_heavy_cfg, job_name="mixed-scenario-tp_heavy")
        pp_dp = build_mixed_scenario_pp_dp(participants=pp_dp_nodes, stage_nodes=stage_nodes, config=pp_dp_cfg, job_name="mixed-scenario-pp_dp")

        injector = NetworkFlowInjector(network)

        # Optional background mice traffic.
        if self.mice is not None and self.mice.enabled:
            MiceFlowInjector(network=network, injector=injector, cfg=self.mice).install()

        runner_tp = JobRunner(sim=network.simulator, injector=injector, job=tp_heavy)
        runner_pp = JobRunner(sim=network.simulator, injector=injector, job=pp_dp)

        metrics_tp = runner_tp.run()
        metrics_pp = runner_pp.run()

        # Optional determinism hook: record flow signatures for first step (before running) so repeated runs match.
        # We hash the flow tuples for a stable fingerprint without dumping huge structures.
        if self.record_first_step_flow_signatures:
            sig_tp = _job_first_step_signature(tp_heavy)
            sig_pp = _job_first_step_signature(pp_dp)
            network.entities["mixed_scenario_first_step_signature"] = {"tp_heavy": sig_tp, "pp_dp": sig_pp}

        network.entities["ai_factory_job_metrics"] = {"tp_heavy": metrics_tp, "pp_dp": metrics_pp}

    def parameters_summary(self):
        out = super().parameters_summary()
        out.update(
            {
                "steps": self.steps,
                "tp_heavy_steps": (self.tp_heavy_steps if self.tp_heavy_steps is not None else self.steps),
                "pp_dp_steps": (self.pp_dp_steps if self.pp_dp_steps is not None else self.steps),
                "seed": self.seed,
                "traffic_scale": self.traffic_scale,
                "allocation_mode": self.allocation_mode,
                "stage_placement_mode": self.stage_placement_mode,
                "tp_heavy_micro_collectives": self.tp_heavy_micro_collectives,
                "pp_dp_microbatch_count": self.pp_dp_microbatch_count,
            }
        )
        if self.mice is not None and self.mice.enabled:
            out["mice_enabled"] = True
            out["mice_interarrival_s"] = self.mice.interarrival_s
            out["mice_end_time_s"] = self.mice.end_time_s
            out["mice_packets_range"] = f"{self.mice.min_packets}-{self.mice.max_packets}"
            out["mice_force_cross_rack"] = self.mice.force_cross_rack
        return out


def _assign_stages(
    pp_dp_nodes: list[str],
    *,
    racks: dict[int, list[str]],
    mode: StagePlacementMode,
    seed: int,
) -> list[list[str]]:
    nodes = list(pp_dp_nodes)

    if mode == "topology_aware":
        # Group by rack id order, then split into 4 contiguous stage groups.
        rack_ordered: list[str] = []
        for rack_id in sorted(racks.keys()):
            # Only include nodes that are in jobB.
            for h in racks[rack_id]:
                if h in pp_dp_nodes:
                    rack_ordered.append(h)
        nodes = rack_ordered
    elif mode == "topology_unaware":
        # Deterministic permutation.
        import random

        rnd = random.Random(int(seed))
        rnd.shuffle(nodes)
    else:
        raise ValueError("stage_placement_mode must be 'topology_aware' or 'topology_unaware'")

    if len(nodes) % 4 != 0:
        raise ValueError("pp_dp node count must be divisible by 4")

    per_stage = len(nodes) // 4
    stages = [nodes[i * per_stage : (i + 1) * per_stage] for i in range(4)]

    # Keep each stage internally deterministic.
    for s in stages:
        s.sort()
    return stages


def _job_first_step_signature(job) -> str:
    tuples: list[tuple] = []
    step0 = job.steps[0]
    for ph in step0.phases:
        if hasattr(ph, "buckets"):
            for b in ph.buckets:
                for f in b.flows:
                    tuples.append((f.src_node_id, f.dst_node_id, int(f.size_bytes), float(f.start_time), f.tag, int(f.job_id)))
    tuples.sort()
    return _sha1_tuples(tuples)


__all__ = ["MixedScenario"]
