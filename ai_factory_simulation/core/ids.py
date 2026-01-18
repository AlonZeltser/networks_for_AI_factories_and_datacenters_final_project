from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class IdGenerator:
    """Deterministic ID generator.

    We use randomness (seeded) to create stable-but-nontrivial IDs so that:
      * tests can assert determinism
      * different jobs in the same simulation don't collide
    """

    seed: int = 0

    def __post_init__(self) -> None:
        self._rnd = random.Random(self.seed)

    def next_int(self, *, bits: int = 31) -> int:
        # 31 bits fits comfortably in signed int ranges and is plenty for IDs.
        return self._rnd.getrandbits(bits)

    def child(self, salt: int | str) -> "IdGenerator":
        # Derive a new generator deterministically.
        return IdGenerator(seed=(hash((self.seed, salt)) & 0x7FFFFFFF))

