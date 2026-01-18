from __future__ import annotations

from typing import Callable

from network_simulation.packet import Protocol
from network_simulation.scenario import Scenario

from ai_factory_simulation.core.runner import FlowInjector, JobRunner
from ai_factory_simulation.traffic.flow import Flow
from ai_factory_simulation.workloads.workload1_dp_heavy import Workload1Config, build_workload1_dp_heavy_job


class NetworkFlowInjector(FlowInjector):
    """Adapter: Flow -> Host.send_message + completion callback.

    Keeps the AI-factory layer packet-agnostic.
    """

    def __init__(self, network):
        self._network = network
        self._callbacks: dict[int, Callable[[int], None]] = {}
        # flow_id -> (dst_ip, expected_bytes, received_bytes)
        self._stats: dict[int, tuple[str, int, int]] = {}

        # Wrap hosts' on_message to detect per-flow completion.
        for host in self._network.hosts.values():
            original = host.on_message

            def wrapped(packet, *, _orig=original):
                _orig(packet)
                flow_id = int(packet.transport_header.flow_id)
                stat = self._stats.get(flow_id)
                if stat is None:
                    return

                dst_ip, expected, received = stat
                # Count bytes only at the final destination host.
                if packet.routing_header.five_tuple.dst_ip != dst_ip:
                    return

                received += int(packet.routing_header.size_bytes)
                if received >= expected:
                    cb = self._callbacks.pop(flow_id, None)
                    self._stats.pop(flow_id, None)
                    if cb is not None:
                        cb(flow_id)
                else:
                    self._stats[flow_id] = (dst_ip, expected, received)

            host.on_message = wrapped  # type: ignore[assignment]

    def inject(self, flow: Flow, *, on_complete: Callable[[int], None]):
        src = self._network.get_entity(flow.src_node_id)
        dst = self._network.get_entity(flow.dst_node_id)
        flow_id = int(flow.flow_id)
        self._callbacks[flow_id] = on_complete
        self._stats[flow_id] = (dst.ip_address, int(flow.size_bytes), 0)
        src.send_message(
            session_id=flow_id,
            dst_ip_address=dst.ip_address,
            source_port=1000,
            dest_port=2000,
            size_bytes=int(flow.size_bytes),
            protocol=Protocol.TCP,
        )


class AIFactorySUDpHeavyScenario(Scenario):
    """Workload1 DP-heavy on the AI-Factory SU topology."""
    def __init__(self, steps: int, seed: int, num_buckets: int, bucket_bytes_per_participant: int, gap_us: float):
        self.steps = steps
        self.seed = seed
        self.num_buckets = num_buckets
        self.bucket_bytes_per_participant = bucket_bytes_per_participant
        self.gap_us = gap_us

    def install(self, network) -> None:
        participants = sorted(network.hosts.keys())
        cfg = Workload1Config(
            steps=int(self.steps),
            num_buckets=int(self.num_buckets),
            bucket_bytes_per_participant=int(self.bucket_bytes_per_participant),
            gap_us=float(self.gap_us),
            seed=int(self.seed),
        )
        job = build_workload1_dp_heavy_job(participants=participants, config=cfg)

        injector = NetworkFlowInjector(network)
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
            }
        )
        return out

