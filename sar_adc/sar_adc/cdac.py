"""Binary-weighted capacitor DAC model."""

from __future__ import annotations

import numpy as np


class CDAC:
    """
    Binary-weighted capacitor DAC with per-capacitor mismatch.

    Capacitor array: caps[i] = 2^i * C_unit * (1 + mismatch_sigma * N(0,1))
    where i=0 is the LSB capacitor and i=n_bits-1 is the MSB capacitor.

    Charge-redistribution output:
        Vdac = Vref * dot(caps_weighted_by_bits) / C_total
    """

    def __init__(
        self,
        n_bits: int = 12,
        vref: float = 1.0,
        mismatch_sigma: float = 0.001,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.n_bits = n_bits
        self.vref = vref

        if rng is None:
            rng = np.random.default_rng()

        # caps[i] has nominal weight 2^i (LSB at i=0, MSB at i=n_bits-1)
        nominal = np.array([2**i for i in range(n_bits)], dtype=float)
        mismatch = 1.0 + mismatch_sigma * rng.standard_normal(n_bits)
        self.caps: np.ndarray = nominal * mismatch
        # The standard C-DAC requires a termination capacitor (C_unit, no mismatch)
        # so that C_total = 2^N * C_unit and all-ones output = Vref*(1 - 1/2^N).
        self.c_term: float = 1.0  # nominal C_unit, fixed (no mismatch)
        self.c_total: float = float(self.caps.sum()) + self.c_term

    def voltage(self, bits: list[int] | np.ndarray) -> float:
        """
        Compute DAC output voltage for a given bit pattern.

        Parameters
        ----------
        bits : sequence of length n_bits
            bits[0] is the MSB (weight 2^(n_bits-1)),
            bits[n_bits-1] is the LSB (weight 2^0).

        Returns
        -------
        float : DAC voltage in [0, Vref]
        """
        # bits[0] = MSB maps to caps[n_bits-1]; reverse to align weights
        b = np.asarray(bits, dtype=float)
        return float(self.vref * np.dot(b[::-1], self.caps) / self.c_total)
