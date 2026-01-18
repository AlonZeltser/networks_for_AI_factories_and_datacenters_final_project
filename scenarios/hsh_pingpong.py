from __future__ import annotations

from dataclasses import dataclass

from network_simulation.host import Host
from network_simulation.packet import Protocol
from network_simulation.scenario import Scenario


@dataclass(frozen=True)
class HSHPingPongScenario(Scenario):
    """Ping-pong traffic between Host1 and Host2 over the HSH topology."""

    name: str = "hsh-pingpong"

    def install(self, creator) -> None:
        def e1():
            h1: Host = creator.get_entity('Host1')
            h1.send_message(
                app_id=1,
                session_id=1,
                dst_ip_address='10.1.1.2',
                source_port=100,
                dest_port=200,
                size_bytes=25000,
                protocol=Protocol.TCP,
                message='Hello, Host2!'
            )

        def e2():
            h2: Host = creator.get_entity('Host2')
            h2.send_message(
                app_id=1,
                session_id=1,
                dst_ip_address='10.1.1.1',
                source_port=200,
                dest_port=100,
                size_bytes=4000,
                protocol=Protocol.TCP,
                message='bye bye, Host1!'
            )


        creator.simulator.schedule_event(0, e1)
        #network.simulator.schedule_event(0, e2)

    def parameters_summary(self):
        out = super().parameters_summary()
        return out
