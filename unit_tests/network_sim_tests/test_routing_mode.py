import unittest

from des.des import DiscreteEventSimulator
from network_simulation.link import Link
from network_simulation.packet import FiveTupleExt, Packet, PacketL3, PacketTrackingInfo, PacketTransport, Protocol
from network_simulation.switch import Switch
from network_simulation.network_node import RoutingMode


class TestRoutingMode(unittest.TestCase):

    def _make_packet(self, *, src_ip: str, dst_ip: str) -> Packet:
        ft = FiveTupleExt(src_ip, dst_ip, 1111, 2222, Protocol.UDP, 1111)
        header = PacketL3(five_tuple=ft, seq_number=0, size_bytes=100, ttl=16)
        tracking = PacketTrackingInfo(global_id=1, birth_time=0.0)
        transport = PacketTransport(flow_id=1, flow_count=1, flow_seq=0)
        return Packet(routing_header=header, transport_header=transport, tracking_info=tracking)

    def test_routing_mode_is_set_on_switch(self):
        sim = DiscreteEventSimulator()
        sw = Switch(
            "s1",
            ports_count=2,
            scheduler=sim,
            routing_mode=RoutingMode.ADAPTIVE,
            message_verbose=False,
            verbose_route=False,
        )
        self.assertEqual(sw.routing_mode, RoutingMode.ADAPTIVE)

    def test_adaptive_avoids_busy_port_when_equal_cost(self):
        sim = DiscreteEventSimulator()

        # Two uplinks (port 1 and port 2). We'll make port 1 look busy by enqueuing a packet.
        sw = Switch(
            "s1",
            ports_count=2,
            scheduler=sim,
            routing_mode=RoutingMode.ADAPTIVE,
            message_verbose=False,
            verbose_route=False,
        )

        # Connect both ports so set_ip_routing doesn't skip them.
        l1 = Link("l1", sim, bandwidth_bps=1e6, propagation_time=0.0)
        l2 = Link("l2", sim, bandwidth_bps=1e6, propagation_time=0.0)
        sw.connect(1, l1)
        sw.connect(2, l2)

        # Two equal-cost routes for the same destination prefix.
        sw.set_ip_routing("10.0.0.0/24", 1)
        sw.set_ip_routing("10.0.0.0/24", 2)

        # Pre-fill port 1 queue to make it busier.
        sw.ports[0].enqueue(self._make_packet(src_ip="1.1.1.1", dst_ip="2.2.2.2"))

        pkt = self._make_packet(src_ip="10.0.0.1", dst_ip="10.0.0.5")
        chosen = sw.select_port_for_packet(pkt)

        # Adaptive should choose port index 1 (port_id=2) because it has the smallest queue.
        self.assertEqual(chosen, 1)


if __name__ == "__main__":
    unittest.main()
