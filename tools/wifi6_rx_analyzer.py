#!/usr/bin/env python3
"""
WiFi 6 (802.11ax) Direct Conversion Receiver Link Analysis Tool

Supports MCS11 80 MHz signal bandwidth.  Analyzes:
  - Cascaded noise figure  (target < 4.5 dB)
  - EVM floor              (target < -35 dB across sensitivity to -50 dBm)
  - IQ mismatch specs
  - LO integrated phase noise (IPN)
  - Cascaded IIP3
  - AGC gain control range

Usage:
  python3 wifi6_rx_analyzer.py                     # default receiver chain
  python3 wifi6_rx_analyzer.py --derive            # show required specs
  python3 wifi6_rx_analyzer.py --plot              # save EVM plot
  python3 wifi6_rx_analyzer.py --iq-amp 0.5 --iq-phase 2.0 --lo-ipn -38
"""

import sys
import argparse
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# ---------------------------------------------------------------------------
# WiFi 6 / 802.11ax constants
# ---------------------------------------------------------------------------

# {mcs: (modulation_order, coding_rate, min_snr_db, evm_limit_db)}
# SNR values from IEEE 802.11ax PER < 10% at 10% PER sensitivity target
WIFI6_MCS = {
    0:  (2,    1/2,   2.0,  -5.0),   # BPSK
    1:  (4,    1/2,   5.0,  -8.0),   # QPSK
    2:  (4,    3/4,   8.0,  -8.0),   # QPSK
    3:  (16,   1/2,  11.0, -13.0),   # 16-QAM
    4:  (16,   3/4,  14.5, -13.0),   # 16-QAM
    5:  (64,   2/3,  17.5, -19.0),   # 64-QAM
    6:  (64,   3/4,  19.5, -19.0),   # 64-QAM
    7:  (64,   5/6,  21.0, -19.0),   # 64-QAM
    8:  (256,  3/4,  24.0, -25.0),   # 256-QAM
    9:  (256,  5/6,  26.5, -25.0),   # 256-QAM
    10: (1024, 3/4,  29.5, -35.0),   # 1024-QAM (WiFi 6 new)
    11: (1024, 5/6,  32.5, -35.0),   # 1024-QAM (WiFi 6 new)
}

# {bw_mhz: {'bw_hz', 'n_data_sc'}} — HE SU format
WIFI6_BW = {
    20:  {"bw_hz": 20e6,  "n_data_sc": 234},
    40:  {"bw_hz": 40e6,  "n_data_sc": 468},
    80:  {"bw_hz": 80e6,  "n_data_sc": 980},
    160: {"bw_hz": 160e6, "n_data_sc": 1960},
}

KT_DBM_HZ      = -174.0   # thermal noise density at 290 K (dBm/Hz)
SUBCARRIER_HZ  = 78125.0  # 802.11ax subcarrier spacing (Hz)
OFDM_PAPR_DB   = 10.0     # typical OFDM PAPR (dB)

# EVM floor requirement
EVM_FLOOR_LIMIT_DB = -35.0
NF_LIMIT_DB        = 4.5


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RxChainStage:
    """One stage in the receiver chain."""
    name: str
    gain_db: float          # positive = amplification, negative = loss
    nf_db: float            # noise figure (dB)
    iip3_dbm: float         # input-referred IP3 (dBm)

    @property
    def oip3_dbm(self) -> float:
        return self.iip3_dbm + self.gain_db


@dataclass
class ReceiverConfig:
    """All configurable parameters of the receiver under analysis."""
    mcs: int = 11
    bw_mhz: float = 80.0

    stages: List[RxChainStage] = field(default_factory=list)

    # IQ mismatch
    iq_amp_imbalance_db: float = 0.3    # amplitude imbalance (dB)
    iq_phase_imbalance_deg: float = 1.0  # phase imbalance (degrees)

    # LO phase noise
    lo_ipn_dbc: float = -40.0           # integrated phase noise (dBc, RMS)

    # ADC
    adc_bits: int = 12
    adc_snr_db: Optional[float] = None  # override calculated SNR

    # Dynamic range
    p_max_dbm: float = -50.0            # maximum input power for EVM spec

    # Targets
    evm_target_db: float = EVM_FLOOR_LIMIT_DB
    nf_limit_db: float = NF_LIMIT_DB


@dataclass
class LinkBudget:
    """Results of the full link budget analysis."""
    # Cascaded chain
    total_gain_db: float = 0.0
    cascaded_nf_db: float = 0.0
    cascaded_iip3_dbm: float = 0.0

    # Sensitivity
    noise_floor_dbm: float = 0.0
    required_snr_db: float = 0.0
    sensitivity_dbm: float = 0.0

    # AGC
    agc_range_db: float = 0.0

    # EVM contributors at p_max_dbm
    evm_thermal_db: float = 0.0
    evm_iq_db: float = 0.0
    evm_pn_db: float = 0.0
    evm_adc_db: float = 0.0
    evm_nl_db: float = 0.0
    evm_floor_db: float = 0.0   # RSS of distortion-only contributors
    evm_total_db: float = 0.0   # RSS of all contributors

    # Derived from IQ
    irr_db: float = 0.0

    # Margins
    evm_floor_margin_db: float = 0.0
    nf_margin_db: float = 0.0


# ---------------------------------------------------------------------------
# Core analysis engine
# ---------------------------------------------------------------------------

class WiFi6RxAnalyzer:
    """WiFi 6 direct conversion receiver link analysis."""

    def __init__(self, config: ReceiverConfig):
        self.config = config
        bw_key = int(config.bw_mhz)
        if bw_key not in WIFI6_MCS:
            pass  # MCS validated separately
        if bw_key not in WIFI6_BW:
            raise ValueError(f"Unsupported bandwidth: {config.bw_mhz} MHz. Choose from {list(WIFI6_BW)}")
        if config.mcs not in WIFI6_MCS:
            raise ValueError(f"Unsupported MCS: {config.mcs}. Choose 0-11.")

        self._mcs_row = WIFI6_MCS[config.mcs]
        self._bw_row  = WIFI6_BW[bw_key]
        self._budget: Optional[LinkBudget] = None

    # --- MCS properties ---

    @property
    def modulation_order(self) -> int:
        return self._mcs_row[0]

    @property
    def coding_rate(self) -> float:
        return self._mcs_row[1]

    @property
    def required_snr_db(self) -> float:
        return self._mcs_row[2]

    @property
    def evm_limit_db(self) -> float:
        return self._mcs_row[3]

    @property
    def bw_hz(self) -> float:
        return self._bw_row["bw_hz"]

    @property
    def n_data_sc(self) -> int:
        return self._bw_row["n_data_sc"]

    # --- RF calculation helpers ---

    def cascaded_noise_figure(self, stages: List[RxChainStage]) -> float:
        """Friis cascaded noise figure (dB)."""
        if not stages:
            return 0.0
        f_total = _db2lin(stages[0].nf_db)        # noise factor F = 10^(NF/10)
        g_accum = _db2pow(stages[0].gain_db)
        for s in stages[1:]:
            f_total += (_db2lin(s.nf_db) - 1.0) / g_accum
            g_accum *= _db2pow(s.gain_db)
        return _lin2db(f_total)

    def cascaded_iip3(self, stages: List[RxChainStage]) -> float:
        """Input-referred cascaded IIP3 (dBm).

        Uses the power-domain Friis-like formula:
            1/IIP3_total = 1/IIP3_1 + G1/IIP3_2 + G1*G2/IIP3_3 + …
        where all IIP3 values are in mW and G in linear power ratio.
        """
        if not stages:
            return 100.0
        inv_iip3 = 0.0
        g_accum  = 1.0
        for s in stages:
            iip3_mw = _dbm2mw(s.iip3_dbm)
            inv_iip3 += g_accum / iip3_mw
            g_accum  *= _db2pow(s.gain_db)
        if inv_iip3 <= 0.0:
            return 100.0
        return _mw2dbm(1.0 / inv_iip3)

    def iq_mismatch_evm(self) -> tuple:
        """IQ mismatch EVM and image rejection ratio.

        Small-signal model:
            ε   = 10^(A_dB/20) - 1   (amplitude imbalance factor)
            φ   = phase_deg * π/180   (phase error, radians)
            EVM²_IQ = (ε² + φ²) / 4
            IRR_dB  = -EVM_IQ_dB

        Returns
        -------
        evm_db : float
        irr_db : float
        """
        eps = 10 ** (self.config.iq_amp_imbalance_db / 20.0) - 1.0
        phi = np.deg2rad(self.config.iq_phase_imbalance_deg)
        evm_sq = (eps ** 2 + phi ** 2) / 4.0
        if evm_sq <= 0:
            return -100.0, 100.0
        evm_db = 10.0 * np.log10(evm_sq)
        irr_db = -evm_db
        return evm_db, irr_db

    def phase_noise_evm(self) -> float:
        """LO phase noise EVM (dB), conservative (no CPE correction).

        EVM_PN_dB = IPN_dBc   because φ_rms = 10^(IPN/20) and EVM ≈ φ_rms.
        """
        return self.config.lo_ipn_dbc

    def adc_evm(self) -> float:
        """ADC quantization-noise EVM (dB).

        SNR = 6.02*N + 1.76 - PAPR  (dB)
        EVM_ADC = -SNR
        """
        if self.config.adc_snr_db is not None:
            snr = self.config.adc_snr_db
        else:
            snr = 6.02 * self.config.adc_bits + 1.76 - OFDM_PAPR_DB
        return -snr

    def nonlinearity_evm(self, p_in_dbm: float) -> float:
        """IP3 nonlinearity EVM at given input power (dB).

        Two-tone IM3 baseline corrected +4.5 dB for OFDM multi-tone:
            EVM_NL = 2*(P_in - IIP3) + 4.5
        """
        iip3 = self.cascaded_iip3(self.config.stages)
        im3_dbc = 2.0 * (p_in_dbm - iip3)
        return im3_dbc + 4.5

    def thermal_noise_evm(self, p_in_dbm: float, nf_db: float) -> float:
        """Thermal-noise EVM at given input power and NF (dB).

        EVM_thermal = -(P_in - noise_floor)
        """
        noise_floor = KT_DBM_HZ + 10.0 * np.log10(self.bw_hz) + nf_db
        return -(p_in_dbm - noise_floor)

    # --- Full analysis ---

    def analyze(self) -> LinkBudget:
        """Compute complete link budget and EVM breakdown."""
        cfg = self.config
        stages = cfg.stages
        b = LinkBudget()

        # Cascaded chain
        if stages:
            b.total_gain_db    = sum(s.gain_db for s in stages)
            b.cascaded_nf_db   = self.cascaded_noise_figure(stages)
            b.cascaded_iip3_dbm = self.cascaded_iip3(stages)
        else:
            b.cascaded_nf_db   = 0.0
            b.cascaded_iip3_dbm = 0.0

        # Sensitivity
        b.noise_floor_dbm = KT_DBM_HZ + 10.0 * np.log10(self.bw_hz) + b.cascaded_nf_db
        b.required_snr_db = self.required_snr_db
        b.sensitivity_dbm = b.noise_floor_dbm + b.required_snr_db

        # AGC range
        b.agc_range_db = cfg.p_max_dbm - b.sensitivity_dbm

        # EVM at p_max (distortion floor + thermal)
        p = cfg.p_max_dbm
        b.evm_iq_db, b.irr_db = self.iq_mismatch_evm()
        b.evm_pn_db            = self.phase_noise_evm()
        b.evm_adc_db           = self.adc_evm()
        b.evm_nl_db            = self.nonlinearity_evm(p)
        b.evm_thermal_db       = self.thermal_noise_evm(p, b.cascaded_nf_db)

        # EVM floor = RSS of distortion contributors only
        distortion = [b.evm_iq_db, b.evm_pn_db, b.evm_adc_db, b.evm_nl_db]
        b.evm_floor_db = _rss_db(distortion)

        # Total EVM including thermal
        b.evm_total_db = _rss_db(distortion + [b.evm_thermal_db])

        # Margins
        b.evm_floor_margin_db = cfg.evm_target_db - b.evm_floor_db   # negative = PASS
        b.nf_margin_db        = cfg.nf_limit_db - b.cascaded_nf_db   # positive = PASS

        self._budget = b
        return b

    def evm_vs_power(
        self,
        p_range: Optional[np.ndarray] = None,
    ) -> tuple:
        """EVM (dB) vs input power sweep.

        Returns
        -------
        powers : np.ndarray
        evm_total : np.ndarray
        evm_floor : np.ndarray   (distortion only, flat line)
        """
        b = self._budget or self.analyze()
        if p_range is None:
            p_range = np.linspace(b.sensitivity_dbm - 5.0, self.config.p_max_dbm + 10.0, 400)

        nf = b.cascaded_nf_db
        evm_iq  = b.evm_iq_db
        evm_pn  = b.evm_pn_db
        evm_adc = b.evm_adc_db

        evm_total = []
        evm_floor = []
        for p in p_range:
            nl      = self.nonlinearity_evm(p)
            thermal = self.thermal_noise_evm(p, nf)
            floor_  = _rss_db([evm_iq, evm_pn, evm_adc, nl])
            total   = _rss_db([evm_iq, evm_pn, evm_adc, nl, thermal])
            evm_floor.append(floor_)
            evm_total.append(total)

        return p_range, np.array(evm_total), np.array(evm_floor)

    def derive_required_specs(self) -> dict:
        """Back-calculate required specs for EVM floor < evm_target_db.

        Distributes the EVM budget equally across four distortion contributors:
            IQ mismatch, LO phase noise, ADC quantization, IP3 nonlinearity.
        Each contributor is allowed  EVM_per = 10·log10(10^(target/10)/4).
        """
        cfg = self.config
        target = cfg.evm_target_db

        # Per-contributor budget (equal split, 4 sources)
        n_contributors = 4
        evm_per = 10.0 * np.log10(10 ** (target / 10.0) / n_contributors)
        thresh  = 10 ** (evm_per / 20.0)   # amplitude threshold

        # IQ mismatch
        # EVM_IQ = sqrt((ε² + φ²)/4) = thresh
        # Equal split between ε and φ: each = thresh * sqrt(2)
        each = thresh * np.sqrt(2.0)
        amp_imb_db   = 20.0 * np.log10(1.0 + each)   # approx upper bound
        phase_err_deg = np.rad2deg(each)
        irr_min_db   = -evm_per

        # LO phase noise:  EVM_PN_dB = IPN_dBc
        lo_ipn_max_dbc = evm_per

        # ADC:  SNR_ADC > -evm_per
        snr_adc_min = -evm_per
        adc_enob_min = int(np.ceil((snr_adc_min - 1.76 + OFDM_PAPR_DB) / 6.02))

        # IIP3 at p_max:  2*(P_in - IIP3) + 4.5 < evm_per
        iip3_min_dbm = cfg.p_max_dbm - (evm_per - 4.5) / 2.0

        # Sensitivity and AGC
        sensitivity = KT_DBM_HZ + 10.0 * np.log10(self.bw_hz) + NF_LIMIT_DB + self.required_snr_db
        agc_range   = cfg.p_max_dbm - sensitivity

        return {
            "evm_per_contributor_db":   round(evm_per, 2),
            "iq_amp_imbalance_max_db":  round(amp_imb_db, 3),
            "iq_phase_error_max_deg":   round(phase_err_deg, 3),
            "iq_irr_min_db":            round(irr_min_db, 1),
            "lo_ipn_max_dbc":           round(lo_ipn_max_dbc, 1),
            "adc_enob_min_bits":        adc_enob_min,
            "adc_snr_min_db":           round(snr_adc_min, 1),
            "iip3_min_dbm":             round(iip3_min_dbm, 1),
            "nf_max_db":                NF_LIMIT_DB,
            "sensitivity_dbm":          round(sensitivity, 1),
            "agc_range_min_db":         round(agc_range, 1),
        }

    # --- Report ---

    def print_report(self, derive: bool = False) -> None:
        """Print full analysis report to stdout."""
        b = self.analyze()
        cfg = self.config

        sep  = "=" * 72
        sep2 = "-" * 72

        print(sep)
        print("  WiFi 6 (802.11ax) Direct Conversion Receiver  — Link Analysis")
        print(sep)

        # ---- System Target ----
        print("\n[1] SYSTEM TARGET")
        print(sep2)
        mod_name = {2: "BPSK", 4: "QPSK", 16: "16-QAM",
                    64: "64-QAM", 256: "256-QAM", 1024: "1024-QAM"}
        mod_str = mod_name.get(self.modulation_order, str(self.modulation_order) + "-QAM")
        print(f"  MCS index          : MCS{cfg.mcs}  "
              f"({mod_str},  rate {self.coding_rate:.4g})")
        print(f"  Signal bandwidth   : {cfg.bw_mhz:.0f} MHz  "
              f"({self.n_data_sc} data subcarriers, Δf = {SUBCARRIER_HZ/1e3:.3g} kHz)")
        print(f"  Required SNR       : {self.required_snr_db:.1f} dB")
        print(f"  EVM limit          : {self.evm_limit_db:.0f} dB "
              f"({_evm_pct(self.evm_limit_db):.2f} %)")
        print(f"  NF requirement     : < {cfg.nf_limit_db:.1f} dB")
        print(f"  Max input power    : {cfg.p_max_dbm:.0f} dBm  (EVM spec upper bound)")
        print(f"  OFDM PAPR          : {OFDM_PAPR_DB:.0f} dB  (typical)")

        # ---- Receiver chain ----
        print(f"\n[2] RECEIVER CHAIN  (cascaded)")
        print(sep2)
        if cfg.stages:
            hdr = f"  {'Stage':<18} {'Gain':>8} {'NF':>8} {'IIP3':>10} {'OIP3':>10}"
            print(hdr)
            print(f"  {'':<18} {'(dB)':>8} {'(dB)':>8} {'(dBm)':>10} {'(dBm)':>10}")
            print(f"  {'-'*18} {'-'*8} {'-'*8} {'-'*10} {'-'*10}")
            for s in cfg.stages:
                print(f"  {s.name:<18} {s.gain_db:>8.1f} {s.nf_db:>8.1f} "
                      f"{s.iip3_dbm:>10.1f} {s.oip3_dbm:>10.1f}")
            print(f"  {'─'*18} {'─'*8} {'─'*8} {'─'*10} {'─'*10}")
            print(f"  {'CASCADED':<18} {b.total_gain_db:>8.1f} {b.cascaded_nf_db:>8.2f} "
                  f"{b.cascaded_iip3_dbm:>10.1f}")
        else:
            print("  (no stages configured)")
            print(f"  Cascaded NF   : {b.cascaded_nf_db:.2f} dB")
            print(f"  Cascaded IIP3 : {b.cascaded_iip3_dbm:.1f} dBm")

        nf_ok = "PASS ✓" if b.nf_margin_db >= 0 else "FAIL ✗"
        print(f"\n  Cascaded NF    = {b.cascaded_nf_db:.2f} dB  "
              f"(limit {cfg.nf_limit_db:.1f} dB,  margin {b.nf_margin_db:+.2f} dB  [{nf_ok}])")
        print(f"  Noise floor    = {b.noise_floor_dbm:.1f} dBm")
        print(f"  Sensitivity    = {b.sensitivity_dbm:.1f} dBm  "
              f"(NF + kTB + SNR_req = {b.cascaded_nf_db:.1f} + "
              f"{KT_DBM_HZ + 10*np.log10(self.bw_hz):.0f} + {b.required_snr_db:.1f} dB)")

        # ---- EVM budget ----
        print(f"\n[3] EVM BUDGET  (at P_in = {cfg.p_max_dbm:.0f} dBm)")
        print(sep2)
        rows = [
            ("Thermal noise",    b.evm_thermal_db),
            ("IQ mismatch",      b.evm_iq_db),
            ("LO phase noise",   b.evm_pn_db),
            ("ADC quantization", b.evm_adc_db),
            ("IP3 nonlinearity", b.evm_nl_db),
        ]
        print(f"  {'Contributor':<22} {'EVM (dB)':>10} {'EVM (%)':>10}")
        print(f"  {'-'*22} {'-'*10} {'-'*10}")
        for name, val in rows:
            pct = _evm_pct(val)
            print(f"  {name:<22} {val:>10.1f} {pct:>10.3f}")
        print(f"  {'─'*22} {'─'*10} {'─'*10}")
        print(f"  {'EVM floor (RSS, no thermal)':<22} {b.evm_floor_db:>10.1f} "
              f"{_evm_pct(b.evm_floor_db):>10.3f}")
        print(f"  {'Total EVM (RSS, all)':<22} {b.evm_total_db:>10.1f} "
              f"{_evm_pct(b.evm_total_db):>10.3f}")

        floor_ok = "PASS ✓" if b.evm_floor_margin_db >= 0 else "FAIL ✗"
        print(f"\n  EVM floor target : {cfg.evm_target_db:.0f} dB")
        print(f"  EVM floor result : {b.evm_floor_db:.2f} dB  "
              f"(margin {b.evm_floor_margin_db:+.2f} dB  [{floor_ok}])")

        # ---- IQ / PN / ADC details ----
        print(f"\n[4] IMPAIRMENT DETAILS")
        print(sep2)
        print(f"  IQ amplitude imbalance : {cfg.iq_amp_imbalance_db:.2f} dB")
        print(f"  IQ phase imbalance     : {cfg.iq_phase_imbalance_deg:.2f}°")
        print(f"  Image rejection ratio  : {b.irr_db:.1f} dB")
        print(f"  LO integrated PN (IPN) : {cfg.lo_ipn_dbc:.1f} dBc  (conservative, no CPE corr.)")
        adc_snr = cfg.adc_snr_db if cfg.adc_snr_db else 6.02 * cfg.adc_bits + 1.76 - OFDM_PAPR_DB
        print(f"  ADC resolution         : {cfg.adc_bits} bits  (SNR ≈ {adc_snr:.1f} dB)")
        print(f"  Cascaded IIP3          : {b.cascaded_iip3_dbm:.1f} dBm")
        im3 = 2 * (cfg.p_max_dbm - b.cascaded_iip3_dbm)
        print(f"  IM3 @ P_max            : {im3:.1f} dBc  (two-tone)  → OFDM: {im3+4.5:.1f} dBc")

        # ---- AGC ----
        print(f"\n[5] AGC GAIN CONTROL RANGE")
        print(sep2)
        print(f"  Sensitivity            : {b.sensitivity_dbm:.1f} dBm  (min. useful input)")
        print(f"  Max input (EVM spec)   : {cfg.p_max_dbm:.0f} dBm")
        print(f"  Dynamic range          : {b.agc_range_db:.1f} dB")
        print(f"  AGC range required     : ≥ {b.agc_range_db:.1f} dB")

        # ---- Required specs (optional) ----
        if derive:
            self._print_required_specs()

        print(f"\n{sep}")
        overall = "PASS ✓" if (b.evm_floor_margin_db >= 0 and b.nf_margin_db >= 0) else "FAIL ✗"
        print(f"  OVERALL ASSESSMENT: {overall}")
        print(sep)

    def _print_required_specs(self) -> None:
        cfg = self.config
        sp = self.derive_required_specs()

        sep2 = "-" * 72
        print(f"\n[6] REQUIRED SPECIFICATIONS  (for EVM floor < {cfg.evm_target_db:.0f} dB)")
        print(sep2)
        print(f"  EVM budget per contributor : {sp['evm_per_contributor_db']:.1f} dB  "
              f"(equal 4-way split)")
        print()
        print(f"  {'Parameter':<35} {'Requirement'}")
        print(f"  {'-'*35} {'-'*30}")
        print(f"  {'IQ amplitude imbalance':<35} < {sp['iq_amp_imbalance_max_db']:.3f} dB")
        print(f"  {'IQ phase error':<35} < {sp['iq_phase_error_max_deg']:.3f}°")
        print(f"  {'Image rejection ratio (IRR)':<35} > {sp['iq_irr_min_db']:.1f} dB")
        print(f"  {'LO integrated phase noise (IPN)':<35} < {sp['lo_ipn_max_dbc']:.1f} dBc")
        print(f"  {'ADC ENOB (effective bits)':<35} ≥ {sp['adc_enob_min_bits']} bits")
        print(f"  {'ADC dynamic range':<35} ≥ {sp['adc_snr_min_db']:.1f} dB SNR")
        print(f"  {'Cascaded IIP3 @ P_max={:.0f} dBm'.format(cfg.p_max_dbm):<35}"
              f" > {sp['iip3_min_dbm']:.1f} dBm")
        print(f"  {'Cascaded noise figure':<35} < {sp['nf_max_db']:.1f} dB")
        print(f"  {'Receiver sensitivity':<35} {sp['sensitivity_dbm']:.1f} dBm")
        print(f"  {'AGC range (min.)':<35} ≥ {sp['agc_range_min_db']:.1f} dB")


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_evm_vs_power(
    analyzer: WiFi6RxAnalyzer,
    outfile: str = "evm_vs_power.png",
) -> None:
    """Save EVM vs. input power plot to *outfile*."""
    if not HAS_MPL:
        print("matplotlib not installed — skipping plot.", file=sys.stderr)
        return

    b = analyzer._budget or analyzer.analyze()
    powers, evm_total, evm_floor = analyzer.evm_vs_power()

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(powers, evm_total, color="#2563eb", lw=2, label="EVM total (incl. thermal)")
    ax.plot(powers, evm_floor, color="#dc2626", lw=2, linestyle="--", label="EVM floor (distortion only)")

    # Target line
    ax.axhline(analyzer.config.evm_target_db, color="#16a34a", lw=1.5,
               linestyle=":", label=f"Target {analyzer.config.evm_target_db:.0f} dB")

    # Sensitivity marker
    ax.axvline(b.sensitivity_dbm, color="#9333ea", lw=1.2, linestyle="-.",
               label=f"Sensitivity {b.sensitivity_dbm:.1f} dBm")

    # p_max marker
    ax.axvline(analyzer.config.p_max_dbm, color="#ea580c", lw=1.2, linestyle="-.",
               label=f"P_max {analyzer.config.p_max_dbm:.0f} dBm")

    # Shaded operating window
    ax.axvspan(b.sensitivity_dbm, analyzer.config.p_max_dbm, alpha=0.08,
               color="#2563eb", label="Operating range")

    ax.set_xlabel("Input Power (dBm)", fontsize=11)
    ax.set_ylabel("EVM (dB)", fontsize=11)
    ax.set_title(
        f"WiFi 6 MCS{analyzer.config.mcs} {analyzer.config.bw_mhz:.0f} MHz — EVM vs. Input Power\n"
        f"NF={b.cascaded_nf_db:.1f} dB, IIP3={b.cascaded_iip3_dbm:.1f} dBm, "
        f"IPN={analyzer.config.lo_ipn_dbc:.0f} dBc, "
        f"IQ {analyzer.config.iq_amp_imbalance_db:.2f} dB/{analyzer.config.iq_phase_imbalance_deg:.1f}°",
        fontsize=10,
    )
    ax.legend(fontsize=9, loc="lower right")
    ax.grid(True, alpha=0.35)
    ax.invert_xaxis()  # sensitivity on right (weak signal), strong on left
    ax.set_ylim(bottom=min(evm_total.min(), evm_floor.min()) - 5,
                top=max(evm_total.max(), -30))

    plt.tight_layout()
    plt.savefig(outfile, dpi=150)
    print(f"EVM plot saved → {outfile}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Default receiver chain
# ---------------------------------------------------------------------------

def build_default_receiver() -> ReceiverConfig:
    """Example WiFi 6 STA direct conversion receiver chain.

    Typical architecture: Antenna → LNA → Balun/switch → Passive mixer
                          → BB LPF → VGA → ADC
    """
    stages = [
        RxChainStage("LNA",           gain_db= 15.0, nf_db= 1.5, iip3_dbm=-15.0),
        RxChainStage("Balun/switch",  gain_db= -1.5, nf_db= 1.5, iip3_dbm= 40.0),
        RxChainStage("Passive mixer", gain_db= -7.0, nf_db= 7.5, iip3_dbm= 12.0),
        RxChainStage("BB LPF",        gain_db= -1.0, nf_db= 1.0, iip3_dbm= 30.0),
        RxChainStage("VGA",           gain_db= 20.0, nf_db= 5.0, iip3_dbm= 10.0),
    ]
    return ReceiverConfig(
        mcs=11,
        bw_mhz=80.0,
        stages=stages,
        iq_amp_imbalance_db=0.3,
        iq_phase_imbalance_deg=1.0,
        lo_ipn_dbc=-40.0,
        adc_bits=12,
        p_max_dbm=-50.0,
    )


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _db2lin(db: float) -> float:
    """dB noise-factor ratio: 10^(db/10)."""
    return 10.0 ** (db / 10.0)

def _db2pow(db: float) -> float:
    """Power gain ratio from dB: 10^(db/10)."""
    return 10.0 ** (db / 10.0)

def _lin2db(x: float) -> float:
    return 10.0 * np.log10(x)

def _dbm2mw(dbm: float) -> float:
    return 10.0 ** (dbm / 10.0)

def _mw2dbm(mw: float) -> float:
    return 10.0 * np.log10(mw)

def _rss_db(values_db: List[float]) -> float:
    """Root-sum-of-squares combination of dB power values."""
    total = sum(10.0 ** (v / 10.0) for v in values_db)
    return 10.0 * np.log10(total)

def _evm_pct(evm_db: float) -> float:
    """Convert EVM dB (power) to % (amplitude)."""
    return 10.0 ** (evm_db / 20.0) * 100.0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="WiFi 6 (802.11ax) direct conversion receiver link analysis",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--mcs",       type=int,   default=11,    help="MCS index (0–11)")
    p.add_argument("--bw",        type=float, default=80.0,  help="Signal bandwidth (MHz)")
    p.add_argument("--iq-amp",    type=float, default=0.3,   help="IQ amplitude imbalance (dB)")
    p.add_argument("--iq-phase",  type=float, default=1.0,   help="IQ phase imbalance (degrees)")
    p.add_argument("--lo-ipn",    type=float, default=-40.0, help="LO integrated phase noise (dBc)")
    p.add_argument("--adc-bits",  type=int,   default=12,    help="ADC resolution (bits)")
    p.add_argument("--p-max",     type=float, default=-50.0, help="Max input power for EVM spec (dBm)")
    p.add_argument("--plot",      action="store_true",       help="Save EVM vs power plot (PNG)")
    p.add_argument("--plot-file", default="evm_vs_power.png",help="Output filename for plot")
    p.add_argument("--derive",    action="store_true",       help="Show required spec derivation")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    cfg = build_default_receiver()
    cfg.mcs                    = args.mcs
    cfg.bw_mhz                 = args.bw
    cfg.iq_amp_imbalance_db    = args.iq_amp
    cfg.iq_phase_imbalance_deg = args.iq_phase
    cfg.lo_ipn_dbc             = args.lo_ipn
    cfg.adc_bits               = args.adc_bits
    cfg.p_max_dbm              = args.p_max

    analyzer = WiFi6RxAnalyzer(cfg)
    analyzer.print_report(derive=args.derive)

    if args.plot:
        plot_evm_vs_power(analyzer, outfile=args.plot_file)


if __name__ == "__main__":
    main()
