#!/usr/bin/env python3
"""A reproducible resource sweep; these are modeled cycles, not silicon results."""
import csv
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tomasulo import Config, Simulator, parse_program
from tomasulo.reference import run_sequential


def main():
    configs={"default":Config(),"two_cdbs":Config(cdb_width=2),
             "more_stations":Config(stations={"ADD":6,"MUL":4,"MEM":3}),
             "two_compute_units":Config(units={"ADD":2,"MUL":2,"MEM":1}),
             "wider_resources":Config(stations={"ADD":6,"MUL":4,"MEM":3},
                                     units={"ADD":2,"MUL":2,"MEM":1},cdb_width=2)}
    rows=[]
    for name in ['hazards','parallel','cdb_contention','memory']:
        program=parse_program((ROOT/'examples'/f'{name}.asm').read_text())
        expected=run_sequential(program)
        for label,config in configs.items():
            sim=Simulator(program,config,record_trace=False).run()
            if (sim.regs,sim.memory)!=expected:raise RuntimeError('Reference mismatch')
            rows.append(dict(program=name,configuration=label,**sim.report()['summary']))
    out=ROOT/'build/experiments.csv';out.parent.mkdir(exist_ok=True)
    with out.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    for r in rows:print(f"{r['program']:16} {r['configuration']:20} {r['cycles']:4} cycles  IPC={r['ipc']:.3f}")
    print(f'Saved {out}')


if __name__=='__main__':main()
