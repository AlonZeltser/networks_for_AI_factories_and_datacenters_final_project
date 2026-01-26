from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from ai_factory_simulation.core.runner import _compute_percentile
from ai_factory_simulation.scenarios.rack_utils import default_rack_key
from ai_factory_simulation.traffic.flow import Flow


@dataclass(frozen=True)
class MiceConfig:
    enabled: bool
    seed: int
    start_delay_s: float
    end_time_s: float
    interarrival_s: float
    min_packets: int
    max_packets: int
    mtu_bytes: int
    force_cross_rack: bool


class MiceFlowInjector:
    """Inject small background 'mice' flows and track their flow completion time (FCT)."""

    def __init__(self, *, network, injector, cfg: MiceConfig):
        self._network = network
        self._injector = injector
        self._cfg = cfg

        self._rnd = random.Random(int(cfg.seed))
        self._hosts: list[str] = sorted(network.hosts.keys())
        self._flow_id_next = 1_000_000_000

        self._fcts_s: list[float] = []

    def install(self) -> None:
        if not self._cfg.enabled:
            return
        if self._cfg.interarrival_s <= 0.0:
            raise ValueError("mice.interarrival_s must be > 0")
        if self._cfg.end_time_s <= self._cfg.start_delay_s:
            raise ValueError("mice.end_time_s must be > mice.start_delay_s")
        if len(self._hosts) < 2:
            raise ValueError("mice requires at least 2 hosts")

        self._network.entities["mice_flow_metrics"] = {
            "count": 0,
            "fcts_s": self._fcts_s,
        }

        self._network.simulator.schedule_event(float(self._cfg.start_delay_s), self._inject_next)

        # Ensure we always publish summary at the end of the sim even if end_time_s is infinity.
        if self._cfg.end_time_s == float("inf"):
            self._network.simulator.schedule_event(float("inf"), self._finalize)

    def _pick_pair(self) -> tuple[str, str]:
        src = self._rnd.choice(self._hosts)

        if not self._cfg.force_cross_rack:
            # Any destination != src
            while True:
                dst = self._rnd.choice(self._hosts)
                if dst != src:
                    return src, dst

        # Force cross-rack: keep sampling until rack differs.
        src_rack = default_rack_key(src)
        for _ in range(128):
            dst = self._rnd.choice(self._hosts)
            if dst != src and default_rack_key(dst) != src_rack:
                return src, dst

        # Fallback if rack parsing isn't meaningful.
        while True:
            dst = self._rnd.choice(self._hosts)
            if dst != src:
                return src, dst

    def _inject_next(self) -> None:
        sim = self._network.simulator
        now = float(sim.get_current_time())

        if now >= float(self._cfg.end_time_s):
            self._finalize()
            return

        src, dst = self._pick_pair()

        n_packets = self._rnd.randint(int(self._cfg.min_packets), int(self._cfg.max_packets))
        size_bytes = int(n_packets) * int(self._cfg.mtu_bytes)

        flow_id = self._flow_id_next
        self._flow_id_next += 1

        t0 = now

        def _done(_: int) -> None:
            t1 = float(sim.get_current_time())
            self._fcts_s.append(t1 - t0)

        f = Flow(
            flow_id=flow_id,
            job_id=-1,
            step_id=-1,
            phase_id=-1,
            bucket_id=None,
            tag="mice",
            src_node_id=src,
            dst_node_id=dst,
            size_bytes=size_bytes,
            start_time=now,
        )

        self._injector.inject(f, on_complete=_done)

        # Update shared, live metrics.
        m = self._network.entities.get("mice_flow_metrics")
        if isinstance(m, dict):
            m["count"] = int(m.get("count", 0)) + 1

        sim.schedule_event(float(self._cfg.interarrival_s), self._inject_next)

    def _finalize(self) -> None:
        # Compute and publish summary.
        n = len(self._fcts_s)
        if n == 0:
            summary = {"mice_fct_avg_ms": 0.0, "mice_fct_p95_ms": 0.0, "mice_fct_p99_ms": 0.0, "mice_flows": 0}
        else:
            avg = sum(self._fcts_s) / n
            s = sorted(self._fcts_s)
            p95 = _compute_percentile(s, 95.0)
            p99 = _compute_percentile(s, 99.0)
            summary = {
                "mice_flows": n,
                "mice_fct_avg_ms": avg * 1000.0,
                "mice_fct_p95_ms": p95 * 1000.0,
                "mice_fct_p99_ms": p99 * 1000.0,
            }

        self._network.entities["mice_flow_summary"] = summary
        logging.info(
            "Mice flows summary: flows=%s avg=%.3fms p95=%.3fms p99=%.3fms",
            summary.get("mice_flows", 0),
            summary.get("mice_fct_avg_ms", 0.0),
            summary.get("mice_fct_p95_ms", 0.0),
            summary.get("mice_fct_p99_ms", 0.0),
        )


__all__ = ["MiceConfig", "MiceFlowInjector"]
