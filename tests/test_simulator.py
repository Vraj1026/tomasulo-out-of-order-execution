import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from tomasulo import Config, Simulator, parse_program
from tomasulo.reference import run_sequential
from tomasulo.isa import arithmetic
from tomasulo.report import write_html

ROOT = Path(__file__).resolve().parents[1]


class TomasuloTests(unittest.TestCase):
    def simulate(self, source, config=None):
        program = parse_program(source)
        sim = Simulator(program, config).run()
        regs, memory = run_sequential(program, sim.config.memory_words)
        self.assertEqual(sim.regs, regs)
        self.assertEqual(sim.memory, memory)
        return sim

    def test_hand_calculated_hazard_timeline(self):
        sim = self.simulate((ROOT / "examples/hazards.asm").read_text())
        self.assertEqual([(r['issue'],r['start'],r['end'],r['writeback']) for r in sim.timeline],
                         [(1,2,6,7),(2,8,9,10),(3,4,5,6),(4,6,7,8),(5,7,11,12),(6,13,14,15)])
        self.assertEqual([sim.regs[i] for i in (3,8,9,10,11)], [23,6,142,18,160])

    def test_raw_waits_for_broadcast(self):
        sim = self.simulate('.reg R1 3\nMUL R2,R1,R1\nADD R3,R2,R2')
        self.assertEqual(sim.regs[3], 18)
        self.assertEqual(sim.timeline[1]['start'], sim.timeline[0]['writeback']+1)

    def test_war_captures_old_source(self):
        sim = self.simulate('.reg R1 9\n.reg R4 5\nMUL R2,R4,R4\nADD R3,R1,R2\nADD R1,R4,R4')
        self.assertEqual((sim.regs[1],sim.regs[3]), (10,34))

    def test_waw_does_not_overwrite_newer_value(self):
        sim = self.simulate('.reg R1 3\nMUL R2,R1,R1\nADD R2,R1,R1')
        self.assertLess(sim.timeline[1]['writeback'], sim.timeline[0]['writeback'])
        self.assertEqual(sim.regs[2], 6)

    def test_older_consumer_keeps_older_producer(self):
        sim = self.simulate('.reg R1 3\nMUL R2,R1,R1\nADD R3,R2,R1\nADD R2,R1,R1')
        self.assertEqual((sim.regs[2],sim.regs[3]), (6,12))

    def test_self_destination_is_read_before_rename(self):
        sim = self.simulate('.reg R1 7\nADD R1,R1,R1\nMUL R1,R1,R1')
        self.assertEqual(sim.regs[1],196)

    def test_r0_never_renamed(self):
        sim = self.simulate('.reg R1 8\nMUL R0,R1,R1\nADD R2,R0,R1')
        self.assertEqual((sim.regs[0],sim.regs[2]),(0,8))
        self.assertTrue(all(s['rat'][0] is None for s in sim.trace))

    def test_cdb_arbitrates_and_retains_loser(self):
        sim = self.simulate((ROOT/'examples/cdb_contention.asm').read_text())
        self.assertEqual(sim.timeline[0]['end'],sim.timeline[2]['end'])
        self.assertEqual((sim.timeline[0]['writeback'],sim.timeline[2]['writeback']),(7,8))
        self.assertEqual(sim.metrics['cdb_wait_instruction_cycles'],1)
        self.assertTrue(all(sum(e['kind']=='broadcast' for e in s['events'])<=1 for s in sim.trace))

    def test_two_cdbs_can_broadcast_together(self):
        sim = self.simulate((ROOT/'examples/cdb_contention.asm').read_text(),Config(cdb_width=2))
        self.assertEqual(sim.timeline[0]['writeback'],sim.timeline[2]['writeback'])

    def test_same_cycle_issue_reads_cdb_value(self):
        config=Config(stations={'ADD':1,'MUL':1,'MEM':1})
        sim=self.simulate('.reg R1 2\nADD R2,R1,R1\nADD R2,R2,R2',config)
        self.assertEqual(sim.timeline[1]['issue'],sim.timeline[0]['writeback'])
        self.assertEqual(sim.regs[2],8)
        self.assertGreater(sim.metrics['issue_stall_cycles'],0)

    def test_issue_stall_blocks_later_different_group(self):
        config=Config(stations={'ADD':1,'MUL':1,'MEM':1})
        sim=self.simulate('ADD R1,R0,R0\nADD R2,R0,R0\nMUL R3,R0,R0',config)
        self.assertEqual(sim.timeline[2]['issue'],sim.timeline[1]['issue']+1)

    def test_latency_one_still_needs_separate_writeback(self):
        c=Config();c.latencies['ADD']=1
        sim=self.simulate('ADD R1,R0,R0',c)
        self.assertEqual((sim.timeline[0]['issue'],sim.timeline[0]['start'],sim.timeline[0]['end'],sim.timeline[0]['writeback']),(1,2,2,3))

    def test_slot_reuse_and_unique_tags(self):
        c=Config(stations={'ADD':1,'MUL':1,'MEM':1})
        sim=self.simulate('.reg R1 1\n'+'\n'.join(['ADD R1,R1,R1']*20),c)
        self.assertEqual(sim.regs[1],2**20)
        self.assertEqual(len({r['id'] for r in sim.timeline}),20)

    def test_integer_edges(self):
        self.assertEqual(arithmetic('ADD',0xffffffff,1),0)
        self.assertEqual(arithmetic('SUB',0,1),0xffffffff)
        self.assertEqual(arithmetic('MUL',0x80000000,2),0)
        self.assertEqual(arithmetic('DIV',0xfffffff9,3),0xfffffffe)
        self.assertEqual(arithmetic('DIV',7,0xfffffffd),0xfffffffe)
        self.assertEqual(arithmetic('DIV',1,0),0xffffffff)
        self.assertEqual(arithmetic('DIV',0x80000000,0xffffffff),0x80000000)

    def test_memory_example(self):
        sim=self.simulate((ROOT/'examples/memory.asm').read_text())
        self.assertEqual((sim.memory[68],sim.memory[72],sim.regs[5]),(70,69,70))
        self.assertGreater(sim.timeline[3]['start'],sim.timeline[2]['writeback'])

    def test_load_before_younger_store(self):
        sim=self.simulate('.reg R1 12\n.mem 0 7\nLD R2,0(R0)\nST R1,0(R0)')
        self.assertEqual((sim.regs[2],sim.memory[0]),(7,12))

    def test_unknown_older_store_address_blocks_load(self):
        sim=self.simulate('.reg R1 4\n.reg R2 9\nMUL R3,R1,R1\nST R2,0(R3)\nLD R4,16(R0)')
        self.assertEqual(sim.regs[4],9)
        self.assertGreater(sim.metrics['memory_order_wait_instruction_cycles'],0)

    def test_store_data_keeps_old_register_version(self):
        sim=self.simulate('.reg R1 4\n.reg R2 9\nMUL R3,R1,R1\nST R2,0(R3)\nADD R2,R1,R1\nLD R4,16(R0)')
        self.assertEqual((sim.regs[2],sim.regs[4]),(8,9))

    def test_uninitialized_load_zero_and_negative_offset(self):
        sim=self.simulate('.reg R1 4\nLD R2,-4(R1)')
        self.assertEqual(sim.regs[2],0)

    def test_bad_memory_addresses_fail(self):
        for source in ['LD R1,2(R0)','LD R1,4096(R0)','LD R1,-4(R0)', '.mem 4096 1']:
            with self.subTest(source=source),self.assertRaises(ValueError):
                Simulator(parse_program(source)).run()

    def test_parser_rejects_bad_input(self):
        for source in ['ADD R32,R0,R0','ADD R1,R2','XYZ R1,R2,R3','.reg R0 4',
                       '.mem 2 5','ADD R1,R0,R0\n.reg R2 5','ADDI R1,R0,2147483648']:
            with self.subTest(source=source),self.assertRaises(ValueError):parse_program(source)

    def test_parser_comments_and_hex(self):
        sim=self.simulate('.reg r1 0xff # comment\naddi r2,r1,-1 ; trailing')
        self.assertEqual(sim.regs[2],254)

    def test_invalid_config_and_cycle_limit(self):
        for c in [Config(cdb_width=0),Config(max_cycles=True),Config(units={'ADD':1,'MUL':1,'MEM':2})]:
            with self.assertRaises(ValueError):Simulator(parse_program(''),c)
        with self.assertRaises(RuntimeError):
            Simulator(parse_program('ADD R1,R0,R0'),Config(max_cycles=1)).run()

    def test_empty_program_and_no_trace(self):
        sim=Simulator(parse_program(''),record_trace=False).run()
        self.assertEqual((sim.cycle,sim.report()['summary']['ipc'],sim.trace),(0,0,[]))

    def test_step_matches_run_and_snapshot_is_independent(self):
        p=parse_program('.reg R1 3\nADD R2,R1,R1\nMUL R3,R2,R1')
        a=Simulator(p);b=Simulator(p).run()
        while not a.done:a.step()
        self.assertEqual(a.report(),b.report())
        self.assertEqual(a.trace[0]['registers'][2],0)

    def test_cli_outputs_and_error_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc=subprocess.run([sys.executable,'-m','tomasulo',str(ROOT/'examples/hazards.asm'),'--check','--out',tmp],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            data=json.loads((Path(tmp)/'trace.json').read_text())
            self.assertEqual(data['registers'][11],160)
            self.assertTrue((Path(tmp)/'trace.html').exists())
            bad=Path(tmp)/'bad.asm';bad.write_text('ADD R32,R0,R0')
            proc=subprocess.run([sys.executable,'-m','tomasulo',str(bad)],cwd=ROOT,capture_output=True)
            self.assertNotEqual(proc.returncode,0)

    def test_html_escapes_script_terminator(self):
        sim=Simulator(parse_program('ADD R1,R0,R0')).run()
        report=sim.report();report['timeline'][0]['instruction']='</script><script>alert(1)</script>'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trace.html';write_html(report,p)
            self.assertNotIn('</script><script>alert',p.read_text())
            self.assertIn('\\u003c/script>',p.read_text())

    def test_500_random_programs_against_independent_oracle(self):
        # 500 independent seeds, 64 instructions each; all ISA operations,
        # register hazards, wraparound, stores, loads, and resource pressure.
        for seed in range(500):
            with self.subTest(seed=seed):
                rng=random.Random(seed)
                lines=[f'.reg R{i} {rng.getrandbits(32)}' for i in range(1,13)]
                lines += [f'.mem {i*4} {rng.getrandbits(32)}' for i in range(16)]
                for _ in range(64):
                    op=rng.choice(['ADD','SUB','MUL','DIV','ADDI','LD','ST'])
                    rd,a,b=(rng.randrange(13) for _ in range(3))
                    if op in ('LD','ST'):lines.append(f'{op} R{rd},{4*rng.randrange(16)}(R0)')
                    elif op=='ADDI':lines.append(f'{op} R{rd},R{a},{rng.randint(-100,100)}')
                    else:lines.append(f'{op} R{rd},R{a},R{b}')
                c=Config(stations={'ADD':rng.randint(1,5),'MUL':rng.randint(1,4),'MEM':rng.randint(1,4)},
                    units={'ADD':rng.randint(1,3),'MUL':rng.randint(1,2),'MEM':1},cdb_width=rng.randint(1,3))
                c.latencies={op:rng.randint(1,8) for op in c.latencies}
                program=parse_program('\n'.join(lines));sim=Simulator(program,c,record_trace=False).run()
                self.assertEqual((sim.regs,sim.memory),run_sequential(program))


if __name__=='__main__':unittest.main()
