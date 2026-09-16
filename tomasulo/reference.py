"""Sequential architectural oracle. No tags, stations, buses, or scheduling."""
from .isa import Program, MASK


def run_sequential(program: Program, memory_words: int = 1024):
    regs = [0] * 32
    for reg, value in program.registers.items():
        regs[reg] = value & MASK
    regs[0] = 0
    memory = {key: value & MASK for key, value in program.memory.items()}
    for inst in program.instructions:
        a = regs[inst.src1]
        b = regs[inst.src2] if inst.src2 is not None else inst.imm
        if inst.op in ("LD", "ST"):
            addr = (a + inst.imm) & MASK
            if addr % 4 or not 0 <= addr < 4 * memory_words:
                raise ValueError(f"Invalid address {addr}")
            if inst.op == "ST":
                memory[addr] = b
                continue
            value = memory.get(addr, 0)
        elif inst.op in ("ADD", "ADDI"):
            value = a + b
        elif inst.op == "SUB":
            value = a - b
        elif inst.op == "MUL":
            value = a * b
        elif inst.op == "DIV":
            a = a if a < 2**31 else a - 2**32
            b = b if b < 2**31 else b - 2**32
            if b == 0:
                value = MASK
            else:
                value = abs(a) // abs(b)
                if a * b < 0:
                    value = -value
        else:
            raise ValueError(inst.op)
        if inst.dst != 0:
            regs[inst.dst] = value & MASK
    return regs, memory
