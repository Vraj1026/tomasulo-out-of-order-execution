# References and implementation notes

Reference: [heyneil09/Tomasulo-algorithm-for-out-of-order-execution](https://github.com/heyneil09/Tomasulo-algorithm-for-out-of-order-execution)

Inspected Git commit: `3b37f86966799ca6b584302d1d475c6dbf4ec14a` (`Update procsim.cpp`).
The repository was successfully cloned for inspection. These findings refer to
that snapshot, not to any later state of the remote repository.

## Files present

`Memory.v`, `PC.v`, `Queue.v`, `RAM.v`, `ROM.v`, `RegFile.v`,
`ReservationStation.v`, and `procsim.cpp`.

## Build blockers observed

| Location | Finding | Consequence |
|---|---|---|
| PC / Queue / RegFile / ReservationStation | Include `head.v`, absent from the snapshot | Missing definitions prevent a complete HDL build |
| `procsim.cpp` | Includes `procsim.hpp`, absent from the snapshot | Required declarations and interface are unavailable |
| Repository root | No integrated processor top level, testbench, or build script | No reproducible end-to-end demonstration |
| `ROM.v` | Loads a hard-coded Windows path ending in `rom/rom.mem` | Program image is absent and path is machine-specific |

## Additional code-review findings

The C++ exception path calls `flush_ROB()`, whose body clears the ROB, and then
accesses `ROB[rob_itr].instr_num` in the following flush call. That access needs
to be preserved before the clear rather than read from the cleared vector.

The scheduling condition includes `scoreboard.FU[schQ[i].op_code]` while `-1`
is also treated as a valid special opcode. When the earlier short-circuit term
is false for that special opcode, the expression can attempt a negative index.
These are inspection findings; the original C++ could not be built from the
available snapshot because its header and harness are missing.

The RTL fragments also need an explicit integrated protocol for execution
acceptance, result holding, arbitration, reset, and memory transactions. For
example, `ReservationStation.v` declares an `EXEable` input but does not use it
to track whether a ready instruction has already begun execution. Its intended
external control is not supplied in the snapshot.

## Implementation scope

This repository contains a standalone implementation.
The original files are not redistributed or presented as working modules.
No original repository history is included. The reference supplied the project
topic and motivated the audit; this implementation uses its own ISA, module
interface, documented timing contract, tests, and explanations.

The MIT license in this package applies to these new sources. The inspected
snapshot did not contain a license file; no licensing claim is made for the
reference repository's code.

## Further primary references

- [University of Edinburgh: operation of the algorithm](https://homepages.inf.ed.ac.uk/rni/comp-arch/Paru/tom-alg.html)
- [University of Edinburgh: HASE Tomasulo project](https://www.icsa.inf.ed.ac.uk/research/groups/hase/models/tomasulo/tomasulo.html)
- [Verilator installation documentation](https://verilator.org/guide/latest/install.html)
- [Homebrew: Icarus Verilog](https://formulae.brew.sh/formula/icarus-verilog)
