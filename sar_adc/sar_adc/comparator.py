"""Voltage comparator model with static offset and Gaussian noise."""

from __future__ import annotations

import numpy as np


class Comparator:
    """
    Single-ended voltage comparator.

    Decision: (vin - vdac + offset + N(0, noise_sigma)) > 0
    Returns True when vin > vdac (DAC voltage is too low → keep bit = 1).
    """

    def __init__(
        self,
        offset: float = 0.0,
        noise_sigma: float = 0.0,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.offset = offset
        self.noise_sigma = noise_sigma
        self._rng = rng if rng is not None else np.random.default_rng()

    def compare(self, vin: float, vdac: float) -> bool:
        noise = self._rng.standard_normal() * self.noise_sigma if self.noise_sigma else 0.0
        return (vin - vdac + self.offset + noise) > 0.0
