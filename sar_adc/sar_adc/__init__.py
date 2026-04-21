"""12-bit SAR ADC behavioral simulation package."""

from .adc import SARADC
from .sweep import SweepResult, sweep
from .plots import plot_all

__all__ = ["SARADC", "sweep", "SweepResult", "plot_all"]
