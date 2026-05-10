Run a complete WiFi 6 direct conversion receiver link budget analysis using `tools/wifi6_rx_analyzer.py`.

Follow these steps:

1. **Ask the user for parameters** (or use defaults if they say "default" / provide no input):
   - MCS index (0–11, default **11** = 1024-QAM 5/6)
   - Signal bandwidth in MHz (20 / 40 / **80** / 160)
   - IQ amplitude imbalance in dB (default **0.08 dB**)
   - IQ phase error in degrees (default **0.50°**)
   - LO integrated phase noise in dBc (default **−42 dBc**)
   - ADC resolution in bits (default **12 bits**)
   - Maximum input power P_max in dBm (default **−50 dBm**)

2. **Build the command** from the parameters above:
   ```
   python3 tools/wifi6_rx_analyzer.py \
     --mcs <MCS> \
     --bw <BW> \
     --iq-amp <IQ_AMP> \
     --iq-phase <IQ_PHASE> \
     --lo-ipn <LO_IPN> \
     --adc-bits <ADC_BITS> \
     --p-max <P_MAX> \
     --derive \
     --plot
   ```

3. **Run the command** using the Bash tool and capture the output.

4. **Interpret and summarise the results** for the user, highlighting:
   - Whether the design **PASS** or **FAIL**
   - Cascaded NF and its margin vs the 4.5 dB limit
   - EVM floor and its margin vs the −35 dB limit
   - The dominant EVM contributor (IQ / LO PN / ADC / IP3)
   - Sensitivity and AGC range
   - Required minimum specs (IQ, IPN, IIP3, ADC ENOB) derived from the equal-budget allocation

5. **Show the generated plot** (`evm_vs_power.png`) by reading it with the Read tool so the user sees it inline.

6. **Offer next steps** — suggest which parameter to tighten if the design fails, or confirm the design margin if it passes.

> Note: The GUI version is at `tools/wifi6_rx_analyzer_gui.py` and can be launched with
> `python3 tools/wifi6_rx_analyzer_gui.py` for interactive slider-based exploration.
