from network_simulation.host import Host
from network_simulation.packet import Protocol
from network_simulation.simulator_creator import SimulatorCreator


class HSHCreator(SimulatorCreator):
    def __init__(self, visualize:bool, max_path:int, link_failure_percent:float=0.0, verbose:bool=False):
        super().__init__("hsh", max_path, visualize, link_failure_percent=link_failure_percent, verbose=verbose)
        self._identifier = {"link failure percent": link_failure_percent}

    def create_topology(self):
        h1 = self.create_host('Host1', "10.1.1.1")
        h2 = self.create_host('Host2', "10.1.1.2")
        s1 = self.create_switch('Switch1', 2)

        l1 = self.create_link("h1_s1", 1e3, 0.01)
        l2 = self.create_link('h2_s1', 1e5, 0.01)

        # physical connection of h1 <-> l1 <-> s1 <-> l2 <-> h2
        h1.connect(1, l1)
        h2.connect(1, l2)
        s1.connect(1, l1)
        s1.connect(2, l2)

        h1.set_ip_routing("10.0.0.0/8", 1)
        h2.set_ip_routing("10.0.0.0/8", 1)
        s1.set_ip_routing("10.1.1.1/32", 1)
        s1.set_ip_routing("10.1.1.2/32", 2)

    def create_scenario(self):
        def e1():
            h1: Host = self.get_entity('Host1')
            h1.send_message(app_id=1,
                            session_id=1,
                            dst_ip_address='10.1.1.2',
                            source_port=100,
                            dest_port=200,
                            size_bytes=50000,
                            protocol=Protocol.TCP,
                            message='Hello, Host2!'
                            )
            #h1.send_to_ip('10.1.1.2', 'Hellow again, Host2!', size_bytes=500000)

        def e2():
            h2: Host  = self.get_entity('Host2')
            h2.send_message(app_id=1,
                            session_id=1,
                            dst_ip_address='10.1.1.1',
                            source_port=200,
                            dest_port=100,
                            size_bytes=50000,
                            protocol=Protocol.TCP,
                            message='bye bye, Host1!'
                            )


        for i in range(0, 10):
            self.simulator.schedule_event(i / 10.0, e1)
            self.simulator.schedule_event(i, e2)
        for i in range(0, 10):
            self.simulator.schedule_event(i / 10.0, e1)
            self.simulator.schedule_event(i, e2)
            """
        for i in range(1):
            self.simulator.schedule_event(0, e1)
            self.simulator.schedule_event(0, e2)
        #for i in range(0, 10):
        #    self.simulator.schedule_event(0, e1)
        #    self.simulator.schedule_event(0, e2)
        """
