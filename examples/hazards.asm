# Long-latency producer, true dependency, WAR, WAW, and independent work.
.reg R1 6
.reg R2 7
.reg R3 100
.reg R4 8
.reg R5 2
.reg R6 20
.reg R7 3
MUL R8, R1, R2
ADD R9, R8, R3
SUB R8, R4, R5
ADD R3, R6, R7
MUL R10, R8, R7
ADD R11, R9, R10
