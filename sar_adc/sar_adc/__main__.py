"""Entry point: python -m sar_adc [options]"""

from __future__ import annotations

import argparse
import sys

import matplotlib
import matplotlib.pyplot as plt


def main() -> None:
    parser = argparse.ArgumentParser(
        description="12-bit SAR ADC behavioral simulation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed for reproducible mismatch/noise")
    parser.add_argument("--mismatch-sigma", type=float, default=0.001,
                        help="Fractional std-dev of capacitor mismatch")
    parser.add_argument("--noise-sigma", type=float, default=1e-4,
                        help="Comparator RMS noise in volts")
    parser.add_argument("--offset", type=float, default=0.0,
                        help="Comparator static offset in volts")
    parser.add_argument("--vin", type=float, default=0.3,
                        help="Input voltage for the waveform panel (V)")
    parser.add_argument("--n-points", type=int, default=50_000,
                        help="Number of sweep points for DNL/INL")
    parser.add_argument("--save", type=str, default=None,
                        help="Save figure to this file path (e.g. results.png)")
    parser.add_argument("--no-show", action="store_true",
                        help="Do not open an interactive window (useful in CI)")
    args = parser.parse_args()

    # Lazy imports so --help is fast
    from .adc import SARADC
    from .sweep import sweep
    from .plots import plot_all

    if args.no_show or args.save:
        matplotlib.use("Agg")

    print(f"Building ADC  seed={args.seed}  mismatch_σ={args.mismatch_sigma}"
          f"  noise_σ={args.noise_sigma}  offset={args.offset} V")

    adc = SARADC(
        n_bits=12,
        vref=1.0,
        mismatch_sigma=args.mismatch_sigma,
        comparator_offset=args.offset,
        comparator_noise_sigma=args.noise_sigma,
        seed=args.seed,
    )

    print(f"Running waveform conversion  Vin={args.vin} V …")
    _, steps = adc.convert_verbose(args.vin)

    print(f"Running full-scale sweep  ({args.n_points:,} points) …")
    result = sweep(adc, n_points=args.n_points)

    dnl_peak = float(abs(result.dnl[~(result.dnl == -1.0)]).max()) if result.dnl.size else 0.0
    inl_peak = float(abs(result.inl).max()) if result.inl.size else 0.0
    print(f"DNL peak = ±{dnl_peak:.3f} LSB   INL peak = ±{inl_peak:.3f} LSB")

    print("Rendering figure …")
    fig = plot_all(adc, result, steps, args.vin, save_path=args.save)

    if args.save:
        print(f"Figure saved to: {args.save}")

    if not args.no_show:
        plt.show()

    return fig


if __name__ == "__main__":
    main()
