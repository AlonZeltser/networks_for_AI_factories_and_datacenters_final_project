from dataclasses import dataclass
from typing import Tuple, Union


@dataclass(frozen=True)
class IPAddress:
    """Simple IPv4 address value object.

    Internally stores four octets (0-255). Provides parsing from string/int and
    helpers useful for fat-tree addressing (pod/edge/host extraction).
    """
    octets: Tuple[int, int, int, int]

    @classmethod
    def parse(cls, value: Union[str, int, Tuple[int, int, int, int]]):
        """Create an IPAddress from a dotted string, 32-bit integer or 4-tuple."""
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            return cls.from_int(value)
        if isinstance(value, (tuple, list)):
            if len(value) != 4:
                raise ValueError("Tuple must have four elements")
            octets = tuple(int(x) for x in value)
            cls._validate_octets(octets)
            return cls(octets)
        if isinstance(value, str):
            parts = value.strip().split('.')
            if len(parts) != 4:
                raise ValueError(f"Invalid IPv4 string: {value}")
            octets = tuple(int(p) for p in parts)
            cls._validate_octets(octets)
            return cls(octets)
        raise TypeError("Unsupported type for IPAddress.parse")

    @staticmethod
    def _validate_octets(octets: Tuple[int, int, int, int]) -> None:
        for o in octets:
            if not (0 <= o <= 255):
                raise ValueError(f"Invalid octet value: {o}")

    def __str__(self) -> str:
        return '.'.join(str(o) for o in self.octets)

    def to_int(self) -> int:
        a, b, c, d = self.octets
        return (a << 24) | (b << 16) | (c << 8) | d

    @classmethod
    def from_int(cls, value: int) -> 'IPAddress':
        if not (0 <= value <= 0xFFFFFFFF):
            raise ValueError("Integer value out of IPv4 range")
        a = (value >> 24) & 0xFF
        b = (value >> 16) & 0xFF
        c = (value >> 8) & 0xFF
        d = value & 0xFF
        return cls((a, b, c, d))


@dataclass(frozen=True)
class IPPrefix:
    """Represents an IPv4 prefix (network address + prefix length).

    Example: IPPrefix.from_string('10.1.2.0/24')
    """
    network: IPAddress
    prefix_len: int

    @classmethod
    def from_string(cls, s: str) -> 'IPPrefix':
        try:
            addr_part, prefix_part = s.split('/')
            prefix_len = int(prefix_part)
        except Exception:
            raise ValueError(f"Invalid prefix string: {s}")
        net_addr = IPAddress.parse(addr_part)
        if not (0 <= prefix_len <= 32):
            raise ValueError("prefix_len must be in [0,32]")
        # Mask network address to prefix length
        net_int = net_addr.to_int()
        mask = cls._mask_from_prefix(prefix_len)
        network_int = net_int & mask
        network_addr = IPAddress.from_int(network_int)
        return cls(network_addr, prefix_len)

    @staticmethod
    def _mask_from_prefix(prefix_len: int) -> int:
        if prefix_len == 0:
            return 0
        return (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF

    def contains(self, ip: Union[IPAddress, str]) -> bool:
        ip_addr = IPAddress.parse(ip)
        mask = self._mask_from_prefix(self.prefix_len)
        return (ip_addr.to_int() & mask) == (self.network.to_int() & mask)

    def __str__(self) -> str:
        return f"{self.network}/{self.prefix_len}"
