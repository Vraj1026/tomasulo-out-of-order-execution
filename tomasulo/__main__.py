"""Run with python3 -m tomasulo examples/hazards.asm --check --out build/demo."""
import argparse
import csv
import json
from pathlib import Path
import sys
from .isa import parse_program, s32
from .model import Config, Simulator
from .reference import run_sequential
from .report import write_html


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cycle-by-cycle integer Tomasulo simulator")
    parser.add_argument("program", type=Path)
    parser.add_argument("--config", type=Path, help="JSON overrides for machine resources/latencies")
    parser.add_argument("--out", type=Path, default=Path("build/run"), help="Output directory")
    parser.add_argument("--check", action="store_true", help="Compare final state with sequential interpreter")
    parser.add_argument("--no-trace", action="store_true", help="Skip snapshots and HTML for large programs")
    args = parser.parse_args(argv)
    try:
        config = Config()
        if args.config:
            values = json.loads(args.config.read_text())
            if not isinstance(values, dict):
                raise ValueError("Configuration must be a JSON object")
            for key, value in values.items():
                if key not in config.__dataclass_fields__:
                    raise ValueError(f"Unknown configuration key {key!r}")
                if key in ("stations", "units", "latencies"):
                    if not isinstance(value, dict):
                        raise ValueError(f"{key} must be an object")
                    getattr(config, key).update(value)
                else:
                    setattr(config, key, value)
        program = parse_program(args.program.read_text())
        sim = Simulator(program, config, record_trace=not args.no_trace).run()
        report = sim.report()
        if args.check:
            reference_regs, reference_mem = run_sequential(program, config.memory_words)
            if sim.regs != reference_regs or sim.memory != reference_mem:
                raise RuntimeError("FAIL: architectural state differs from sequential reference")
            report["validation"] = "PASS: all 32 registers and full initialized/written memory match sequential reference"
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "trace.json").write_text(json.dumps(report, indent=2) + "\n")
        with (args.out / "timeline.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["id", "instruction", "issue", "start", "end", "writeback", "slot"])
            writer.writeheader()
            writer.writerows(report["timeline"])
        if not args.no_trace:
            write_html(report, args.out / "trace.html")
        print(f"Instructions: {len(program.instructions)} | Cycles: {sim.cycle} | IPC: {report['summary']['ipc']:.3f}")
        print(f"{'ID':>3}  {'Instruction':<26} {'Issue':>5} {'Start':>5} {'End':>5} {'WB':>5}")
        for row in report["timeline"]:
            print(f"{row['id']:>3}  {row['instruction']:<26} {row['issue']:>5} {row['start']:>5} {row['end']:>5} {row['writeback']:>5}")
        print("Registers: " + ", ".join(f"R{i}={s32(v)}" for i,v in enumerate(sim.regs) if v or i == 0))
        if "validation" in report:
            print(report["validation"])
        print(f"Output: {args.out.resolve()}")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
