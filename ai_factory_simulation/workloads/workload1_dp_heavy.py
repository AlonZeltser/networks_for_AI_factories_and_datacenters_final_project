from __future__ import annotations

from dataclasses import dataclass
import secrets

from ai_factory_simulation.core.entities import Bucket, CommPhase, ComputePhase, Job, JobStep
from ai_factory_simulation.core.ids import IdGenerator
from ai_factory_simulation.traffic.collective import CollectiveAlgorithm, CollectiveKind, expand_collective


@dataclass(frozen=True)
class Workload1Config:
    steps: int
    t_fwd_bwd_ms: float
    num_buckets: int
    bucket_bytes_per_participant: int
    algorithm: CollectiveAlgorithm
    gap_us: float
    optimizer_ms: float
    seed: int


def build_workload1_dp_heavy_job(
    *,
    participants: list[str],
    config: Workload1Config,
    job_name: str = "workload1-dp-heavy",
) -> Job:
    """Build Workload 1 (DP-heavy) as a Job hierarchy."""

    ids = IdGenerator(seed=config.seed)

    # Make job_id unique per process run even if the workload seed is fixed.
    # Keep it deterministic-ish but collision-resistant.
    job_id = (ids.next_int() ^ secrets.randbits(31)) & 0x7FFFFFFF

    steps: list[JobStep] = []
    for step_idx in range(int(config.steps)):
        phases: list = []

        phases.append(
            ComputePhase(
                phase_id=0,
                name="fwd_bwd_compute",
                duration_s=float(config.t_fwd_bwd_ms) / 1000.0,
            )
        )

        comm_buckets: list[Bucket] = []
        for b in range(int(config.num_buckets)):
            bucket_id = b
            start_time = 0.0

            rs = expand_collective(
                kind=CollectiveKind.REDUCE_SCATTER,
                algorithm=config.algorithm,
                participants=participants,
                bytes_per_participant=int(config.bucket_bytes_per_participant),
                start_time=start_time,
                gap_us=float(config.gap_us),
                ids=ids.child((step_idx, 1, bucket_id, "rs")),
                job_id=job_id,
                step_id=step_idx,
                phase_id=1,
                bucket_id=bucket_id,
            )
            ag = expand_collective(
                kind=CollectiveKind.ALL_GATHER,
                algorithm=config.algorithm,
                participants=participants,
                bytes_per_participant=int(config.bucket_bytes_per_participant),
                start_time=start_time,
                gap_us=float(config.gap_us),
                ids=ids.child((step_idx, 1, bucket_id, "ag")),
                job_id=job_id,
                step_id=step_idx,
                phase_id=1,
                bucket_id=bucket_id,
            )

            comm_buckets.append(Bucket(bucket_id=bucket_id, flows=rs.flows + ag.flows))

        phases.append(CommPhase(phase_id=1, name="gradient_sync", buckets=comm_buckets))

        phases.append(
            ComputePhase(
                phase_id=2,
                name="optimizer_compute",
                duration_s=float(config.optimizer_ms) / 1000.0,
            )
        )

        steps.append(JobStep(step_id=step_idx, phases=phases))

    return Job(job_id=job_id, name=job_name, steps=steps, participants=participants)

