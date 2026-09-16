"""Cycle-stepped Tomasulo with tagged operands and conservative memory ordering."""
from dataclasses import asdict, dataclass, field
from copy import deepcopy
from .isa import GROUP, Instruction, Program, address, arithmetic, u32


@dataclass
class Config:
    stations: dict[str, int] = field(default_factory=lambda: {"ADD": 3, "MUL": 2, "MEM": 3})
    units: dict[str, int] = field(default_factory=lambda: {"ADD": 1, "MUL": 1, "MEM": 1})
    latencies: dict[str, int] = field(default_factory=lambda:
        {"ADD": 2, "SUB": 2, "ADDI": 2, "MUL": 5, "DIV": 12, "LD": 3, "ST": 3})
    cdb_width: int = 1
    memory_words: int = 1024
    max_cycles: int = 100000

    def validate(self):
        for label, values, keys in (("stations", self.stations, {"ADD", "MUL", "MEM"}),
                                    ("units", self.units, {"ADD", "MUL", "MEM"}),
                                    ("latencies", self.latencies, set(GROUP))):
            if not isinstance(values, dict) or set(values) != keys:
                raise ValueError(f"{label} must have exactly {sorted(keys)}")
            if any(type(x) is not int or x < 1 for x in values.values()):
                raise ValueError(f"{label} values must be positive integers")
        if self.units["MEM"] != 1:
            raise ValueError("This conservative memory model supports exactly one memory unit")
        for key in ("cdb_width", "memory_words", "max_cycles"):
            value = getattr(self, key)
            if type(value) is not int or value < 1:
                raise ValueError(f"{key} must be a positive integer")


@dataclass
class Operand:
    value: int = 0
    tag: int | None = None


@dataclass
class Entry:
    tag: int
    slot: str
    inst: Instruction
    a: Operand
    b: Operand
    issued: int
    state: str = "waiting"
    remaining: int = 0
    result: int | None = None
    addr: int | None = None
    end: int | None = None


class Simulator:
    def __init__(self, program: Program, config: Config | None = None, *, record_trace=True):
        self.program = deepcopy(program)
        self.config = deepcopy(config or Config())
        self.config.validate()
        self.regs = [0] * 32
        for reg, value in self.program.registers.items():
            if type(reg) is not int or not 0 <= reg < 32 or (reg == 0 and value != 0):
                raise ValueError(f"Invalid initial register R{reg}")
            self.regs[reg] = u32(value)
        self.memory = dict(self.program.memory)
        for addr in self.memory:
            address(addr, 0, self.config.memory_words)
            if addr < 0 or addr > 0xFFFFFFFF:
                raise ValueError(f"Invalid initial address {addr}")
            self.memory[addr] = u32(self.memory[addr])
        for inst in self.program.instructions:
            if inst.op not in GROUP:
                raise ValueError(f"Unsupported opcode {inst.op}")
            for reg in (inst.src1, inst.src2, inst.dst):
                if reg is not None and (type(reg) is not int or not 0 <= reg < 32):
                    raise ValueError(f"Invalid register {reg}")
        self.rat: list[int | None] = [None] * 32
        self.entries: list[Entry] = []
        self.pc = self.cycle = 0
        self.record_trace = record_trace
        self.timeline = [dict(id=i+1, instruction=x.text, issue=None,
            start=None, end=None, writeback=None, slot=None) for i, x in enumerate(self.program.instructions)]
        self.metrics = dict(issue_stall_cycles=0, cdb_wait_instruction_cycles=0,
                            operand_wait_instruction_cycles=0, memory_order_wait_instruction_cycles=0,
                            fu_wait_instruction_cycles=0)
        self.trace: list[dict] = []
        self._snapshot([])

    @property
    def done(self):
        return self.pc == len(self.program.instructions) and not self.entries

    def _read(self, reg: int) -> Operand:
        return Operand(self.regs[reg], self.rat[reg])

    def _event(self, events, kind, entry, **kwargs):
        events.append(dict(kind=kind, id=entry.tag, slot=entry.slot, **kwargs))

    def step(self):
        if self.done:
            return []
        if self.cycle >= self.config.max_cycles:
            raise RuntimeError(f"Cycle limit {self.config.max_cycles} reached")
        self.cycle += 1
        events = []

        # Choose using start-of-cycle state. A broadcast wakes a consumer for
        # NEXT cycle; a just-issued instruction cannot start this cycle.
        starting = []
        for group in self.config.stations:
            occupied = sum(e.state == "executing" and GROUP[e.inst.op] == group for e in self.entries)
            free = self.config.units[group] - occupied
            for e in self.entries:  # Entries stay in program/tag order.
                if GROUP[e.inst.op] != group or e.state != "waiting":
                    continue
                if e.a.tag is not None or e.b.tag is not None:
                    self.metrics["operand_wait_instruction_cycles"] += 1
                elif group == "MEM" and any(x.tag < e.tag and GROUP[x.inst.op] == "MEM" for x in self.entries):
                    self.metrics["memory_order_wait_instruction_cycles"] += 1
                elif free <= 0:
                    self.metrics["fu_wait_instruction_cycles"] += 1
                else:
                    starting.append(e)
                    free -= 1

        # Oldest completed instruction wins CDB arbitration; stores use no CDB.
        completed = [e for e in self.entries if e.state == "complete"]
        writes = [e for e in completed if e.inst.op != "ST"]
        winners = writes[:self.config.cdb_width]
        self.metrics["cdb_wait_instruction_cycles"] += max(0, len(writes) - len(winners))
        for e in completed:
            if e.inst.op == "ST":
                self.memory[e.addr] = e.b.value
                self._event(events, "store", e, address=e.addr, value=e.b.value)
            elif e in winners:
                for consumer in self.entries:
                    for operand in (consumer.a, consumer.b):
                        if operand.tag == e.tag:
                            operand.value, operand.tag = e.result, None
                # This test is essential: an older writer may be superseded.
                if e.inst.dst != 0 and self.rat[e.inst.dst] == e.tag:
                    self.regs[e.inst.dst] = e.result
                    self.rat[e.inst.dst] = None
                self._event(events, "broadcast", e, value=e.result, destination=e.inst.dst)
            else:
                continue
            self.timeline[e.tag-1]["writeback"] = self.cycle
            self.entries.remove(e)

        for e in starting:
            e.state = "executing"
            e.remaining = self.config.latencies[e.inst.op]
            self.timeline[e.tag-1]["start"] = self.cycle
            if GROUP[e.inst.op] == "MEM":
                e.addr = address(e.a.value, e.inst.imm, self.config.memory_words)
            self._event(events, "start", e)

        # The starting cycle is execution cycle 1. Finish at start+latency-1.
        for e in self.entries:
            if e.state != "executing":
                continue
            e.remaining -= 1
            if e.remaining == 0:
                if e.inst.op == "LD":
                    e.result = self.memory.get(e.addr, 0)
                elif e.inst.op != "ST":
                    e.result = arithmetic(e.inst.op, e.a.value, e.b.value)
                e.state, e.end = "complete", self.cycle
                self.timeline[e.tag-1]["end"] = self.cycle
                self._event(events, "finish", e, value=e.result)

        # In-order, single issue; sources are captured BEFORE destination rename.
        if self.pc < len(self.program.instructions):
            inst = self.program.instructions[self.pc]
            group = GROUP[inst.op]
            used = {e.slot for e in self.entries}
            slot = next((f"{group}{i}" for i in range(self.config.stations[group])
                         if f"{group}{i}" not in used), None)
            if slot is None:
                self.metrics["issue_stall_cycles"] += 1
                events.append(dict(kind="issue_stall", id=self.pc+1, group=group))
            else:
                a = self._read(inst.src1)
                b = self._read(inst.src2) if inst.src2 is not None else Operand(u32(inst.imm))
                tag = self.pc + 1  # Unique sequence tag, independent of reused slot.
                e = Entry(tag, slot, inst, a, b, self.cycle)
                self.entries.append(e)
                if inst.dst is not None and inst.dst != 0:
                    self.rat[inst.dst] = tag
                self.timeline[self.pc].update(issue=self.cycle, slot=slot)
                self.pc += 1
                self._event(events, "issue", e)
        self._check_invariants()
        self._snapshot(events)
        return events

    def _check_invariants(self):
        tags = {e.tag for e in self.entries}
        assert self.regs[0] == 0 and self.rat[0] is None
        assert len(tags) == len(self.entries)
        assert len({e.slot for e in self.entries}) == len(self.entries)
        assert all(tag is None or tag in tags for tag in self.rat)
        for e in self.entries:
            assert all(o.tag is None or (o.tag in tags and o.tag < e.tag) for o in (e.a, e.b))
        for group, count in self.config.stations.items():
            assert sum(GROUP[e.inst.op] == group for e in self.entries) <= count
            assert sum(GROUP[e.inst.op] == group and e.state == "executing" for e in self.entries) <= self.config.units[group]

    def _snapshot(self, events):
        if self.record_trace:
            self.trace.append(dict(cycle=self.cycle, pc=self.pc, registers=self.regs.copy(),
                rat=self.rat.copy(), memory=dict(self.memory), events=deepcopy(events),
                stations=[dict(tag=e.tag, slot=e.slot, op=e.inst.op, dst=e.inst.dst,
                    vj=e.a.value if e.a.tag is None else None, qj=e.a.tag,
                    vk=e.b.value if e.b.tag is None else None, qk=e.b.tag,
                    state=e.state, remaining=e.remaining, result=e.result, address=e.addr)
                    for e in self.entries]))

    def run(self):
        while not self.done:
            self.step()
        return self

    def report(self):
        count = len(self.program.instructions)
        return dict(config=asdict(self.config), summary=dict(instructions=count, cycles=self.cycle,
            ipc=count/self.cycle if self.cycle else 0, **self.metrics),
            registers=self.regs.copy(), memory=dict(self.memory),
            timeline=deepcopy(self.timeline), trace=deepcopy(self.trace))
