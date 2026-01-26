from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import xxhash

from network_simulation.ip import IPAddress


class Protocol(Enum):
    TCP = 1
    UDP = 2
    CONTROL = 3


@dataclass(slots=True)
class FiveTupleExt:
    src_ip: str
    dst_ip: str
    src_protocol_port: int
    dst_protocol_port: int
    protocol: Protocol
    flowlet_field: int

    # Cached int forms (computed once when the FiveTupleExt is created).
    src_ip_int: int = field(init=False, repr=False)
    dst_ip_int: int = field(init=False, repr=False)
    _hash: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, 'src_ip_int', IPAddress.parse(self.src_ip).to_int())
        object.__setattr__(self, 'dst_ip_int', IPAddress.parse(self.dst_ip).to_int())
        # Cache hash once; __hash__ should be stable and fast.
        object.__setattr__(self, '_hash', xxhash.xxh64(str(self)).intdigest())

    def __str__(self) -> str:
        return (f"{self.src_ip}:{self.src_protocol_port} -> "
                f"{self.dst_ip}:{self.dst_protocol_port} ({self.protocol.name}), ({self.flowlet_field})")

    def __hash__(self) -> int:
        return self._hash


@dataclass
class PacketL3:
    """packet routing_header containing L3, L4 information."""
    five_tuple: FiveTupleExt
    seq_number: int
    size_bytes: int
    ttl: int # number of hops the packet can traverse. At 0, the packet is expired.
    dropped: bool = field(default=False)

@dataclass(frozen=True)
class PacketTransport:
    flow_id: int
    flow_count: int
    flow_seq: int

    def __str__(self) -> str:
        return (f"AppSessionID: {self.flow_id}, "
                f"PacketsCount: {self.flow_count}")

@dataclass
class PacketTrackingInfo:
    """Debug information for a packet."""
    global_id: int
    birth_time: float
    route_length: int = 0
    verbose_route: list[str] | None = None  # only when verbose_route tracking is enabled
    delivered: bool = False
    arrival_time: Optional[float] = None


@dataclass(slots=True)
class Packet:
    routing_header: PacketL3
    transport_header: PacketTransport
    tracking_info: PacketTrackingInfo

    def is_expired(self) -> bool:
        return self.routing_header.ttl <= 0

    @property
    def delivered(self) -> bool:
        return self.tracking_info.delivered

    @delivered.setter
    def delivered(self, value: bool) -> None:
        self.tracking_info.delivered = value

    @property
    def dropped(self) -> bool:
        # Historically this lived on Packet directly; the canonical flag is routing_header.dropped.
        return self.routing_header.dropped

    @dropped.setter
    def dropped(self, value: bool) -> None:
        self.routing_header.dropped = value

    @property
    def arrival_time(self) -> Optional[float]:
        return self.tracking_info.arrival_time

    @arrival_time.setter
    def arrival_time(self, value: Optional[float]) -> None:
        self.tracking_info.arrival_time = value
