from des.des import DiscreteEventSimulator


def test_run_without_until_executes_all_events_and_advances_time():
    sim = DiscreteEventSimulator()
    calls = []

    def make_action(name):
        return lambda: calls.append((name, sim.current_time))

    sim.schedule_event(1.0, make_action("a"))
    sim.schedule_event(2.5, make_action("b"))

    sim.run()

    # Both actions should have run in time order
    assert calls == [("a", 1.0), ("b", 2.5)]
    # Simulator current time should be the time of the last event
    assert sim.current_time == 2.5


