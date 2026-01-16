from scenarios.circle_creator import CircleCreator


def test_circle_topology_and_one_send_each():
    creator = CircleCreator(visualize=False, max_path=32, link_failure_percent=0.0, verbose=False)
    sim = creator.create_simulator()

    # topology sanity
    assert len(creator.hosts) == 5
    assert len(creator.switches) == 5
    assert len(creator.links) == 10

    # run: should deliver exactly 5 packets (one per host) in this scenario
    sim.run()

    received_total = sum(h.received_count for h in creator.hosts.values())
    assert received_total == 5
