"""Traffic scenarios.

Each scenario is responsible only for scheduling traffic/events on top of an already-built topology.
See `network_simulation.scenario.Scenario`.
"""
from network_simulation.scenario import Scenario
from .none_scenario import NoneScenario
from .hsh_pingpong import HSHPingPongScenario
from .simple_star_all_to_all import SimpleStarAllToAllScenario

__all__ = [
    "Scenario",
    "NoneScenario",
    "HSHPingPongScenario",
    "SimpleStarAllToAllScenario",
]

