import tkinter as tk
from tkinter import ttk
import math

class RFCalculatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Wi-Fi 6 (1024-QAM) 射频系统指标计算器")
        self.root.geometry("850x650")
        self.root.configure(bg="#f3f4f6")

        self.default_font = ("Segoe UI", 10)
        self.title_font = ("Segoe UI", 12, "bold")
        self.header_font = ("Segoe UI", 16, "bold")
        self.result_font = ("Consolas", 12, "bold")

        self.setup_variables()
        self.create_widgets()
        self.calculate_results()

    def setup_variables(self):
        self.var_lo_leakage = tk.DoubleVar(value=-60.0)
        self.var_impedance = tk.DoubleVar(value=50.0)
        self.var_mixer_gain = tk.DoubleVar(value=10.0)

        self.var_evm_target_pn = tk.DoubleVar(value=-40.0)

        self.var_pin = tk.DoubleVar(value=-50.0)
        self.var_im3_target = tk.DoubleVar(value=-40.0)

        self.var_bw = tk.DoubleVar(value=160.0)
        self.var_nf = tk.DoubleVar(value=4.5)
        self.var_max_input = tk.DoubleVar(value=-20.0)

        self.var_dc_offset = tk.StringVar()
        self.var_ipn = tk.StringVar()
        self.var_iip3 = tk.StringVar()
        self.var_noise_floor = tk.StringVar()
        self.var_agc_range = tk.StringVar()

        for var in [self.var_lo_leakage, self.var_impedance, self.var_mixer_gain,
                    self.var_evm_target_pn, self.var_pin, self.var_im3_target,
                    self.var_bw, self.var_nf, self.var_max_input]:
            var.trace_add("write", self.calculate_results)

    def calculate_results(self, *args):
        try:
            lo_leak = self.var_lo_leakage.get()
            imp = self.var_impedance.get()
            mix_gain = self.var_mixer_gain.get()

            evm_pn = self.var_evm_target_pn.get()

            pin = self.var_pin.get()
            im3 = self.var_im3_target.get()

            bw = self.var_bw.get()
            nf = self.var_nf.get()
            max_in = self.var_max_input.get()

            # DC Offset
            power_w = 10 ** ((lo_leak - 30) / 10)
            v_rms = math.sqrt(power_w * imp)
            v_peak = v_rms * math.sqrt(2)
            gain_linear = 10 ** (mix_gain / 20)
            dc_offset_mv = v_peak * gain_linear * 1000
            self.var_dc_offset.set(f"{dc_offset_mv:.3f}")

            # Phase noise
            evm_linear = 10 ** (evm_pn / 20)
            ipn_deg = evm_linear * (180 / math.pi)
            self.var_ipn.set(f"{ipn_deg:.3f}")

            # IIP3
            iip3 = pin - (im3 / 2)
            self.var_iip3.set(f"{iip3:.1f}")

            # Noise floor & AGC
            noise_floor = -174 + 10 * math.log10(bw * 1e6) + nf
            agc_range = max_in - noise_floor
            self.var_noise_floor.set(f"{noise_floor:.2f}")
            self.var_agc_range.set(f"{agc_range:.1f}")

        except Exception:
            pass

    def reset_defaults(self):
        self.var_lo_leakage.set(-60.0)
        self.var_impedance.set(50.0)
        self.var_mixer_gain.set(10.0)
        self.var_evm_target_pn.set(-40.0)
        self.var_pin.set(-50.0)
        self.var_im3_target.set(-40.0)
        self.var_bw.set(160.0)
        self.var_nf.set(4.5)
        self.var_max_input.set(-20.0)

    def create_widgets(self):
        header_frame = tk.Frame(self.root, bg="#1e293b", pady=15, padx=20)
        header_frame.pack(fill=tk.X)

        tk.Label(header_frame, text="Wi-Fi 6 (1024-QAM) 射频系统指标计算表", font=self.header_font, bg="#1e293b", fg="white").pack(side=tk.LEFT)
        btn_reset = tk.Button(header_frame, text="↻ 恢复默认", command=self.reset_defaults, bg="#334155", fg="white", relief=tk.FLAT, padx=10, cursor="hand2")
        btn_reset.pack(side=tk.RIGHT)

        main_frame = tk.Frame(self.root, bg="white", padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        left_frame = tk.Frame(main_frame, bg="white", width=400)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        tk.Label(left_frame, text="输入参数 (Input Parameters)", font=self.title_font, fg="#1e40af", bg="white").pack(anchor=tk.W, pady=(0, 10))

        canvas_l = tk.Canvas(left_frame, height=2, bg="#dbeafe", highlightthickness=0)
        canvas_l.pack(fill=tk.X, pady=(0, 10))

        self.add_section_title(left_frame, "1. 本振泄露与增益")
        self.add_input_row(left_frame, "LO Leakage (本振泄露)", self.var_lo_leakage, "dBm")
        self.add_input_row(left_frame, "系统阻抗", self.var_impedance, "Ω")
        self.add_input_row(left_frame, "混频器+TIA 转换增益", self.var_mixer_gain, "dB")

        self.add_section_title(left_frame, "2. 相位噪声分配预算")
        self.add_input_row(left_frame, "目标 EVM 贡献 (PN)", self.var_evm_target_pn, "dB")

        self.add_section_title(left_frame, "3. 系统非线性要求")
        self.add_input_row(left_frame, "评估输入功率 (Pin)", self.var_pin, "dBm")
        self.add_input_row(left_frame, "目标 IM3 产物相对值", self.var_im3_target, "dBc")

        self.add_section_title(left_frame, "4. 噪声与动态范围")
        self.add_input_row(left_frame, "信道带宽 (BW)", self.var_bw, "MHz")
        self.add_input_row(left_frame, "系统级联噪声系数 (NF)", self.var_nf, "dB")
        self.add_input_row(left_frame, "最大不饱和输入功率", self.var_max_input, "dBm")

        right_frame = tk.Frame(main_frame, bg="#f8fafc", width=400)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        right_inner = tk.Frame(right_frame, bg="#f8fafc", padx=15, pady=10)
        right_inner.pack(fill=tk.BOTH, expand=True)

        tk.Label(right_inner, text="自动计算结果 (Calculated Outputs)", font=self.title_font, fg="#166534", bg="#f8fafc").pack(anchor=tk.W, pady=(0, 10))

        canvas_r = tk.Canvas(right_inner, height=2, bg="#dcfce7", highlightthickness=0)
        canvas_r.pack(fill=tk.X, pady=(0, 10))

        self.add_section_title(right_inner, "1. 动态直流偏置预测", bg_color="#f8fafc")
        self.add_output_row(right_inner, "混频器端最坏 DC Offset", self.var_dc_offset, "mV", highlight=True)
        self.add_note(right_inner, "↑ 需通过 DCOC 电路在数字基带消除")

        self.add_section_title(right_inner, "2. PLL 相位噪声底线", bg_color="#f8fafc")
        self.add_output_row(right_inner, "最大允许积分相位噪声 (IPN)", self.var_ipn, "° rms", highlight=True)
        self.add_note(right_inner, "↑ 在给定的宽带积分区间内不可超标")

        self.add_section_title(right_inner, "3. 互调截点要求", bg_color="#f8fafc")
        self.add_output_row(right_inner, "系统级联最小 IIP3", self.var_iip3, "dBm", highlight=True)
        self.add_note(right_inner, "↑ 当输入达到上述 Pin 时，确保 IM3 不恶化 EVM")

        self.add_section_title(right_inner, "4. 噪声底线与AGC要求", bg_color="#f8fafc")
        self.add_output_row(right_inner, "系统热噪声底 (Noise Floor)", self.var_noise_floor, "dBm")
        self.add_output_row(right_inner, "理想 AGC 动态控制范围", self.var_agc_range, "dB", highlight=True)
        self.add_note(right_inner, "↑ 从噪声底到最大不饱和输入信号的范围跨度")

        tips_frame = tk.Frame(right_inner, bg="#eff6ff", bd=1, relief=tk.SOLID, highlightbackground="#bfdbfe")
        tips_frame.pack(fill=tk.X, pady=(30, 0), ipady=10, ipadx=10)
        tk.Label(tips_frame, text="架构师提示 (Architect Notes):", font=("Segoe UI", 10, "bold"), fg="#1e40af", bg="#eff6ff").pack(anchor=tk.W)
        tips_text = (
            "• 1024-QAM EVM target 通常设定在 -35dB。\n"
            "• 单一损伤预算(如 PN)必须设定在 -40dB 以下预留余量。\n"
            "• DC Offset 的计算假定同相混频的最坏情况。\n"
            "• 若 Mixer 增益过大，DC Offset 将导致后级瞬间饱和。"
        )
        tk.Label(tips_frame, text=tips_text, justify=tk.LEFT, font=("Segoe UI", 9), fg="#1e3a8a", bg="#eff6ff").pack(anchor=tk.W, pady=(5, 0))

    def add_section_title(self, parent, text, bg_color="white"):
        tk.Label(parent, text=text, font=("Segoe UI", 9, "bold"), fg="#94a3b8", bg=bg_color).pack(anchor=tk.W, pady=(10, 2))

    def add_input_row(self, parent, label_text, variable, unit_text):
        row = tk.Frame(parent, bg="white")
        row.pack(fill=tk.X, pady=2)

        tk.Label(row, text=label_text, width=25, anchor=tk.W, font=self.default_font, bg="white", fg="#334155").pack(side=tk.LEFT)
        tk.Label(row, text=unit_text, width=5, anchor=tk.W, font=self.default_font, bg="white", fg="#64748b").pack(side=tk.RIGHT)

        entry = tk.Entry(row, textvariable=variable, justify=tk.RIGHT, font=self.default_font, bg="#eff6ff", fg="#1e3a8a", relief=tk.FLAT, highlightbackground="#93c5fd", highlightthickness=1)
        entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)

    def add_output_row(self, parent, label_text, variable, unit_text, highlight=False):
        bg_color = "#ecfdf5" if highlight else "#f8fafc"
        row = tk.Frame(parent, bg=bg_color, pady=5)
        row.pack(fill=tk.X, pady=1)

        tk.Label(row, text=label_text, width=25, anchor=tk.W, font=self.default_font, bg=bg_color, fg="#1e293b").pack(side=tk.LEFT, padx=(5, 0))
        tk.Label(row, text=unit_text, width=6, anchor=tk.W, font=self.default_font, bg=bg_color, fg="#475569").pack(side=tk.RIGHT)

        lbl_res = tk.Label(row, textvariable=variable, font=self.result_font, bg=bg_color, fg="#15803d", anchor=tk.E)
        lbl_res.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)

    def add_note(self, parent, text):
        tk.Label(parent, text=text, font=("Segoe UI", 8), fg="#94a3b8", bg="#f8fafc").pack(anchor=tk.W, pady=(0, 5), padx=(5, 0))


if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    app = RFCalculatorApp(root)
    root.mainloop()
