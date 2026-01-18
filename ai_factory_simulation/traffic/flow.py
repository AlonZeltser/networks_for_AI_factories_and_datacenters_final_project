from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Flow:
    """A bulk transfer request emitted by the AI-factory layer.

    Packet-agnostic: the network simulator decides packetization, routing, congestion, etc.
    """

    flow_id: int
    job_id: int
    step_id: int
    phase_id: int
    bucket_id: int | None
    tag: str

    src_node_id: str
    dst_node_id: str
    size_bytes: int
    start_time: float

    priority: int | None = None
    deadline: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def signature_tuple(self) -> tuple:
        return (self.src_node_id, self.dst_node_id, int(self.size_bytes), float(self.start_time), self.tag)

