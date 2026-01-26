from __future__ import annotations

from network_simulation.scenario import Scenario

from ai_factory_simulation.core.runner import JobRunner
from ai_factory_simulation.scenarios.network_flow_injector import NetworkFlowInjector
from ai_factory_simulation.traffic.collective import CollectiveAlgorithm
from ai_factory_simulation.workloads.workload1_dp_heavy import Workload1Config, build_workload1_dp_heavy_job
from ai_factory_simulation.scenarios.mice_flow_injector import MiceConfig, MiceFlowInjector


class AIFactorySUDpHeavyScenario(Scenario):
    """Workload1 DP-heavy on the AI-Factory SU topology."""

    def __init__(
        self,
        steps: int,
        seed: int,
        num_buckets: int,
        bucket_bytes_per_participant: int,
        gap_us: float,
        t_fwd_bwd_ms: float,
        optimizer_ms: float,
        *,
        mice: MiceConfig | None = None,
    ):
        self.steps = steps
        self.seed = seed
        self.num_buckets = num_buckets
        self.bucket_bytes_per_participant = bucket_bytes_per_participant
        self.gap_us = gap_us
        self.t_fwd_bwd_ms = t_fwd_bwd_ms
        self.optimizer_ms = optimizer_ms
        self.mice = mice

    def install(self, network) -> None:
        participants = sorted(network.hosts.keys())
        cfg = Workload1Config(
            steps=int(self.steps),
            num_buckets=int(self.num_buckets),
            bucket_bytes_per_participant=int(self.bucket_bytes_per_participant),
            algorithm=CollectiveAlgorithm.RING,
            gap_us=float(self.gap_us),
            seed=int(self.seed),
            t_fwd_bwd_ms=float(self.t_fwd_bwd_ms),
            optimizer_ms=float(self.optimizer_ms),
        )
        job = build_workload1_dp_heavy_job(participants=participants, config=cfg)

        injector = NetworkFlowInjector(network)

        # Optional background mice traffic.
        if self.mice is not None and self.mice.enabled:
            MiceFlowInjector(network=network, injector=injector, cfg=self.mice).install()

        runner = JobRunner(sim=network.simulator, injector=injector, job=job)
        metrics = runner.run()

        # Expose for downstream result collection.
        network.entities["ai_factory_job_metrics"] = metrics

    def parameters_summary(self):
        out = super().parameters_summary()
        out.update(
            {
                "steps": self.steps,
                "seed": self.seed,
                "num_buckets": self.num_buckets,
                "bucket_bytes_per_participant": self.bucket_bytes_per_participant,
                "gap_us": self.gap_us,
                "t_fwd_bwd_ms": self.t_fwd_bwd_ms,
                "optimizer_ms": self.optimizer_ms,
            }
        )
        if self.mice is not None and self.mice.enabled:
            out["mice_enabled"] = True
            out["mice_interarrival_s"] = self.mice.interarrival_s
            out["mice_end_time_s"] = self.mice.end_time_s
            out["mice_packets_range"] = f"{self.mice.min_packets}-{self.mice.max_packets}"
            out["mice_force_cross_rack"] = self.mice.force_cross_rack
        return out

