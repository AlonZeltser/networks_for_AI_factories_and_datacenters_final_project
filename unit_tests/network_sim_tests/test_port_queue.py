import unittest

from des.des import DiscreteEventSimulator
from network_simulation.host import Host
from network_simulation.link import Link
from network_simulation.packet import Protocol


class TestPortQueue(unittest.TestCase):

    def test_port_queue_drains_using_link_availability(self):
        sim = DiscreteEventSimulator()

        h1 = Host("h1", sim, "10.0.0.1", max_path=10)
        h2 = Host("h2", sim, "10.0.0.2", max_path=10)

        # 1 Mbps, 0 propagation delay.
        link = Link("l1", sim, bandwidth_bps=1e6, propagation_time=0.0)
        h1.connect(1, link)
        h2.connect(1, link)

        # route between hosts
        h1.set_ip_routing("10.0.0.2/32", 1)
        h2.set_ip_routing("10.0.0.1/32", 1)

        # Create 2 packets at time 0. They should serialize on the link.
        # unit_tests/network_sim_tests/test_port_queue.py

        # Create 2 packets at time 0. They should serialize on the link.
        h1.send_message(
            app_id=1,
            session_id=1,
            dst_ip_address="10.0.0.2",
            source_port=12345,
            dest_port=80,
            size_bytes=1000,  # 0.008s serialization
            protocol=Protocol.UDP,
            message="a",
        )
        h1.send_message(
            app_id=1,
            session_id=1,
            dst_ip_address="10.0.0.2",
            source_port=12345,
            dest_port=80,
            size_bytes=1000,
            protocol=Protocol.UDP,
            message="b",
        )


        # Immediately after enqueuing, we should have a backlog (at least 1 waiting).
        self.assertGreaterEqual(h1.port_queue_size(1), 1)

        sim.run()

        self.assertEqual(h2.received_count, 2)
        self.assertTrue(all(m.delivered for m in sim.messages))
        self.assertAlmostEqual(sim.end_time, 0.016, places=6)


if __name__ == "__main__":
    unittest.main()

