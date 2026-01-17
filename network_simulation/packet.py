from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import xxhash


class Protocol(Enum):
    TCP = 1
    UDP = 2
    CONTROL = 3


@dataclass
class FiveTuple:
    src_ip: str
    dst_ip: str
    src_protocol_port: int
    dst_protocol_port: int
    protocol: Protocol

    def __str__(self) -> str:
        return (f"{self.src_ip}:{self.src_protocol_port} -> "
                f"{self.dst_ip}:{self.dst_protocol_port} ({self.protocol.name})")

    def __hash__(self) -> int:
        return xxhash.xxh64(str(self)).intdigest()


@dataclass
class PacketHeader:
    """packet header containing L3, L4 information."""
    five_tuple: FiveTuple
    seq_number: int
    size_bytes: int
    ttl: int # number of hops the packet can traverse. At 0, the packet is expired.
    dropped: bool = field(default=False)

@dataclass(frozen=True)
class AppPacketHeader:
    """Application-level packet type identifier."""
    app_session_id: int
    app_session_packets_count: int

    def __str__(self) -> str:
        return (f"AppSessionID: {self.app_session_id}, "
                f"PacketsCount: {self.app_session_packets_count}")

@dataclass
class PacketTrackingInfo:
    """Debug information for a packet."""
    global_id: int
    sender: str
    birth_time: float
    route_length: int = 0
    verbose_route: list[str] | None = None  # only when verbose_route tracking is enabled
    delivered: bool = False
    arrival_time: Optional[float] = None


@dataclass
class Packet:
    header: PacketHeader
    app_info: AppPacketHeader
    tracking_info: PacketTrackingInfo
    content: Any

    def is_expired(self) -> bool:
        return self.header.ttl <= 0

    @property
    def delivered(self) -> bool:
        return self.tracking_info.delivered

    @delivered.setter
    def delivered(self, value: bool) -> None:
        self.tracking_info.delivered = value

    @property
    def dropped(self) -> bool:
        # Historically this lived on Packet directly; the canonical flag is header.dropped.
        return self.header.dropped

    @dropped.setter
    def dropped(self, value: bool) -> None:
        self.header.dropped = value

    @property
    def arrival_time(self) -> Optional[float]:
        return self.tracking_info.arrival_time

    @arrival_time.setter
    def arrival_time(self, value: Optional[float]) -> None:
        self.tracking_info.arrival_time = value
