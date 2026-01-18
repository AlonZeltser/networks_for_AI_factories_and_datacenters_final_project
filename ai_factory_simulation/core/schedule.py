from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Set

from des.des import DiscreteEventSimulator


@dataclass
class Join:
    """A barrier on a set of flow_ids."""

    pending: Set[int]
    on_done: Callable[[], None]

    def mark_complete(self, flow_id: int) -> None:
        self.pending.discard(flow_id)
        if not self.pending:
            self.on_done()


@dataclass
class BarrierBookkeeper:
    """Tracks joins/barriers for a running job."""

    joins: Dict[str, Join] = field(default_factory=dict)

    def add_join(self, name: str, join: Join) -> None:
        if name in self.joins:
            raise ValueError(f"Join name already exists: {name}")
        self.joins[name] = join

    def on_flow_complete(self, flow_id: int) -> None:
        # Iterate over a copy, since callbacks might mutate joins.
        for name, join in list(self.joins.items()):
            if flow_id in join.pending:
                join.mark_complete(flow_id)
                if not join.pending:
                    self.joins.pop(name, None)


def schedule_timer(sim: DiscreteEventSimulator, *, delay_s: float, cb: Callable[[], None]) -> None:
    sim.schedule_event(delay_s, cb)

