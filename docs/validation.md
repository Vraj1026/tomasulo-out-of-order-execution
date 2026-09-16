# Validation results

## Local macOS run

The Python suite and hazard demo were rerun on Vraj Patel's Mac. The shared
Terminal output reports 28 passing tests in 1.158 seconds and the expected
15-cycle demo result. An excerpt is recorded in
[evidence/macos-python-results.txt](evidence/macos-python-results.txt).
The default RTL regression also passed with Icarus Verilog: **208 cases and
20,407 cycles checked**. The shared Terminal output is transcribed in
[evidence/macos-rtl-default.txt](evidence/macos-rtl-default.txt), and the
[waveform screenshot](images/tomasulo_waveform.png) shows the hazard example
in VaporView. The screenshot is an unmodified capture supplied by Vraj.

The tiny RTL regression subsequently passed with Icarus Verilog: **208 cases
and 15,993 cycles checked**. Its shared Terminal output is transcribed in
[evidence/macos-rtl-tiny.txt](evidence/macos-rtl-tiny.txt).
Together, the two macOS RTL runs cover **416 cases and 36,400 checked cycles**.
Full tool versions were not captured in the shared output.

## Linux baseline

The initial automated regressions were run by Codex in a Linux development
environment with Python 3.12.14 and the PyPI Verilator distribution 5.48.0.
The binary identifies itself as `vUNKNOWN-built20260516-4e853d8`; both the
package and binary identifiers are retained here for reproducibility.
The table below describes those runs.

## Results

| Check | Observed result |
|---|---|
| Python unittest suite | 28 tests passed |
| Random architectural comparison within that suite | 500 seeds × 64 instructions; all seven operations; all final states matched |
| Default RTL profile | 208 cases passed; 20,407 cycles checked |
| Tiny RTL profile | 208 cases passed; 15,993 cycles checked |
| Total RTL | 416 cases; 36,400 cycles checked |
| HDL lint after width-warning cleanup | Passed without reported warnings under the invoked default lint settings |
| Python syntax compilation | Passed |
| Resource sweep | 20 configurations/program combinations matched the sequential oracle |
| HTML interaction checks | Passed for hazard and memory traces in jsdom 30.0.1 |

Default RTL uses three add/sub stations, two multiply stations, two-cycle
addition/subtraction, five-cycle multiplication, and one CDB. Tiny RTL uses one
station per group and one-cycle arithmetic, exercising full-station stalls,
same-cycle result/issue handling, and frequent station reuse.

Every RTL case checks issue timing; CDB valid, tag, and data on every cycle;
the final 32-register state; drain; pending-tag clearing; and reset with accepted
work in flight. The first case also generates an actual VCD, copied to
`demo/hazards.vcd`.

Machine-readable summaries are in `evidence/rtl-default.json`,
`evidence/rtl-tiny.json`, `evidence/experiments.csv`, and `evidence/viewer.json`.

## Main demo values

| Result | Expected and observed |
|---|---:|
| Instructions | 6 |
| Modeled cycles | 15 |
| IPC | 0.400 |
| R3 | 23 |
| R8 | 6 |
| R9 | 142 |
| R10 | 18 |
| R11 | 160 |

The test suite checks the hand-calculated issue/start/end/writeback table in
`project_guide.md`. The saved demo JSON and CSV contain the full observed trace.

## Scope and limits

- The Linux baseline used Verilator. The separate macOS default and tiny runs
  used Icarus Verilog. Hosted CI execution has not been verified here.
- The viewer's initialization, tables, buttons, slider, arrow keys, play/pause,
  events, and final drained state were checked in a DOM runtime. A real-browser
  screenshot/layout review was unavailable because the browser download failed.
- Python supports DIV/ADDI/LD/ST in addition to the shared arithmetic subset.
  Those operations are not implemented or claimed as tested in RTL.
- No hardware synthesis, FPGA deployment, static timing analysis, frequency,
  area, power, gate-level simulation, UVM coverage, or formal proof was performed.
- Random testing provides substantial exercised behavior, not exhaustive
  correctness or a percentage coverage claim. Input backpressure is exercised
  by filled stations; arbitrary upstream bubbles and all invalid-port scenarios
  are not exhaustively covered.
- The records here are local regression results. Check the repository Actions
  tab separately for hosted CI status.

## Reproduce

```bash
python3 -m unittest discover -s tests -v
python3 scripts/verify_rtl.py --backend verilator --seeds 200
python3 scripts/verify_rtl.py --backend verilator --profile tiny --seeds 200
python3 scripts/experiments.py
python3 -m tomasulo examples/hazards.asm --check --out build/hazards
python3 -m tomasulo examples/memory.asm --check --out build/memory
```

The project has no third-party Python dependencies. The HDL simulator and
DOM runtime are development tools; jsdom is not required to open the viewer
or run the model. See [local verification](local_verification.md) to record
additional runs and screenshots.
