# The store waits for R3, and the following load waits for the older store.
.reg R1 64
.reg R2 7
.mem 64 10
.mem 68 3
LD R3, 0(R1)
MUL R4, R3, R2
ST R4, 4(R1)
LD R5, 4(R1)
ADDI R6, R5, -1
ST R6, 8(R1)
