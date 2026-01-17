from __future__ import annotations

from network_simulation.scenario import Scenario


class NoneScenario(Scenario):
    """No traffic; topology-only run."""

    name = "none"

    def install(self, creator) -> None:
        return

