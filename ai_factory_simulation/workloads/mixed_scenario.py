from __future__ import annotations

from dataclasses import dataclass

from ai_factory_simulation.core.entities import Bucket, CommPhase, ComputePhase, Job, JobStep
from ai_factory_simulation.core.ids import IdGenerator
from ai_factory_simulation.traffic.flow import Flow
from ai_factory_simulation.traffic.collective import CollectiveAlgorithm, CollectiveKind, expand_collective


@dataclass(frozen=True)
class MixedScenarioTpHeavyConfig:
    steps: int
    seed: int
    traffic_scale: float

    fwd_compute_ms: float
    micro_collectives: int
    micro_collective_bytes_per_participant: int
    micro_compute_gap_ms: float

    final_sync_bytes_per_participant: int
    tail_compute_ms: float

    gap_us: float
    algorithm: CollectiveAlgorithm


@dataclass(frozen=True)
class MixedScenarioPpDpConfig:
    steps: int
    seed: int
    traffic_scale: float

    microbatch_count: int
    microbatch_gap_us: float
    activation_bytes_per_microbatch: int
    grad_bytes_per_microbatch: int

    dp_sync_bytes_per_participant: int
    tail_compute_ms: float


def build_mixed_scenario_tp_heavy(
    *,
    participants: list[str],
    config: MixedScenarioTpHeavyConfig,
    job_name: str = "mixed-scenario-tp_heavy",
) -> Job:
    ids = IdGenerator(seed=config.seed)
    job_id = ids.next_int()

    steps: list[JobStep] = []
    for step_idx in range(int(config.steps)):
        phases = []

        phases.append(
            ComputePhase(
                phase_id=0,
                name="tp_heavy_compute_front",
                duration_s=float(config.fwd_compute_ms) / 1000.0,
            )
        )

        # TP micro-collectives: alternating comm + small compute gap.
        for m in range(int(config.micro_collectives)):
            bytes_pp = int(int(config.micro_collective_bytes_per_participant) * float(config.traffic_scale))
            coll = expand_collective(
                kind=CollectiveKind.ALL_REDUCE,
                algorithm=config.algorithm,
                participants=participants,
                bytes_per_participant=bytes_pp,
                start_time=0.0,
                gap_us=float(config.gap_us),
                ids=ids.child(f"tp_heavy/step{step_idx}/micro{m}/tp"),
                job_id=job_id,
                step_id=step_idx,
                phase_id=1 + (m * 2),
                bucket_id=0,
            )
            phases.append(
                CommPhase(
                    phase_id=1 + (m * 2),
                    name=f"tp_heavy_tp_micro_{m}",
                    buckets=[Bucket(bucket_id=0, flows=_retag(coll.flows, job_id=job_id, tag_prefix="tp_heavy_tp_micro"))],
                )
            )
            phases.append(
                ComputePhase(
                    phase_id=2 + (m * 2),
                    name=f"tp_heavy_gap_{m}",
                    duration_s=float(config.micro_compute_gap_ms) / 1000.0,
                )
            )

        # Final DP sync (heavier): reduce-scatter + all-gather.
        bytes_pp = int(int(config.final_sync_bytes_per_participant) * float(config.traffic_scale))
        rs = expand_collective(
            kind=CollectiveKind.REDUCE_SCATTER,
            algorithm=config.algorithm,
            participants=participants,
            bytes_per_participant=bytes_pp,
            start_time=0.0,
            gap_us=float(config.gap_us),
            ids=ids.child(f"tp_heavy/step{step_idx}/final/rs"),
            job_id=job_id,
            step_id=step_idx,
            phase_id=9991,
            bucket_id=0,
        )
        ag = expand_collective(
            kind=CollectiveKind.ALL_GATHER,
            algorithm=config.algorithm,
            participants=participants,
            bytes_per_participant=bytes_pp,
            start_time=0.0,
            gap_us=float(config.gap_us),
            ids=ids.child(f"tp_heavy/step{step_idx}/final/ag"),
            job_id=job_id,
            step_id=step_idx,
            phase_id=9992,
            bucket_id=0,
        )
        phases.append(
            CommPhase(
                phase_id=9993,
                name="tp_heavy_dp_sync",
                buckets=[Bucket(bucket_id=0, flows=_retag(rs.flows + ag.flows, job_id=job_id, tag_prefix="tp_heavy_dp_sync"))],
            )
        )

        phases.append(
            ComputePhase(
                phase_id=9994,
                name="tp_heavy_compute_tail",
                duration_s=float(config.tail_compute_ms) / 1000.0,
            )
        )

        steps.append(JobStep(step_id=step_idx, phases=phases))

    return Job(job_id=job_id, name=job_name, steps=steps, participants=participants)


def build_mixed_scenario_pp_dp(
    *,
    participants: list[str],
    stage_nodes: list[list[str]],
    config: MixedScenarioPpDpConfig,
    job_name: str = "mixed-scenario-pp_dp",
) -> Job:
    ids = IdGenerator(seed=config.seed)
    job_id = ids.next_int()

    # stage_nodes[k] is list of nodes in stage k.
    if len(stage_nodes) != 4:
        raise ValueError("MixedScenario pp_dp requires exactly 4 stages")
    if any(len(s) != len(stage_nodes[0]) for s in stage_nodes):
        raise ValueError("All stages must have equal node counts")

    per_stage = len(stage_nodes[0])

    def partner(stage_k: int, idx: int) -> str:
        return stage_nodes[stage_k][idx]

    steps: list[JobStep] = []
    for step_idx in range(int(config.steps)):
        phases = []

        # Forward microbatches: 0->1, 1->2, 2->3 sequential per microbatch.
        fwd_bytes = int(int(config.activation_bytes_per_microbatch) * float(config.traffic_scale))
        bwd_bytes = int(int(config.grad_bytes_per_microbatch) * float(config.traffic_scale))

        phases.append(
            CommPhase(
                phase_id=100,
                name="pp_dp_pp_fwd",
                buckets=[
                    Bucket(
                        bucket_id=0,
                        flows=_build_pp_microbatches(
                            ids=ids.child(f"pp_dp/step{step_idx}/fwd"),
                            job_id=job_id,
                            step_id=step_idx,
                            phase_id=100,
                            stage_nodes=stage_nodes,
                            microbatch_count=int(config.microbatch_count),
                            microbatch_gap_us=float(config.microbatch_gap_us),
                            bytes_per_send=fwd_bytes,
                            direction="fwd",
                        ),
                    )
                ],
            )
        )

        phases.append(
            CommPhase(
                phase_id=200,
                name="pp_dp_pp_bwd",
                buckets=[
                    Bucket(
                        bucket_id=0,
                        flows=_build_pp_microbatches(
                            ids=ids.child(f"pp_dp/step{step_idx}/bwd"),
                            job_id=job_id,
                            step_id=step_idx,
                            phase_id=200,
                            stage_nodes=stage_nodes,
                            microbatch_count=int(config.microbatch_count),
                            microbatch_gap_us=float(config.microbatch_gap_us),
                            bytes_per_send=bwd_bytes,
                            direction="bwd",
                        ),
                    )
                ],
            )
        )

        # DP sync across all pp_dp participants.
        dp_bytes = int(int(config.dp_sync_bytes_per_participant) * float(config.traffic_scale))
        rs = expand_collective(
            kind=CollectiveKind.REDUCE_SCATTER,
            algorithm=CollectiveAlgorithm.RING,
            participants=participants,
            bytes_per_participant=dp_bytes,
            start_time=0.0,
            gap_us=0.0,
            ids=ids.child(f"pp_dp/step{step_idx}/dp/rs"),
            job_id=job_id,
            step_id=step_idx,
            phase_id=300,
            bucket_id=0,
        )
        ag = expand_collective(
            kind=CollectiveKind.ALL_GATHER,
            algorithm=CollectiveAlgorithm.RING,
            participants=participants,
            bytes_per_participant=dp_bytes,
            start_time=0.0,
            gap_us=0.0,
            ids=ids.child(f"pp_dp/step{step_idx}/dp/ag"),
            job_id=job_id,
            step_id=step_idx,
            phase_id=301,
            bucket_id=0,
        )
        phases.append(
            CommPhase(
                phase_id=302,
                name="pp_dp_dp_sync",
                buckets=[Bucket(bucket_id=0, flows=_retag(rs.flows + ag.flows, job_id=job_id, tag_prefix="pp_dp_dp_sync"))],
            )
        )

        phases.append(
            ComputePhase(
                phase_id=400,
                name="pp_dp_compute_tail",
                duration_s=float(config.tail_compute_ms) / 1000.0,
            )
        )

        steps.append(JobStep(step_id=step_idx, phases=phases))

    return Job(job_id=job_id, name=job_name, steps=steps, participants=participants)


def _build_pp_microbatches(
    *,
    ids: IdGenerator,
    job_id: int,
    step_id: int,
    phase_id: int,
    stage_nodes: list[list[str]],
    microbatch_count: int,
    microbatch_gap_us: float,
    bytes_per_send: int,
    direction: str,
) -> list[Flow]:
    # Deterministic, sequential microbatch bursts.
    if direction not in {"fwd", "bwd"}:
        raise ValueError("direction must be 'fwd' or 'bwd'")

    flows: list[Flow] = []
    per_stage = len(stage_nodes[0])

    for mb in range(int(microbatch_count)):
        base_t = mb * (float(microbatch_gap_us) * 1e-6)
        if direction == "fwd":
            pairs = [(0, 1), (1, 2), (2, 3)]
            tag = "pp_dp_pp_fwd"
        else:
            pairs = [(3, 2), (2, 1), (1, 0)]
            tag = "pp_dp_pp_bwd"

        # Each hop in the pipeline is a burst at slightly increasing time.
        for hop_idx, (s_stage, d_stage) in enumerate(pairs):
            t = base_t + hop_idx * (float(microbatch_gap_us) * 1e-6)
            for i in range(per_stage):
                src = stage_nodes[s_stage][i]
                dst = stage_nodes[d_stage][i]
                flow_id = ids.next_int()
                flows.append(
                    Flow(
                        flow_id=flow_id,
                        job_id=job_id,
                        step_id=step_id,
                        phase_id=phase_id,
                        bucket_id=0,
                        tag=f"{tag}/mb{mb}/hop{hop_idx}",
                        src_node_id=src,
                        dst_node_id=dst,
                        size_bytes=int(bytes_per_send),
                        start_time=float(t),
                        metadata={"block": tag, "microbatch": mb, "hop": hop_idx},
                    )
                )

    return flows


def _retag(flows: list[Flow], *, job_id: int, tag_prefix: str) -> list[Flow]:
    # Keep ids and timing, but unify tags and metadata for later filtering.
    out: list[Flow] = []
    for f in flows:
        out.append(
            Flow(
                flow_id=int(f.flow_id),
                job_id=int(job_id),
                step_id=int(f.step_id),
                phase_id=int(f.phase_id),
                bucket_id=f.bucket_id,
                tag=f"{tag_prefix}:{f.tag}",
                src_node_id=f.src_node_id,
                dst_node_id=f.dst_node_id,
                size_bytes=int(f.size_bytes),
                start_time=float(f.start_time),
                priority=f.priority,
                deadline=f.deadline,
                metadata={**dict(f.metadata), "block": tag_prefix},
            )
        )
    return out
