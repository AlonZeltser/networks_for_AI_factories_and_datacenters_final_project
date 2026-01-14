"""Deprecated: `Node` has been merged into `NetworkNode`.

The project used to have both `Node` (actor/message handling) and `NetworkNode`
(networking). `NetworkNode` now includes the full `Node` contract, so keeping
this module as a small compatibility shim avoids breaking older imports.

New code should import `NetworkNode` from `network_simulation.network_node`.
"""

from network_simulation.network_node import NetworkNode as Node

__all__ = ["Node"]
