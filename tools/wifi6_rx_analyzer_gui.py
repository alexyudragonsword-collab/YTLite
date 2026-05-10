#!/usr/bin/env python3
"""
WiFi 6 (802.11ax) Direct Conversion Receiver Link Analyzer — GUI
Single-file standalone.  Requires: numpy, matplotlib  (tkinter is stdlib).

Usage:
    python3 wifi6_rx_analyzer_gui.py
"""

import sys, math
import numpy as np

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure
    import matplotlib.gridspec as gridspec
except ImportError as e:
    print(f"Missing dependency: {e}\nRun:  pip install matplotlib numpy", file=sys.stderr)
    sys.exit(1)

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError as e:
    print(f"Missing dependency: {e}\nRun:  sudo apt install python3-tk  (or equivalent)",
          file=sys.stderr)
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
#  Constants
# ══════════════════════════════════════════════════════════════════════════════

WIFI6_MCS = {
    0:  (2,    1/2,   2.0,  -5.0,  "BPSK"),
    1:  (4,    1/2,   5.0,  -8.0,  "QPSK"),
    2:  (4,    3/4,   8.0,  -8.0,  "QPSK"),
    3:  (16,   1/2,  11.0, -13.0,  "16-QAM"),
    4:  (16,   3/4,  14.5, -13.0,  "16-QAM"),
    5:  (64,   2/3,  17.5, -19.0,  "64-QAM"),
    6:  (64,   3/4,  19.5, -19.0,  "64-QAM"),
    7:  (64,   5/6,  21.0, -19.0,  "64-QAM"),
    8:  (256,  3/4,  24.0, -25.0,  "256-QAM"),
    9:  (256,  5/6,  26.5, -25.0,  "256-QAM"),
    10: (1024, 3/4,  29.5, -35.0,  "1024-QAM"),
    11: (1024, 5/6,  32.5, -35.0,  "1024-QAM"),
}
WIFI6_BW = {
    20:  {"bw_hz": 20e6,  "n_sc": 234},
    40:  {"bw_hz": 40e6,  "n_sc": 468},
    80:  {"bw_hz": 80e6,  "n_sc": 980},
    160: {"bw_hz": 160e6, "n_sc": 1960},
}
KT_DBM_HZ    = -174.0
OFDM_PAPR_DB = 10.0
NF_LIMIT_DB  = 4.5
EVM_LIMIT_DB = -35.0

# Default receiver chain: (name, gain_db, nf_db, iip3_dbm)
DEFAULT_CHAIN = [
    ("LNA",           15.0,  1.5, -15.0),
    ("Balun/switch",  -1.5,  1.5,  40.0),
    ("Passive mixer", -7.0,  7.5,  12.0),
    ("BB LPF",        -1.0,  1.0,  30.0),
    ("VGA",           20.0,  5.0,  10.0),
]

# ══════════════════════════════════════════════════════════════════════════════
#  RF Analysis Engine
# ══════════════════════════════════════════════════════════════════════════════

def _p(db):   return 10 ** (db / 10)
def _db(x):   return 10 * math.log10(max(float(x), 1e-30))
def _mw(dbm): return 10 ** (dbm / 10)
def _rss(vs): return _db(sum(_p(v) for v in vs))
def _pct(e):  return 10 ** (e / 20) * 100


def calc_nf(chain):
    f = _p(chain[0][2]); g = _p(chain[0][1])
    for _, g_, nf_, _ in chain[1:]:
        f += (_p(nf_) - 1) / g
        g *= _p(g_)
    return _db(f)


def calc_iip3(chain):
    inv = 0.0; g = 1.0
    for _, g_, _, i3 in chain:
        inv += g / _mw(i3)
        g   *= _p(g_)
    return _db(1 / inv) if inv > 0 else 100.0


def evm_iq(amp_db, phase_deg):
    e = 10 ** (amp_db / 20) - 1
    p = math.radians(phase_deg)
    sq = (e**2 + p**2) / 4
    return (10 * math.log10(sq), -10 * math.log10(sq)) if sq > 0 else (-100.0, 100.0)


def evm_nl(p_in, iip3):    return 2 * (p_in - iip3) + 4.5
def evm_th(p_in, nf, bw):  return -(p_in - (KT_DBM_HZ + 10 * math.log10(bw) + nf))


def run_analysis(mcs, bw_mhz, iq_a, iq_p, ipn, adc_b, pmax):
    mr  = WIFI6_MCS[mcs]
    br  = WIFI6_BW[bw_mhz]
    bw  = br["bw_hz"]
    snr = mr[2]

    nf   = calc_nf(DEFAULT_CHAIN)
    iip3 = calc_iip3(DEFAULT_CHAIN)
    sens = KT_DBM_HZ + 10 * math.log10(bw) + nf + snr

    e_iq, irr = evm_iq(iq_a, iq_p)
    e_pn  = float(ipn)
    e_adc = -(6.02 * adc_b + 1.76 - OFDM_PAPR_DB)
    e_nl  = evm_nl(pmax, iip3)
    e_th  = evm_th(pmax, nf, bw)

    e_floor = _rss([e_iq, e_pn, e_adc, e_nl])
    e_tot   = _rss([e_iq, e_pn, e_adc, e_nl, e_th])

    per  = _db(_p(EVM_LIMIT_DB) / 4)
    each = 10 ** (per / 20) * math.sqrt(2)

    return dict(
        mcs=mcs, mr=mr, bw_mhz=bw_mhz, bw=bw, n_sc=br["n_sc"], snr=snr,
        nf=nf, iip3=iip3, sens=sens, agc=pmax - sens,
        nfloor=KT_DBM_HZ + 10 * math.log10(bw) + nf,
        e_th=e_th, e_iq=e_iq, e_pn=e_pn, e_adc=e_adc, e_nl=e_nl,
        e_floor=e_floor, e_tot=e_tot, irr=irr,
        nf_ok=nf <= NF_LIMIT_DB,
        evm_ok=e_floor <= EVM_LIMIT_DB,
        nf_m=NF_LIMIT_DB - nf,
        evm_m=EVM_LIMIT_DB - e_floor,
        pmax=pmax, iq_a=iq_a, iq_p=iq_p, ipn=ipn, adc_b=adc_b,
        specs=dict(
            per=per,
            iq_a_max=20 * math.log10(1 + each),
            iq_p_max=math.degrees(each),
            irr_min=-per, ipn_max=per,
            enob=math.ceil((-per - 1.76 + OFDM_PAPR_DB) / 6.02),
            iip3_min=pmax - (per - 4.5) / 2,
            sens_lim=KT_DBM_HZ + 10 * math.log10(bw) + NF_LIMIT_DB + snr,
            agc_min=pmax - (KT_DBM_HZ + 10 * math.log10(bw) + NF_LIMIT_DB + snr),
        ),
    )


def make_curves(r):
    ps = np.linspace(r["sens"] - 8, r["pmax"] + 12, 500)
    ef, et = [], []
    for p in ps:
        nl = evm_nl(p, r["iip3"])
        th = evm_th(p, r["nf"], r["bw"])
        ef.append(_rss([r["e_iq"], r["e_pn"], r["e_adc"], nl]))
        et.append(_rss([r["e_iq"], r["e_pn"], r["e_adc"], nl, th]))
    return ps, np.array(et), np.array(ef)


def build_report(r):
    s = r["specs"]
    MOD = {2: "BPSK", 4: "QPSK", 16: "16-QAM",
           64: "64-QAM", 256: "256-QAM", 1024: "1024-QAM"}
    sep = "═" * 60
    def L(lbl, val, unit="", flag=None):
        f = ""
        if flag is True:   f = "  [PASS]"
        elif flag is False: f = "  [FAIL]"
        return f"  {lbl:<26}{val}{unit}{f}"

    lines = [
        "SYSTEM TARGET", sep,
        L("MCS:", f"MCS{r['mcs']}  {MOD.get(r['mr'][0],'?')}  rate {r['mr'][1]:.3g}"),
        L("Bandwidth:", f"{r['bw_mhz']} MHz  •  {r['n_sc']} data SCs"),
        L("Required SNR:", f"{r['snr']:.1f}", " dB"),
        L("EVM limit:", f"{EVM_LIMIT_DB:.0f} dB  ({_pct(EVM_LIMIT_DB):.2f}%)"),
        "",
        "RECEIVER CHAIN", sep,
        f"  {'Stage':<18} {'Gain':>5}  {'NF':>5}  {'IIP3':>7}  {'OIP3':>7}",
        "  " + "─" * 48,
    ]
    for nm, g, nf_, i3 in DEFAULT_CHAIN:
        lines.append(f"  {nm:<18} {g:>5.1f}  {nf_:>5.1f}  {i3:>7.1f}  {i3+g:>7.1f}")
    lines += [
        "  " + "─" * 48,
        f"  {'CASCADED':<18} {sum(c[1] for c in DEFAULT_CHAIN):>5.1f}  {r['nf']:>5.2f}"
        f"  {r['iip3']:>7.1f}",
        L("Noise floor:", f"{r['nfloor']:.1f}", " dBm"),
        L("Sensitivity:", f"{r['sens']:.1f}", " dBm"),
        L("NF margin:", f"{r['nf_m']:+.2f}", " dB", r["nf_ok"]),
        "",
        f"EVM BUDGET  (P_in = {r['pmax']:.0f} dBm)", sep,
        f"  {'Contributor':<22} {'EVM (dB)':>9} {'EVM (%)':>9}",
        "  " + "─" * 44,
        f"  {'Thermal noise':<22} {r['e_th']:>9.1f} {_pct(r['e_th']):>9.3f}",
        f"  {'IQ mismatch':<22} {r['e_iq']:>9.1f} {_pct(r['e_iq']):>9.3f}",
        f"  {'LO phase noise':<22} {r['e_pn']:>9.1f} {_pct(r['e_pn']):>9.3f}",
        f"  {'ADC quantization':<22} {r['e_adc']:>9.1f} {_pct(r['e_adc']):>9.3f}",
        f"  {'IP3 nonlinearity':<22} {r['e_nl']:>9.1f} {_pct(r['e_nl']):>9.3f}",
        "  " + "═" * 44,
        f"  {'EVM floor (no thermal)':<22} {r['e_floor']:>9.1f} {_pct(r['e_floor']):>9.3f}",
        f"  {'Total EVM':<22} {r['e_tot']:>9.1f} {_pct(r['e_tot']):>9.3f}",
        L("EVM floor margin:", f"{r['evm_m']:+.2f}", " dB", r["evm_ok"]),
        "",
        "IMPAIRMENT DETAILS", sep,
        L("IQ amp imbalance:", f"{r['iq_a']:.3f}", " dB"),
        L("IQ phase error:", f"{r['iq_p']:.2f}", "°"),
        L("IRR:", f"{r['irr']:.1f}", " dB"),
        L("LO IPN:", f"{r['ipn']:.1f}", " dBc  (conservative)"),
        L("ADC:", f"{r['adc_b']} bits  SNR≈{6.02*r['adc_b']+1.76-OFDM_PAPR_DB:.1f} dB"),
        L("Cascaded IIP3:", f"{r['iip3']:.1f}", " dBm"),
        L("IM3 @ P_max:", f"{2*(r['pmax']-r['iip3']):.1f}", " dBc  (two-tone)"),
        "",
        "AGC RANGE", sep,
        L("Sensitivity:", f"{r['sens']:.1f}", " dBm"),
        L("Max input (P_max):", f"{r['pmax']:.0f}", " dBm"),
        L("AGC range:", f"{r['agc']:.1f}", " dB"),
        "",
        "REQUIRED SPECIFICATIONS  (EVM floor < -35 dB, equal 4-way budget)", sep,
        L("Per contributor:", f"{s['per']:.1f}", " dB"),
        L("IQ amp imb. max:", f"{s['iq_a_max']:.3f}", " dB"),
        L("IQ phase max:", f"{s['iq_p_max']:.3f}", "°"),
        L("IRR min:", f"{s['irr_min']:.1f}", " dB"),
        L("LO IPN max:", f"{s['ipn_max']:.1f}", " dBc"),
        L("ADC ENOB min:", f"{s['enob']}", " bits"),
        L("IIP3 min:", f"{s['iip3_min']:.1f}", f" dBm  @ {r['pmax']:.0f} dBm"),
        L("NF max:", f"{NF_LIMIT_DB:.1f}", " dB"),
        L("Sensitivity:", f"{s['sens_lim']:.1f}", " dBm  (@ NF limit)"),
        L("AGC range min:", f"{s['agc_min']:.1f}", " dB"),
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════════════════════════════════════════

class WiFi6GUI:
    # Colour palette
    C_BG     = "#f8fafc"
    C_PANEL  = "#f1f5f9"
    C_BORDER = "#cbd5e1"
    C_TEXT   = "#1e293b"
    C_DIM    = "#64748b"
    C_PASS   = "#16a34a"
    C_FAIL   = "#dc2626"
    C_BLUE   = "#2563eb"
    # Plot dark theme
    PL_BG    = "#0d1117"
    PL_AX    = "#161b22"
    PL_TEXT  = "#c9d1d9"
    PL_GRID  = "#21262d"

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("WiFi 6 (802.11ax)  Receiver Link Analyzer")
        root.geometry("1320x800")
        root.minsize(960, 640)
        root.configure(bg=self.C_BG)

        self._result = None
        self._after_id = None

        # Tk variables
        self.v_mcs   = tk.IntVar(value=11)
        self.v_bw    = tk.IntVar(value=80)
        self.v_iq_a  = tk.DoubleVar(value=0.08)
        self.v_iq_p  = tk.DoubleVar(value=0.50)
        self.v_ipn   = tk.DoubleVar(value=-42.0)
        self.v_adc   = tk.IntVar(value=12)
        self.v_pmax  = tk.DoubleVar(value=-50.0)

        self._build_ui()

        # Wire all variables → debounced analysis
        for v in (self.v_mcs, self.v_bw, self.v_iq_a, self.v_iq_p,
                  self.v_ipn, self.v_adc, self.v_pmax):
            v.trace_add("write", self._schedule_analyze)

        self._analyze()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg="#0f172a", height=46)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(hdr, text="WiFi 6 (802.11ax)  Direct Conversion Receiver Link Analyzer",
                 bg="#0f172a", fg="white",
                 font=("Helvetica", 13, "bold")).pack(side=tk.LEFT, padx=16, pady=11)
        self.lbl_header_status = tk.Label(hdr, text="", bg="#0f172a",
                                          font=("Helvetica", 11, "bold"))
        self.lbl_header_status.pack(side=tk.RIGHT, padx=16)

        # Main horizontal pane
        h = tk.PanedWindow(self.root, orient=tk.HORIZONTAL,
                           sashwidth=6, sashrelief="flat",
                           bg=self.C_BORDER, bd=0)
        h.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(h, bg=self.C_PANEL, width=295)
        left.pack_propagate(False)
        h.add(left, minsize=250)

        right = tk.Frame(h, bg=self.C_BG)
        h.add(right, minsize=600)

        self._build_left(left)
        self._build_right(right)

    def _build_left(self, parent):
        # Scrollable canvas inside left panel
        cv = tk.Canvas(parent, bg=self.C_PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=cv.yview)
        inner = tk.Frame(cv, bg=self.C_PANEL)
        inner.bind("<Configure>",
                   lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        cv.bind("<MouseWheel>",
                lambda e: cv.yview_scroll(int(-e.delta / 120), "units"))
        self._fill_params(inner)

    def _section(self, parent, title):
        tk.Frame(parent, bg=self.C_PANEL, height=6).pack()
        tk.Label(parent, text=title.upper(), bg=self.C_PANEL,
                 fg=self.C_BLUE, font=("Helvetica", 9, "bold")).pack(
            anchor="w", padx=12, pady=(4, 0))
        tk.Frame(parent, bg=self.C_BORDER, height=1).pack(fill=tk.X, padx=10)

    def _slider_row(self, parent, label, var, lo, hi, step, unit, fmt=".2f"):
        """Label + Scale (slider) + live value label."""
        fr = tk.Frame(parent, bg=self.C_PANEL)
        fr.pack(fill=tk.X, padx=10, pady=(3, 0))

        top = tk.Frame(fr, bg=self.C_PANEL)
        top.pack(fill=tk.X)
        tk.Label(top, text=label, bg=self.C_PANEL, fg=self.C_TEXT,
                 font=("Helvetica", 9), width=14, anchor="w").pack(side=tk.LEFT)

        val_lbl = tk.Label(top, bg=self.C_PANEL, fg=self.C_TEXT,
                           font=("Helvetica", 9, "bold"), width=9, anchor="e")
        val_lbl.pack(side=tk.RIGHT)
        tk.Label(top, text=unit, bg=self.C_PANEL, fg=self.C_DIM,
                 font=("Helvetica", 8)).pack(side=tk.RIGHT)

        def refresh(*_):
            try:
                val_lbl.config(text=f"{var.get():{fmt}}")
            except tk.TclError:
                pass

        scale = tk.Scale(fr, variable=var, from_=lo, to=hi,
                         resolution=step, orient=tk.HORIZONTAL,
                         showvalue=False, bg=self.C_PANEL, fg=self.C_DIM,
                         troughcolor="#94a3b8", activebackground=self.C_BLUE,
                         highlightthickness=0, relief="flat", bd=0,
                         sliderlength=14, sliderrelief="flat")
        scale.pack(fill=tk.X, pady=(1, 4))
        var.trace_add("write", refresh)
        refresh()
        return scale

    def _combo_row(self, parent, label, var, values, width=5):
        fr = tk.Frame(parent, bg=self.C_PANEL)
        fr.pack(fill=tk.X, padx=10, pady=(3, 1))
        tk.Label(fr, text=label, bg=self.C_PANEL, fg=self.C_TEXT,
                 font=("Helvetica", 9), width=14, anchor="w").pack(side=tk.LEFT)
        cb = ttk.Combobox(fr, textvariable=var, values=values,
                          width=width, state="readonly",
                          font=("Helvetica", 9))
        cb.pack(side=tk.LEFT)
        return cb

    def _fill_params(self, f):
        self._section(f, "System Parameters")
        self._combo_row(f, "MCS index", self.v_mcs, list(range(12)), width=4)
        # MCS description label
        self.lbl_mcs_desc = tk.Label(f, bg=self.C_PANEL, fg=self.C_DIM,
                                     font=("Helvetica", 8))
        self.lbl_mcs_desc.pack(anchor="w", padx=24)
        self.v_mcs.trace_add("write", self._update_mcs_label)
        self._update_mcs_label()

        self._combo_row(f, "Bandwidth", self.v_bw, [20, 40, 80, 160], width=5)
        tk.Label(f, text="MHz", bg=self.C_PANEL, fg=self.C_DIM,
                 font=("Helvetica", 8)).pack(anchor="w", padx=24)

        self._section(f, "IQ Mismatch")
        self._slider_row(f, "Amp imbalance", self.v_iq_a,
                         0.0, 3.0, 0.01, "dB", ".3f")
        self._slider_row(f, "Phase error",   self.v_iq_p,
                         0.0, 10.0, 0.05, "deg", ".2f")

        self._section(f, "LO Phase Noise")
        self._slider_row(f, "IPN",  self.v_ipn,
                         -65.0, -20.0, 0.5, "dBc", ".1f")

        self._section(f, "ADC")
        self._slider_row(f, "Bits", self.v_adc,
                         6, 16, 1, "bits", ".0f")

        self._section(f, "Input Range")
        self._slider_row(f, "P_max", self.v_pmax,
                         -80.0, -10.0, 1.0, "dBm", ".0f")

        # Analyze button
        tk.Frame(f, bg=self.C_PANEL, height=10).pack()
        tk.Button(f, text="▶  Run Analysis", command=self._analyze,
                  bg=self.C_BLUE, fg="white",
                  font=("Helvetica", 10, "bold"),
                  relief="flat", padx=0, pady=7,
                  activebackground="#1d4ed8",
                  cursor="hand2").pack(fill=tk.X, padx=12)

        # Status summary
        self._section(f, "Status")
        self.lbl_nf   = tk.Label(f, bg=self.C_PANEL, font=("Helvetica", 9))
        self.lbl_nf.pack(anchor="w", padx=16, pady=1)
        self.lbl_evm  = tk.Label(f, bg=self.C_PANEL, font=("Helvetica", 9))
        self.lbl_evm.pack(anchor="w", padx=16, pady=1)
        self.lbl_sens = tk.Label(f, bg=self.C_PANEL, fg=self.C_DIM,
                                 font=("Helvetica", 9))
        self.lbl_sens.pack(anchor="w", padx=16, pady=1)
        self.lbl_agc  = tk.Label(f, bg=self.C_PANEL, fg=self.C_DIM,
                                 font=("Helvetica", 9))
        self.lbl_agc.pack(anchor="w", padx=16, pady=1)
        self.lbl_iip3 = tk.Label(f, bg=self.C_PANEL, fg=self.C_DIM,
                                 font=("Helvetica", 9))
        self.lbl_iip3.pack(anchor="w", padx=16, pady=1)

        tk.Frame(f, bg=self.C_PANEL, height=8).pack()
        self.lbl_verdict = tk.Label(f, bg=self.C_PANEL,
                                    font=("Helvetica", 13, "bold"))
        self.lbl_verdict.pack(anchor="w", padx=12, pady=(0, 12))

        # Receiver chain (fixed, informational)
        self._section(f, "Receiver Chain  (fixed)")
        for nm, g, nf_, i3 in DEFAULT_CHAIN:
            tk.Label(f, text=f"  {nm:<16} G={g:+.0f}  NF={nf_:.1f}  IIP3={i3:.0f}",
                     bg=self.C_PANEL, fg=self.C_DIM,
                     font=("Courier", 8)).pack(anchor="w", padx=10)
        tk.Frame(f, bg=self.C_PANEL, height=12).pack()

    def _build_right(self, parent):
        v = tk.PanedWindow(parent, orient=tk.VERTICAL,
                           sashwidth=6, sashrelief="flat",
                           bg=self.C_BORDER, bd=0)
        v.pack(fill=tk.BOTH, expand=True)

        plot_frame = tk.Frame(v, bg=self.PL_BG)
        v.add(plot_frame, minsize=280)

        text_frame = tk.Frame(v, bg=self.C_BG)
        v.add(text_frame, minsize=120)

        self._build_plot(plot_frame)
        self._build_text(text_frame)

        # Set initial split: ~65% plot / 35% text
        v.after(150, lambda: v.sash_place(0, 0, 490))

    def _build_plot(self, parent):
        self.fig = Figure(facecolor=self.PL_BG)
        gs = gridspec.GridSpec(
            2, 1, figure=self.fig,
            height_ratios=[1.9, 1.0],
            hspace=0.52,
            left=0.07, right=0.97, top=0.94, bottom=0.07,
        )
        self.ax1 = self.fig.add_subplot(gs[0])
        self.ax2 = self.fig.add_subplot(gs[1])
        for ax in (self.ax1, self.ax2):
            ax.set_facecolor(self.PL_AX)

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        tb_frame = tk.Frame(parent, bg="#1e293b")
        tb_frame.pack(fill=tk.X)
        tb = NavigationToolbar2Tk(self.canvas, tb_frame)
        tb.config(background="#1e293b")
        for child in tb.winfo_children():
            try: child.config(background="#1e293b")
            except tk.TclError: pass
        tb.update()

    def _build_text(self, parent):
        hdr = tk.Frame(parent, bg=self.C_PANEL)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="  Link Budget Report",
                 bg=self.C_PANEL, fg=self.C_TEXT,
                 font=("Helvetica", 9, "bold")).pack(side=tk.LEFT, pady=3)

        body = tk.Frame(parent)
        body.pack(fill=tk.BOTH, expand=True)

        self.txt = tk.Text(body,
                           font=("Courier", 9),
                           bg="#161b22", fg="#c9d1d9",
                           insertbackground="#c9d1d9",
                           relief="flat", padx=10, pady=8,
                           wrap="none", state="disabled")
        sb_y = ttk.Scrollbar(body, orient="vertical",   command=self.txt.yview)
        sb_x = ttk.Scrollbar(body, orient="horizontal", command=self.txt.xview)
        self.txt.config(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        sb_y.pack(side=tk.RIGHT,  fill=tk.Y)
        sb_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _update_mcs_label(self, *_):
        try:
            m = self.v_mcs.get()
            mr = WIFI6_MCS[m]
            self.lbl_mcs_desc.config(
                text=f"{mr[4]}  r={mr[1]:.3g}  SNR≥{mr[2]:.1f} dB")
        except (tk.TclError, KeyError):
            pass

    def _schedule_analyze(self, *_):
        """Debounce: wait 120 ms after last change before re-running."""
        if self._after_id:
            self.root.after_cancel(self._after_id)
        self._after_id = self.root.after(120, self._analyze)

    def _analyze(self):
        self._after_id = None
        try:
            mcs  = self.v_mcs.get()
            bw   = self.v_bw.get()
            iq_a = float(self.v_iq_a.get())
            iq_p = float(self.v_iq_p.get())
            ipn  = float(self.v_ipn.get())
            adc  = int(self.v_adc.get())
            pmax = float(self.v_pmax.get())
        except (tk.TclError, ValueError):
            return

        r = run_analysis(mcs, bw, iq_a, iq_p, ipn, adc, pmax)
        self._result = r
        self._update_status(r)
        self._update_plot(r)
        self._update_text(r)

    def _update_status(self, r):
        cn = self.C_PASS if r["nf_ok"]  else self.C_FAIL
        ce = self.C_PASS if r["evm_ok"] else self.C_FAIL
        ok = r["nf_ok"] and r["evm_ok"]
        ca = self.C_PASS if ok else self.C_FAIL

        self.lbl_nf.config(
            text=f"NF = {r['nf']:.2f} dB  ({r['nf_m']:+.1f} dB)", fg=cn)
        self.lbl_evm.config(
            text=f"EVM floor = {r['e_floor']:.1f} dB  ({r['evm_m']:+.1f} dB)", fg=ce)
        self.lbl_sens.config(text=f"Sensitivity : {r['sens']:.1f} dBm")
        self.lbl_agc.config( text=f"AGC range   : {r['agc']:.1f} dB")
        self.lbl_iip3.config(text=f"Cascaded IIP3 : {r['iip3']:.1f} dBm")

        verdict = "●  PASS  ✓" if ok else "●  FAIL  ✗"
        self.lbl_verdict.config(text=verdict, fg=ca)
        self.lbl_header_status.config(
            text=verdict,
            fg=ca)

    def _update_plot(self, r):
        powers, e_tot, e_floor = make_curves(r)

        # ── Top subplot: EVM vs input power ──────────────────────────────────
        ax = self.ax1
        ax.clear()
        ax.set_facecolor(self.PL_AX)

        ax.plot(powers, e_tot,   color="#60a5fa", lw=2.0,
                label="EVM total  (incl. thermal)")
        ax.plot(powers, e_floor, color="#f87171", lw=2.0, ls="--",
                label="EVM floor  (distortion only)")
        ax.axhline(EVM_LIMIT_DB, color="#4ade80", lw=1.4, ls=":",
                   label=f"Target  {EVM_LIMIT_DB:.0f} dB")
        ax.axvline(r["sens"],  color="#a78bfa", lw=1.2, ls="-.",
                   label=f"Sensitivity  {r['sens']:.1f} dBm")
        ax.axvline(r["pmax"],  color="#fb923c", lw=1.2, ls="-.",
                   label=f"P_max  {r['pmax']:.0f} dBm")
        ax.axvspan(r["sens"], r["pmax"], alpha=0.07, color="#60a5fa",
                   label="Operating range")

        # Annotate floor
        c_ann = "#4ade80" if r["evm_ok"] else "#f87171"
        mid_x = (r["sens"] + r["pmax"]) / 2
        ax.annotate(
            f"floor = {r['e_floor']:.1f} dB   margin {r['evm_m']:+.1f} dB",
            xy=(mid_x, r["e_floor"]),
            xytext=(mid_x, r["e_floor"] + 2.5),
            ha="center", color=c_ann, fontsize=8,
            arrowprops=dict(arrowstyle="->", color=c_ann, lw=0.8),
        )

        ax.invert_xaxis()
        ax.set_xlabel("Input Power (dBm)", color=self.PL_TEXT, fontsize=9)
        ax.set_ylabel("EVM (dB)",          color=self.PL_TEXT, fontsize=9)
        ax.set_title(
            f"MCS{r['mcs']}  {r['bw_mhz']} MHz  —  EVM vs. Input Power"
            f"     NF={r['nf']:.2f} dB   IIP3={r['iip3']:.1f} dBm"
            f"   IPN={r['ipn']:.0f} dBc",
            color=self.PL_TEXT, fontsize=9, pad=5,
        )
        ax.tick_params(colors=self.PL_TEXT, labelsize=8)
        for sp in ax.spines.values(): sp.set_edgecolor(self.PL_GRID)
        ax.legend(fontsize=8, loc="lower right",
                  facecolor="#1e293b", edgecolor=self.PL_GRID,
                  labelcolor=self.PL_TEXT, framealpha=0.9)
        ax.grid(True, color=self.PL_GRID, alpha=0.8, ls="--", lw=0.5)

        # ── Bottom subplot: EVM contributor bar chart ─────────────────────────
        ax2 = self.ax2
        ax2.clear()
        ax2.set_facecolor(self.PL_AX)

        labels = ["Thermal", "IQ mismatch", "LO PN", "ADC quant.", "IP3 NL"]
        vals   = [r["e_th"], r["e_iq"], r["e_pn"], r["e_adc"], r["e_nl"]]
        colors = ["#60a5fa", "#f472b6", "#fb923c", "#a78bfa", "#34d399"]

        bars = ax2.barh(labels, vals, color=colors, alpha=0.85, height=0.55)
        ax2.axvline(EVM_LIMIT_DB, color="#4ade80", lw=1.4, ls=":",
                    label=f"Target {EVM_LIMIT_DB:.0f} dB")

        x_lim = ax2.get_xlim()
        for bar, val in zip(bars, vals):
            ax2.text(val - 0.5, bar.get_y() + bar.get_height() / 2,
                     f"{val:.1f} dB", va="center", ha="right",
                     color="#1e293b", fontsize=7.5, fontweight="bold")

        ax2.set_xlabel("EVM (dB)", color=self.PL_TEXT, fontsize=9)
        ax2.set_title(
            f"EVM Contributors  @  P_max = {r['pmax']:.0f} dBm",
            color=self.PL_TEXT, fontsize=9, pad=4,
        )
        ax2.tick_params(colors=self.PL_TEXT, labelsize=8)
        for sp in ax2.spines.values(): sp.set_edgecolor(self.PL_GRID)
        ax2.legend(fontsize=8, loc="lower right",
                   facecolor="#1e293b", edgecolor=self.PL_GRID,
                   labelcolor=self.PL_TEXT)
        ax2.grid(True, color=self.PL_GRID, alpha=0.8, axis="x",
                 ls="--", lw=0.5)

        self.fig.set_facecolor(self.PL_BG)
        self.canvas.draw_idle()

    def _update_text(self, r):
        self.txt.config(state="normal")
        self.txt.delete("1.0", tk.END)

        # colour-tagged PASS / FAIL
        self.txt.tag_config("pass", foreground="#4ade80")
        self.txt.tag_config("fail", foreground="#f87171")
        self.txt.tag_config("hdr",  foreground="#93c5fd", font=("Courier", 9, "bold"))
        self.txt.tag_config("dim",  foreground="#64748b")

        report_text = build_report(r)
        for line in report_text.splitlines(keepends=True):
            if line.strip().startswith("═") or line.strip().startswith("─"):
                self.txt.insert(tk.END, line, "dim")
            elif "[PASS]" in line:
                pre, _, _ = line.partition("[PASS]")
                self.txt.insert(tk.END, pre)
                self.txt.insert(tk.END, "[PASS]\n", "pass")
            elif "[FAIL]" in line:
                pre, _, _ = line.partition("[FAIL]")
                self.txt.insert(tk.END, pre)
                self.txt.insert(tk.END, "[FAIL]\n", "fail")
            elif line.isupper() or (line.strip() and line.strip()[0].isupper()
                                    and line.strip().endswith("\n") is False
                                    and ":" not in line):
                self.txt.insert(tk.END, line, "hdr")
            else:
                self.txt.insert(tk.END, line)

        self.txt.config(state="disabled")
        self.txt.see("1.0")


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except tk.TclError:
        pass
    WiFi6GUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
