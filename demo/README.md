# Ready-to-open demonstrations

Open `trace.html` for the six-instruction RAW/WAR/WAW example. Open
`memory/trace.html` for the ordered memory example. Both files work offline and
contain their own trace data and interface code.

`trace.json` contains every saved cycle. `timeline.csv` lists instruction issue,
execution start/end, and writeback cycles. `hazards.vcd` is the actual waveform
from the SystemVerilog default-profile testbench.

Regenerate the software trace from the project root with:

```bash
python3 -m tomasulo examples/hazards.asm --check --out build/hazards
```

Regenerate the hardware waveform with:

```bash
python3 scripts/verify_rtl.py
```

The VCD starts with reset and register initialization, before algorithm cycle 1.
All checked outputs are described in `../docs/validation.md`.
