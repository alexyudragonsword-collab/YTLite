"""SAR state machine and per-cycle conversion step logging."""

from __future__ import annotations

import dataclasses

from .cdac import CDAC
from .comparator import Comparator


@dataclasses.dataclass
class ConversionStep:
    """Snapshot of one SAR clock cycle, used for waveform plotting."""
    cycle: int           # 1-based cycle number (1 = MSB trial)
    bit_index: int       # bit position being decided (11 = MSB, 0 = LSB)
    trial_bits: list[int]
    vdac: float
    comparator_out: bool
    bit_decision: int    # final settled value (0 or 1)


class SARLogic:
    """
    12-cycle successive approximation register state machine.

    Runs MSB-first: cycle 1 decides bit 11, cycle 12 decides bit 0.
    """

    def __init__(self, cdac: CDAC, comparator: Comparator) -> None:
        self.cdac = cdac
        self.comparator = comparator
        self.n_bits = cdac.n_bits

    def convert(self, vin: float) -> tuple[int, list[ConversionStep]]:
        """
        Perform one full ADC conversion.

        Parameters
        ----------
        vin : float
            Analog input voltage.

        Returns
        -------
        code : int
            Resulting digital code (0 … 2^n_bits - 1).
        steps : list[ConversionStep]
            One entry per clock cycle for waveform plotting.
        """
        # bits[i] represents the bit with weight 2^i;
        # bits[n_bits-1] is MSB, bits[0] is LSB.
        bits = [0] * self.n_bits
        steps: list[ConversionStep] = []

        for cycle in range(self.n_bits):
            bit_idx = self.n_bits - 1 - cycle  # MSB first

            bits[bit_idx] = 1  # trial: tentatively set this bit
            # Reconstruct bits array in MSB-first order for CDAC
            trial_msb_first = bits[::-1]
            vdac = self.cdac.voltage(trial_msb_first)
            comp_out = self.comparator.compare(vin, vdac)

            if not comp_out:
                # Vin < Vdac → trial voltage too high → clear this bit
                bits[bit_idx] = 0

            steps.append(ConversionStep(
                cycle=cycle + 1,
                bit_index=bit_idx,
                trial_bits=trial_msb_first.copy(),
                vdac=vdac,
                comparator_out=comp_out,
                bit_decision=bits[bit_idx],
            ))

        code = sum(b * (2 ** i) for i, b in enumerate(bits))
        return code, steps
