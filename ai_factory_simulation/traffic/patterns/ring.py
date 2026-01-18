from __future__ import annotations

from dataclasses import dataclass
from typing import List
import random

from ai_factory_simulation.core.ids import IdGenerator
from ai_factory_simulation.traffic.flow import Flow


@dataclass(frozen=True)
class RingPlan:
    """A deterministic ring order."""

    participants: List[str]

    def next_of(self, node_id: str) -> str:
        i = self.participants.index(node_id)
        return self.participants[(i + 1) % len(self.participants)]


def build_ring_order(participants: list[str], *, seed: int) -> RingPlan:
    """Return a deterministic ring order.

    If seed is the same, the order is stable.
    """
    out = list(participants)
    rnd = random.Random(seed)
    for i in range(len(out) - 1, 0, -1):
        j = rnd.randint(0, i)
        out[i], out[j] = out[j], out[i]
    return RingPlan(participants=out)


def _chunk_sizes(bytes_per_participant: int, p: int) -> list[int]:
    base = bytes_per_participant // p
    rem = bytes_per_participant % p
    # Deterministic remainder: first `rem` steps get +1 byte.
    return [base + (1 if i < rem else 0) for i in range(p)]


def expand_ring_neighbor_sends(
    *,
    op_tag: str,
    participants: list[str],
    bytes_per_participant: int,
    start_time: float,
    gap_us: float,
    ids: IdGenerator,
    job_id: int,
    step_id: int,
    phase_id: int,
    bucket_id: int | None,
) -> list[Flow]:
    """Minimum viable ring model.

    Rule:
      - P participants, steps = P-1
      - Chunk size per step per sender = bytes_per_participant / P (deterministic remainder)
      - At each step s, each node i sends one chunk to next(i) in ring order
      - Emit all step flows at time start_time + s * gap_us

    Returns a list of Flow objects; completion is modeled as "all flows delivered".
    """

    p = len(participants)
    if p < 2:
        return []

    ring = build_ring_order(participants, seed=ids.seed)
    steps = p - 1
    chunk_per_step = _chunk_sizes(bytes_per_participant, p)

    flows: list[Flow] = []
    for s in range(steps):
        t = start_time + (s * (gap_us * 1e-6))
        for sender in ring.participants:
            receiver = ring.next_of(sender)
            size = chunk_per_step[s]
            flow_id = ids.next_int()
            flows.append(
                Flow(
                    flow_id=flow_id,
                    job_id=job_id,
                    step_id=step_id,
                    phase_id=phase_id,
                    bucket_id=bucket_id,
                    tag=f"{op_tag}/ring_step_{s}",
                    src_node_id=sender,
                    dst_node_id=receiver,
                    size_bytes=size,
                    start_time=t,
                    metadata={"ring_step": s, "participants": p},
                )
            )

    return flows

