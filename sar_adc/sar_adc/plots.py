"""2×2 matplotlib figure for SAR ADC characterization."""

from __future__ import annotations

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.figure

from .adc import SARADC
from .sar_logic import ConversionStep
from .sweep import SweepResult

# Use non-interactive backend when no display is available
matplotlib.rcParams.setdefault("figure.dpi", 150)


def plot_all(
    adc: SARADC,
    result: SweepResult,
    steps: list[ConversionStep],
    vin_sample: float,
    save_path: str | None = None,
) -> matplotlib.figure.Figure:
    """
    Draw a 2×2 characterization figure and optionally save it to disk.

    Layout
    ------
    [0,0] Conversion waveform (single sample)
    [0,1] Transfer curve (full-scale)
    [1,0] DNL vs. output code
    [1,1] INL vs. output code

    Parameters
    ----------
    adc        : SARADC instance (for metadata labels)
    result     : SweepResult from sweep()
    steps      : ConversionStep list from adc.convert_verbose(vin_sample)
    vin_sample : Vin used for the waveform panel
    save_path  : If given, save figure to this path
    """
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    _plot_waveform(axes[0, 0], steps, vin_sample, adc.vref, adc.lsb, adc.n_bits)
    _plot_transfer(axes[0, 1], result, adc.vref, adc.n_bits)
    _plot_dnl(axes[1, 0], result)
    _plot_inl(axes[1, 1], result)

    fig.suptitle(
        f"{adc.n_bits}-bit SAR ADC Characterization  |  "
        f"mismatch_σ={adc._cdac.caps.std() / adc._cdac.caps.mean():.4f}  "
        f"noise_σ={adc._comparator.noise_sigma:.2e} V  "
        f"Vref={adc.vref} V",
        fontsize=12,
        fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    if save_path:
        fig.savefig(save_path, bbox_inches="tight")

    return fig


# ---------------------------------------------------------------------------
# Panel helpers
# ---------------------------------------------------------------------------

def _plot_waveform(
    ax: plt.Axes,
    steps: list[ConversionStep],
    vin: float,
    vref: float,
    lsb: float,
    n_bits: int,
) -> None:
    cycles = [s.cycle for s in steps]
    vdac_values = [s.vdac for s in steps]

    # Plot Vdac as a step trace
    ax.step(cycles, vdac_values, where="post", color="steelblue",
            linewidth=2, label="$V_{DAC}$")
    ax.scatter(cycles, vdac_values, color="steelblue", zorder=5, s=40)

    # Vin reference line
    ax.axhline(vin, color="crimson", linestyle="--", linewidth=1.5, label=f"$V_{{in}}$ = {vin:.4f} V")

    # Annotate each bit decision above the marker
    for s in steps:
        label = f"b{s.bit_index}={'1' if s.bit_decision else '0'}"
        ax.annotate(
            label,
            xy=(s.cycle, s.vdac),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            fontsize=7,
            color="navy",
        )

    # Resolved code at the bottom
    final_code = sum(s.bit_decision * 2 ** s.bit_index for s in steps)
    ax.set_title(f"Conversion Waveform  (code = {final_code}, "
                 f"error = {(vin - final_code * lsb) / lsb:.2f} LSB)")
    ax.set_xlabel("Clock Cycle")
    ax.set_ylabel("Voltage (V)")
    ax.set_xlim(0.5, n_bits + 0.5)
    ax.set_ylim(-0.05 * vref, 1.1 * vref)
    ax.set_xticks(range(1, n_bits + 1))
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)


def _plot_transfer(
    ax: plt.Axes,
    result: SweepResult,
    vref: float,
    n_bits: int,
) -> None:
    # Downsample: keep only points where the code changes (transition edges)
    diff = np.diff(result.codes)
    edge_idx = np.where(diff != 0)[0]
    # Include the point before and after each edge for a clean step look
    keep = np.unique(np.concatenate([edge_idx, edge_idx + 1]))
    keep = np.clip(keep, 0, len(result.vin_points) - 1)

    ax.plot(result.vin_points[keep], result.codes[keep],
            color="royalblue", linewidth=0.8, label="Actual")

    # Ideal staircase
    n_codes = 2 ** n_bits
    ideal_vin = np.linspace(0, vref, n_codes, endpoint=False)
    ideal_code = np.arange(n_codes)
    ax.step(ideal_vin, ideal_code, where="post",
            color="lightgray", linewidth=0.6, label="Ideal", zorder=0)

    ax.set_title("Transfer Curve")
    ax.set_xlabel("$V_{in}$ (V)")
    ax.set_ylabel("Output Code")
    ax.set_xlim(0, vref)
    ax.set_ylim(0, n_codes)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)


def _plot_dnl(ax: plt.Axes, result: SweepResult) -> None:
    codes = np.arange(1, len(result.dnl) + 1)
    dnl = result.dnl

    # Stem plot
    markerline, stemlines, baseline = ax.stem(
        codes, dnl, linefmt="C0-", markerfmt="C0.", basefmt="k-"
    )
    plt.setp(stemlines, linewidth=0.5)
    plt.setp(markerline, markersize=2)

    ax.axhline(0.5, color="red", linestyle="--", linewidth=1, alpha=0.7, label="±0.5 LSB")
    ax.axhline(-0.5, color="red", linestyle="--", linewidth=1, alpha=0.7)
    ax.axhline(0.0, color="black", linewidth=0.5)

    peak = np.nanmax(np.abs(dnl))
    ax.set_title(f"DNL  (peak = ±{peak:.3f} LSB)")
    ax.set_xlabel("Output Code")
    ax.set_ylabel("DNL (LSB)")
    ax.set_xlim(0, len(dnl))
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)


def _plot_inl(ax: plt.Axes, result: SweepResult) -> None:
    codes = np.arange(1, len(result.inl) + 1)
    inl = result.inl

    ax.plot(codes, inl, color="royalblue", linewidth=1.0)
    ax.fill_between(codes, inl, alpha=0.15, color="royalblue")

    ax.axhline(1.0, color="red", linestyle="--", linewidth=1, alpha=0.7, label="±1 LSB")
    ax.axhline(-1.0, color="red", linestyle="--", linewidth=1, alpha=0.7)
    ax.axhline(0.0, color="black", linewidth=0.5)

    peak = np.nanmax(np.abs(inl))
    ax.set_title(f"INL  (peak = ±{peak:.3f} LSB)")
    ax.set_xlabel("Output Code")
    ax.set_ylabel("INL (LSB)")
    ax.set_xlim(0, len(inl))
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
