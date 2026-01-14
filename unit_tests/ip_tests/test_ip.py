import pytest
from network_simulation.ip import IPAddress, IPPrefix


def test_parse_and_str_and_int():
    ip = IPAddress.parse('10.1.2.3')
    assert str(ip) == '10.1.2.3'
    assert ip.to_int() == (10 << 24) | (1 << 16) | (2 << 8) | 3


def test_from_int_and_conversion():
    i = (192 << 24) | (168 << 16) | (0 << 8) | 1
    ip = IPAddress.from_int(i)
    assert str(ip) == '192.168.0.1'
    assert ip.to_int() == i


def test_prefix_contains():
    p = IPPrefix.from_string('10.1.2.0/24')
    assert p.contains('10.1.2.5')
    assert not p.contains('10.1.3.5')


def test_prefix_zero_and_full():
    p0 = IPPrefix.from_string('0.0.0.0/0')
    assert p0.contains('1.2.3.4')
    p32 = IPPrefix.from_string('10.1.2.3/32')
    assert p32.contains('10.1.2.3')
    assert not p32.contains('10.1.2.4')

