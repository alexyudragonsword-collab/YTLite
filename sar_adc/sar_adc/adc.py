"""Top-level SARADC orchestrator — the primary public API."""

from __future__ import annotations

import numpy as np

from .cdac import CDAC
from .comparator import Comparator
from .sar_logic import ConversionStep, SARLogic


class SARADC:
    """
    12-bit SAR ADC behavioral model.

    Instantiate once per simulated device; mismatch is fixed at construction
    time and shared across all subsequent conversions (models a single chip).

    Parameters
    ----------
    n_bits : int
        ADC resolution (default 12).
    vref : float
        Full-scale reference voltage in volts (default 1.0).
    mismatch_sigma : float
        Fractional std-dev of per-capacitor mismatch (default 0.001 ≈ 0.1 %).
    comparator_offset : float
        Static comparator input-referred offset in volts (default 0.0).
    comparator_noise_sigma : float
        RMS comparator noise in volts (default 1e-4 = 0.4 LSB for 12-bit 1V).
    seed : int | None
        RNG seed for reproducible results.  None → non-deterministic.
    """

    def __init__(
        self,
        n_bits: int = 12,
        vref: float = 1.0,
        mismatch_sigma: float = 0.001,
        comparator_offset: float = 0.0,
        comparator_noise_sigma: float = 1e-4,
        seed: int | None = None,
    ) -> None:
        self.n_bits = n_bits
        self.vref = vref

        rng = np.random.default_rng(seed)
        cdac_rng, comp_rng = rng.spawn(2)

        self._cdac = CDAC(n_bits, vref, mismatch_sigma, cdac_rng)
        self._comparator = Comparator(comparator_offset, comparator_noise_sigma, comp_rng)
        self._sar = SARLogic(self._cdac, self._comparator)

    @property
    def lsb(self) -> float:
        """Ideal LSB voltage = Vref / 2^n_bits."""
        return self.vref / (2 ** self.n_bits)

    def convert(self, vin: float) -> int:
        """Fast path: return integer code only (no step log)."""
        code, _ = self._sar.convert(vin)
        return code

    def convert_verbose(self, vin: float) -> tuple[int, list[ConversionStep]]:
        """Return integer code and full per-cycle step log (for waveform plot)."""
        return self._sar.convert(vin)
