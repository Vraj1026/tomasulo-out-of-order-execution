# Local verification

Run these commands from the project root, where `run.sh` and `README.md` are
located. Generated outputs go into `build/`.

## 1. Python tests and trace

```bash
python3 --version
bash run.sh
```

A successful run reports 28 passing tests and a six-instruction example taking
15 modeled cycles. The final values include R8=6, R9=142, R10=18, and R11=160.

On macOS, open the trace with:

```bash
open build/hazards/trace.html
```

Move the cycle slider to 7. The event list should include I1 broadcasting 42,
while R8 still contains 6. This is the useful WAW/RAW interaction to inspect.

## 2. RTL regression

Check the installed simulator version:

```bash
iverilog -V
```

If Icarus is missing and Homebrew is installed, install the
[official Homebrew package](https://formulae.brew.sh/formula/icarus-verilog):

```bash
brew install icarus-verilog
```

Run the default and minimal-resource profiles:

```bash
python3 scripts/verify_rtl.py --backend iverilog
python3 scripts/verify_rtl.py --backend iverilog --profile tiny
```

Each profile contains 208 cases. A successful run prints `PASS` and writes a
`validation.json` summary. The expected checked-cycle totals are 20,407 for the
default profile and 15,993 for the tiny profile. These expectations come from
the reference model; record the actual simulator output before reporting a pass.

Verilator can be used instead by selecting `--backend verilator`. Its build
requires a C++ compiler and `make` in addition to Verilator.

If compilation fails, inspect `build/rtl-default/compile.log` (or the matching
profile's directory). If simulation fails, preserve the printed error and any
`failed.asm` file. Do not treat generated files alone as evidence of a pass.

## 3. Capture results

Record the operating system, Python version, and HDL simulator version with
any new regression results. Keep the new evidence separate from the existing
Linux baseline under `docs/evidence/`.

For README images, capture:

- The trace viewer at cycle 7, showing the timeline, CDB event, and register R8.
- The terminal's actual RTL pass summary, or a waveform from the new local run.

On macOS, Command + Shift + 4 captures a selected region. Frame the project
output so unrelated windows are excluded. Suggested filenames are
`docs/images/execution_trace.png` and `docs/images/rtl_regression.png`.
Add image links to the README after those files exist.

The actual local RTL waveform is `build/rtl-default/hazards.vcd`. Open it in
VaporView or another VCD viewer, and inspect `issue_valid`, `issue_ready`,
`cdb_valid`, `cdb_tag`, `cdb_data`, and `idle`. Reset and register initialization
precede algorithm cycle 1.

## 4. Try a resource change

```bash
python3 scripts/experiments.py
```

Compare `parallel` with one and two compute units per group. The recorded
baseline changes from 12 to 10 cycles. Check that the final registers still
match the sequential reference and identify which instructions start earlier.
