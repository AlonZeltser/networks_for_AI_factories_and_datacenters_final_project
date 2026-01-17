from __future__ import annotations

from dataclasses import dataclass

from network_simulation.scenario import Scenario


@dataclass(frozen=True)
class SimpleStarAllToAllScenario(Scenario):
    """All-to-all traffic among the 4 hosts in the simple-star topology."""

    name: str = "simple-star-all-to-all"
    repeats: int = 50
    message_size_bytes: int = 1000

    def install(self, creator) -> None:
        def burst():
            hosts_names = ['H1', 'H2', 'H3', 'H4']
            hosts = [creator.get_entity(s) for s in hosts_names]
            for source in hosts:
                for destination in hosts:
                    source.send_message(
                        app_id=1,
                        session_id=1,
                        dst_ip_address=destination.ip_address,
                        source_port=1000,
                        dest_port=2000,
                        size_bytes=int(self.message_size_bytes),
                        protocol=None,
                        message=f'Message from {source.name} to {destination.name}'
                    )

        for _ in range(int(self.repeats)):
            creator.simulator.schedule_event(1, burst)

    def parameters_summary(self):
        out = super().parameters_summary()
        out.update({"repeats": self.repeats, "message_size_bytes": self.message_size_bytes})
        return out

