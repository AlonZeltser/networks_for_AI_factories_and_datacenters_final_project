from dataclasses import dataclass


@dataclass
class NetworkEnvironment:
    mtu: int = 4096  # bytes, default is AI Factory common maximum transmission unit
    ttl: int = 64  # default hops for packets

ENV = NetworkEnvironment()