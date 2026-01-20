from __future__ import annotations

from ai_factory_simulation.scenarios.mixed_scenario import MixedScenario
from network_simulation.network_node import RoutingMode
from network_simulators.ai_factory_su_network_simulator import AIFactorySUNetworkSimulator


def _mk_network(*, routing_mode: RoutingMode) -> AIFactorySUNetworkSimulator:
    # Use the SU topology defaults (32 hosts). Keep it fast by using high bandwidths.
    return AIFactorySUNetworkSimulator(
        max_path=64,
        link_failure_percent=0.0,
        routing_mode=routing_mode,
        ecmp_flowlet_n_packets=512,
        verbose=False,
        verbose_route=False,
        server_to_leaf_bandwidth_bps=400e9,
        leaf_to_spine_bandwidth_bps=400e9,
        mtu=4096,
        ttl=64,
    )


def test_mixed_scenario_completes_and_metrics_lengths() -> None:
    network = _mk_network(routing_mode=RoutingMode.ECMP)
    scenario = MixedScenario(
        steps=5,
        seed=123,
        traffic_scale=0.01,
        allocation_mode="rack_balanced",
        stage_placement_mode="topology_aware",
        jobA_micro_collectives=2,
        jobB_microbatch_count=1,
        record_first_step_flow_signatures=True,
    )

    network.create(False)
    network.assign_scenario(scenario)
    network.run()

    metrics = network.entities.get("ai_factory_job_metrics")
    assert isinstance(metrics, dict)
    assert "jobA" in metrics and "jobB" in metrics

    jobA = metrics["jobA"]
    jobB = metrics["jobB"]

    assert len(jobA.steps) == 5
    assert len(jobB.steps) == 5


def test_mixed_scenario_deterministic_first_step_signature() -> None:
    network1 = _mk_network(routing_mode=RoutingMode.ECMP)
    network2 = _mk_network(routing_mode=RoutingMode.ECMP)

    scenario = MixedScenario(
        steps=2,
        seed=999,
        traffic_scale=0.01,
        allocation_mode="rack_balanced",
        stage_placement_mode="topology_unaware",
        jobA_micro_collectives=2,
        jobB_microbatch_count=1,
        record_first_step_flow_signatures=True,
    )

    network1.create(False)
    network1.assign_scenario(scenario)
    network1.run()

    network2.create(False)
    network2.assign_scenario(scenario)
    network2.run()

    sig1 = network1.entities.get("mixed_scenario_first_step_signature")
    sig2 = network2.entities.get("mixed_scenario_first_step_signature")

    assert sig1 == sig2
