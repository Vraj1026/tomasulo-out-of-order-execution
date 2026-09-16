"""Small integer teaching ISA. This is not a binary RISC-V implementation."""
from dataclasses import dataclass, field
import re

MASK = 0xFFFFFFFF
GROUP = {"ADD": "ADD", "SUB": "ADD", "ADDI": "ADD",
         "MUL": "MUL", "DIV": "MUL", "LD": "MEM", "ST": "MEM"}


def u32(value: int) -> int:
    return value & MASK


def s32(value: int) -> int:
    value &= MASK
    return value if value < 0x80000000 else value - 0x100000000


def arithmetic(op: str, a: int, b: int) -> int:
    if op in ("ADD", "ADDI"):
        return u32(a + b)
    if op == "SUB":
        return u32(a - b)
    if op == "MUL":
        return u32(a * b)
    if op == "DIV":
        a, b = s32(a), s32(b)
        if b == 0:
            return MASK
        quotient = abs(a) // abs(b)
        return u32(-quotient if (a < 0) != (b < 0) else quotient)
    raise ValueError(f"Not an arithmetic operation: {op}")


def address(base: int, offset: int, memory_words: int) -> int:
    result = u32(base + offset)
    if result % 4 or result >= 4 * memory_words:
        raise ValueError(f"Invalid memory address {result}: require 4-byte alignment "
                         f"and 0 <= address < {4 * memory_words}")
    return result


@dataclass(frozen=True)
class Instruction:
    op: str
    dst: int | None
    src1: int
    src2: int | None = None
    imm: int = 0
    text: str = ""


@dataclass
class Program:
    instructions: list[Instruction] = field(default_factory=list)
    registers: dict[int, int] = field(default_factory=dict)
    memory: dict[int, int] = field(default_factory=dict)


def register(text: str) -> int:
    if not re.fullmatch(r"R(?:[0-9]|[12][0-9]|3[01])", text.upper()):
        raise ValueError(f"Invalid register {text!r}; expected R0..R31")
    return int(text[1:])


def number(text: str, signed_only: bool = False) -> int:
    # Decimal, including leading zeros, or an explicit 0x/0b prefix.
    try:
        value = int(text, 0) if re.match(r"[+-]?0[xXbB]", text) else int(text, 10)
    except ValueError:
        raise ValueError(f"Invalid integer {text!r}") from None
    high = 0x7FFFFFFF if signed_only else MASK
    if not -0x80000000 <= value <= high:
        raise ValueError(f"Integer {text!r} is outside the supported 32-bit range")
    return value


def parse_program(source: str) -> Program:
    program = Program()
    for line_no, raw in enumerate(source.splitlines(), 1):
        line = raw.split("#", 1)[0].split(";", 1)[0].strip()
        if not line:
            continue
        try:
            fields = line.replace(",", " ").split()
            op = fields[0].upper()
            if op in (".REG", ".MEM"):
                if len(fields) != 3 or program.instructions:
                    raise ValueError("Initialization directives require two operands and precede instructions")
                val = u32(number(fields[2]))
                if op == ".REG":
                    reg = register(fields[1])
                    if reg == 0 and val != 0:
                        raise ValueError("R0 is hardwired to zero")
                    program.registers[reg] = val
                else:
                    addr = number(fields[1])
                    if addr < 0 or addr % 4:
                        raise ValueError("Memory initialization needs a nonnegative aligned byte address")
                    program.memory[addr] = val
            elif op in ("ADD", "SUB", "MUL", "DIV") and len(fields) == 4:
                program.instructions.append(Instruction(op, register(fields[1]),
                    register(fields[2]), register(fields[3]), text=line))
            elif op == "ADDI" and len(fields) == 4:
                program.instructions.append(Instruction(op, register(fields[1]),
                    register(fields[2]), imm=number(fields[3], True), text=line))
            elif op in ("LD", "ST"):
                match = re.fullmatch(r"(LD|ST)\s+(R\d+)\s*,?\s*([+-]?(?:0[xX][0-9a-fA-F]+|0[bB][01]+|\d+))\s*\(\s*(R\d+)\s*\)", line, re.I)
                if not match:
                    raise ValueError("Use LD R1, 0(R2) or ST R1, 0(R2)")
                data_reg, base = register(match[2]), register(match[4])
                offset = number(match[3], True)
                program.instructions.append(Instruction(op,
                    data_reg if op == "LD" else None, base,
                    data_reg if op == "ST" else None, offset, line))
            else:
                raise ValueError(f"Unknown instruction or wrong operand count: {line}")
        except ValueError as exc:
            raise ValueError(f"Line {line_no}: {exc}") from None
    return program
