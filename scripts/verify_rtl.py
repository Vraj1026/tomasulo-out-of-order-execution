#!/usr/bin/env python3
"""Generate vectors, compile RTL, compare every issue/CDB cycle and all registers."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tomasulo import Config, Simulator, parse_program
from tomasulo.reference import run_sequential


def write_case(source, path, config):
    p=parse_program(source)
    s=Simulator(p,config).run()
    expected,_=run_sequential(p)
    if s.regs != expected:raise RuntimeError('Python model disagrees with independent oracle')
    lines=[f'{len(p.instructions)} {s.cycle}',
           ' '.join(f'{p.registers.get(i,0):08x}' for i in range(32))]
    ops={'ADD':0,'SUB':1,'MUL':2}
    for inst,row in zip(p.instructions,s.timeline):
        lines.append(f'{ops[inst.op]} {inst.dst} {inst.src1} {inst.src2} {row["issue"]}')
    for snap in s.trace[1:]:
        broadcasts=[e for e in snap['events'] if e['kind']=='broadcast']
        lines.append(f'1 {broadcasts[0]["id"]} {broadcasts[0]["value"]:08x}' if broadcasts else '0 0 00000000')
    lines.append(' '.join(f'{v:08x}' for v in expected))
    path.write_text('\n'.join(lines)+'\n')
    return s.cycle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds',type=int,default=200)
    parser.add_argument('--backend',choices=['auto','iverilog','verilator'],default='auto')
    parser.add_argument('--profile',choices=['default','tiny'],default='default')
    args=parser.parse_args()
    if args.seeds<0:parser.error('--seeds cannot be negative')
    build=ROOT/'build'/f'rtl-{args.profile}';build.mkdir(parents=True,exist_ok=True)
    iverilog=shutil.which('iverilog')
    verilator=shutil.which(os.environ.get('VERILATOR','verilator')) or shutil.which('verilator-cli')
    if not verilator and importlib.util.find_spec('verilator'):
        import sysconfig
        candidate=Path(sysconfig.get_path('scripts',scheme='posix_user'))/'verilator-cli'
        if candidate.exists():verilator=str(candidate)
    backend=args.backend
    if backend=='auto':backend='iverilog' if iverilog else 'verilator'
    if (backend=='iverilog' and not iverilog) or (backend=='verilator' and not verilator):
        print('No RTL simulator available. Install Icarus Verilog or Verilator; see README.',file=sys.stderr)
        return 2
    config=Config()
    params={}
    if args.profile=='tiny':
        config.stations.update(ADD=1,MUL=1)
        config.latencies.update(ADD=1,SUB=1,MUL=1)
        params={'ADD_RS':1,'MUL_RS':1,'ADD_LATENCY':1,'MUL_LATENCY':1}
    sources=[str(ROOT/'rtl/tomasulo_core.sv'),str(ROOT/'tb/tomasulo_tb.sv')]
    if backend=='iverilog':
        executable=build/'sim.vvp'
        cmd=[iverilog,'-g2012','-s','tomasulo_tb','-o',str(executable)]
        cmd += [f'-Ptomasulo_tb.{k}={v}' for k,v in params.items()]+sources
        runner=[shutil.which('vvp') or 'vvp',str(executable)]
    else:
        obj=build/'obj_dir'
        cmd=[verilator,'--binary','--timing','--trace','--top-module','tomasulo_tb',
             '--Mdir',str(obj),'-j','2','-Wno-fatal']
        cmd += [f'-G{k}={v}' for k,v in params.items()]+sources
        runner=[str(obj/'Vtomasulo_tb')]
    compile_result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
    (build/'compile.log').write_text(compile_result.stdout+compile_result.stderr)
    if compile_result.returncode:
        print(compile_result.stdout+compile_result.stderr,file=sys.stderr);return 1
    directed=[(ROOT/'examples'/name).read_text() for name in ['hazards.asm','parallel.asm','cdb_contention.asm']]
    directed += ['', '.reg R1 7\nADD R1,R1,R1\nMUL R1,R1,R1',
                 '.reg R1 7\nMUL R0,R1,R1\nADD R2,R0,R1',
                 '.reg R1 2\n'+'\n'.join(['ADD R1,R1,R1']*20),
                 '.reg R1 3\nMUL R2,R1,R1\nADD R3,R2,R1\nADD R2,R1,R1']
    sources_by_case=list(directed)
    for seed in range(args.seeds):
        rng=random.Random(seed)
        lines=[f'.reg R{i} {rng.getrandbits(32)}' for i in range(1,13)]
        for _ in range(48):
            op=rng.choice(['ADD','SUB','MUL']);rd,a,b=[rng.randrange(13) for _ in range(3)]
            lines.append(f'{op} R{rd},R{a},R{b}')
        sources_by_case.append('\n'.join(lines))
    total_cycles=0
    for i,source in enumerate(sources_by_case):
        case=build/f'case_{i:04d}.txt'
        total_cycles+=write_case(source,case,config)
        run=runner+[f'+CASE={case}']
        if i==0:run += [f'+WAVES={build / "hazards.vcd"}']
        result=subprocess.run(run,cwd=ROOT,capture_output=True,text=True,timeout=30)
        if result.returncode or 'PASS ' not in result.stdout:
            (build/'failed.asm').write_text(source)
            print(result.stdout+result.stderr,file=sys.stderr)
            print(f'FAILED case {i}; saved {build / "failed.asm"}',file=sys.stderr);return 1
    report=dict(status='PASS',backend=backend,profile=args.profile,cases=len(sources_by_case),
                random_seeds=args.seeds,checked_cycles=total_cycles,
                checks=['issue timing','CDB valid, tag, value every cycle','32 final registers',
                        'drain','pending tags cleared','reset during in-flight work'])
    (build/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS: {len(sources_by_case)} RTL cases, {total_cycles} cycles checked ({backend}, {args.profile}).')
    print(f'Waveform: {build / "hazards.vcd"}')
    return 0


if __name__=='__main__':raise SystemExit(main())
