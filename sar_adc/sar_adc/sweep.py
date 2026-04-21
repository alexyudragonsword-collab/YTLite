"""Full-scale sweep engine for DNL/INL characterization."""

from __future__ import annotations

import dataclasses

import numpy as np

from .adc import SARADC


@dataclasses.dataclass
class SweepResult:
    """Results of a full-scale input sweep."""
    vin_points: np.ndarray          # shape (n_points,)  — input voltages
    codes: np.ndarray               # shape (n_points,)  — int output codes
    transition_voltages: np.ndarray # shape (n_codes-1,) — V_k: first Vin giving code ≥ k
    dnl: np.ndarray                 # shape (n_codes-2,) — DNL in LSB (interior codes)
    inl: np.ndarray                 # shape (n_codes-2,) — INL in LSB (endpoint method)


def sweep(adc: SARADC, n_points: int = 50_000) -> SweepResult:
    """
    Sweep the analog input from 0 to Vref and characterize DNL/INL.

    Parameters
    ----------
    adc : SARADC
        ADC instance to characterize (mismatch already realized).
    n_points : int
        Number of uniformly-spaced input samples.  Should be >> 2^n_bits
        so each code bin is hit multiple times.

    Returns
    -------
    SweepResult
    """
    n_codes = 2 ** adc.n_bits
    lsb_ideal = adc.vref / n_codes

    # Input array: [0, Vref), avoiding the exact full-scale boundary
    vin_array = np.linspace(0.0, adc.vref, n_points, endpoint=False)

    # Conversion loop — cannot vectorize because Comparator draws fresh noise each call
    codes = np.empty(n_points, dtype=int)
    for i, vin in enumerate(vin_array):
        codes[i] = adc.convert(vin)

    # --- Transition voltages ---
    # V_k = first vin_array value at which output code becomes >= k (k = 1..n_codes-1)
    transition_voltages = np.full(n_codes - 1, np.nan)
    for k in range(1, n_codes):
        idx = np.searchsorted(codes, k, side="left")
        # searchsorted on a non-monotone array may miss; find first occurrence explicitly
        where = np.nonzero(codes >= k)[0]
        if where.size > 0:
            transition_voltages[k - 1] = vin_array[where[0]]
        # else: code k never appeared (missing code) → stays NaN

    # --- DNL (interior codes: indices 1..n_codes-2) ---
    # dnl[k-1] = (V_{k+1} - V_k) / lsb_ideal - 1   for k = 1..n_codes-2
    dnl = np.full(n_codes - 2, np.nan)
    for k in range(1, n_codes - 1):
        v_lo = transition_voltages[k - 1]   # V_k
        v_hi = transition_voltages[k]       # V_{k+1}
        if np.isnan(v_lo) or np.isnan(v_hi):
            dnl[k - 1] = -1.0  # missing-code convention
        else:
            dnl[k - 1] = (v_hi - v_lo) / lsb_ideal - 1.0

    # --- INL (endpoint method) ---
    # Cumulative sum of DNL, then subtract a linear ramp so INL[0]=0 and INL[-1]=0
    dnl_for_sum = np.where(np.isnan(dnl), -1.0, dnl)
    inl_raw = np.cumsum(dnl_for_sum)

    start = inl_raw[0] if not np.isnan(inl_raw[0]) else 0.0
    end = inl_raw[-1] if not np.isnan(inl_raw[-1]) else 0.0
    correction = np.linspace(start, end, len(inl_raw))
    inl = inl_raw - correction

    return SweepResult(
        vin_points=vin_array,
        codes=codes,
        transition_voltages=transition_voltages,
        dnl=dnl,
        inl=inl,
    )
