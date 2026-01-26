from __future__ import annotations


def default_rack_key(host_id: str) -> int:
    """Best-effort rack key extraction.

    For AI-factory SU host IDs that look like: su1_leaf<leaf_i>_srv<srv_i>,
    we treat leaf_i as rack id.

    Falls back to digit grouping when the expected pattern isn't found.
    """

    import re

    m = re.search(r"leaf(\d+)", host_id)
    if m:
        return int(m.group(1))

    digits = "".join(ch for ch in host_id if ch.isdigit())
    if digits:
        n = int(digits)
        return (n - 1) // 4

    return 0


__all__ = ["default_rack_key"]
