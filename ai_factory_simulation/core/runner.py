from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from des.des import DiscreteEventSimulator

from ai_factory_simulation.core.entities import (
    Job,
    JobMetrics,
    StepMetrics,
    PhaseMetrics,
    ComputePhase,
    CommPhase,
    Bucket,
)
from ai_factory_simulation.core.schedule import BarrierBookkeeper, Join, schedule_timer
from ai_factory_simulation.traffic.flow import Flow


class FlowInjector:
    """Adapter interface: Flow -> network injection.

    Implementations must call `on_complete(flow_id)` once the flow is fully delivered.
    """

    def inject(self, flow: Flow, *, on_complete: Callable[[int], None]) -> None:
        raise NotImplementedError


def _sim_time_prefix(sim: DiscreteEventSimulator) -> str:
    """Format simulator time prefix for aligned logging."""
    return f"[sim_t={sim.get_current_time():012.6f}s]"


@dataclass
class JobRunner:
    """Event-driven state machine that advances Job -> Step -> Phase.

    - Compute phases schedule DES timers.
    - Comm phases inject flows and wait for completion events.
    """

    sim: DiscreteEventSimulator
    injector: FlowInjector
    job: Job

    metrics: JobMetrics | None = None

    def run(self) -> JobMetrics:
        self.metrics = JobMetrics(job_id=self.job.job_id, start_time=self.sim.get_current_time())
        self.sim.schedule_event(0.0, self._start_job)
        return self.metrics

    def _start_job(self) -> None:
        assert self.metrics is not None
        logging.info(
            f"{_sim_time_prefix(self.sim)} Job starting       job={self.job.name} id={self.job.job_id} participants={len(self.job.participants)} steps={len(self.job.steps)}"
        )
        self._run_step(step_index=0)

    def _run_step(self, *, step_index: int) -> None:
        assert self.metrics is not None
        if step_index >= len(self.job.steps):
            self.metrics.end_time = self.sim.get_current_time()
            logging.info(f"{_sim_time_prefix(self.sim)} Job finished       job_id={self.job.job_id}")
            return

        logging.debug(f"{_sim_time_prefix(self.sim)} Step starting      step={step_index}")
        step = self.job.steps[step_index]
        step_metrics = StepMetrics(step_id=step.step_id, start_time=self.sim.get_current_time(), end_time=-1.0)
        self.metrics.steps.append(step_metrics)
        self._run_phase(step_index=step_index, phase_index=0)

    def _run_phase(self, *, step_index: int, phase_index: int) -> None:
        assert self.metrics is not None
        step = self.job.steps[step_index]
        step_metrics = self.metrics.steps[-1]

        if phase_index >= len(step.phases):
            step_metrics.end_time = self.sim.get_current_time()
            logging.debug(f"{_sim_time_prefix(self.sim)} Step finished      step={step_index}")
            self._run_step(step_index=step_index + 1)
            return

        phase = step.phases[phase_index]
        logging.debug(f"{_sim_time_prefix(self.sim)} Phase starting     step={step_index} phase={phase_index} name={phase.name}")
        phase_metrics = PhaseMetrics(
            phase_id=phase.phase_id,
            name=phase.name,
            start_time=self.sim.get_current_time(),
            end_time=-1.0,
        )
        step_metrics.phases.append(phase_metrics)

        def done_phase() -> None:
            phase_metrics.end_time = self.sim.get_current_time()
            logging.debug(f"{_sim_time_prefix(self.sim)} Phase finished     step={step_index} phase={phase_index} name={phase.name}")
            self._run_phase(step_index=step_index, phase_index=phase_index + 1)

        if isinstance(phase, ComputePhase):
            schedule_timer(self.sim, delay_s=phase.duration_s, cb=done_phase)
            return

        if isinstance(phase, CommPhase):
            self._run_comm_phase(phase, done_phase)
            return

        raise TypeError(f"Unknown phase type: {type(phase)}")

    def _run_comm_phase(self, phase: CommPhase, done_phase: Callable[[], None]) -> None:
        book = BarrierBookkeeper()

        def run_bucket(bucket_index: int) -> None:
            if bucket_index >= len(phase.buckets):
                done_phase()
                return

            logging.debug(f"{_sim_time_prefix(self.sim)} Bucket starting    phase={phase.name} bucket={bucket_index}")
            bucket: Bucket = phase.buckets[bucket_index]
            if not bucket.flows:
                logging.debug(f"{_sim_time_prefix(self.sim)} Bucket finished    phase={phase.name} bucket={bucket_index} (empty)")
                run_bucket(bucket_index + 1)
                return

            join_name = f"phase{phase.phase_id}/bucket{bucket.bucket_id}"

            def done_bucket() -> None:
                logging.debug(f"{_sim_time_prefix(self.sim)} Bucket finished    phase={phase.name} bucket={bucket_index}")
                run_bucket(bucket_index + 1)

            join = Join(pending={f.flow_id for f in bucket.flows}, on_done=done_bucket)
            book.add_join(join_name, join)

            now = self.sim.get_current_time()
            for f in bucket.flows:
                delay = max(0.0, float(f.start_time) - float(now))

                def _inject(ff: Flow = f) -> None:
                    self.injector.inject(ff, on_complete=book.on_flow_complete)

                self.sim.schedule_event(delay, _inject)

        run_bucket(0)

