from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ai_factory_simulation.core.ids import IdGenerator
from ai_factory_simulation.traffic.flow import Flow
from ai_factory_simulation.traffic.patterns.ring import expand_ring_neighbor_sends


class CollectiveKind(str, Enum):
    REDUCE_SCATTER = "reduce_scatter"
    ALL_GATHER = "all_gather"
    ALL_REDUCE = "all_reduce"


class CollectiveAlgorithm(str, Enum):
    RING = "ring"
    TREE = "tree"


@dataclass(frozen=True)
class CollectiveResult:
    flows: list[Flow]
    join_flow_ids: set[int]


def expand_collective(
    *,
    kind: CollectiveKind,
    algorithm: CollectiveAlgorithm,
    participants: list[str],
    bytes_per_participant: int,
    start_time: float,
    gap_us: float,
    ids: IdGenerator,
    job_id: int,
    step_id: int,
    phase_id: int,
    bucket_id: int | None,
) -> CollectiveResult:
    if algorithm != CollectiveAlgorithm.RING:
        raise NotImplementedError("Only ring algorithm is implemented for now")

    op_tag = f"{kind.value}"
    flows = expand_ring_neighbor_sends(
        op_tag=op_tag,
        participants=participants,
        bytes_per_participant=bytes_per_participant,
        start_time=start_time,
        gap_us=gap_us,
        ids=ids,
        job_id=job_id,
        step_id=step_id,
        phase_id=phase_id,
        bucket_id=bucket_id,
    )
    return CollectiveResult(flows=flows, join_flow_ids={f.flow_id for f in flows})

