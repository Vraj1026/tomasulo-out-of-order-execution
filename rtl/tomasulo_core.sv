`timescale 1ns/1ps
// Integer Tomasulo arithmetic backend. No fetch/decode, memory, or ROB.
// Opcodes: 0 ADD, 1 SUB, 2 MUL. R0 is hardwired to zero.
module tomasulo_core #(
    parameter integer ADD_RS = 3,
    parameter integer MUL_RS = 2,
    parameter integer ADD_LATENCY = 2,
    parameter integer MUL_LATENCY = 5
)(
    input  logic clk,
    input  logic rst_n,
    input  logic issue_valid,
    output logic issue_ready,
    input  logic [1:0] issue_op,
    input  logic [4:0] issue_rd, issue_rs1, issue_rs2,
    // Debug initialization is accepted only while idle, with issue_valid low.
    input  logic init_valid,
    input  logic [4:0] init_addr,
    input  logic [31:0] init_data,
    input  logic [4:0] debug_addr,
    output logic [31:0] debug_data,
    output logic debug_pending,
    output logic idle,
    // CDB signals are sampled on the rising edge when cdb_valid is high.
    output logic cdb_valid,
    output logic [31:0] cdb_tag, cdb_data
);
    localparam integer N = ADD_RS + MUL_RS;
    logic [31:0] regs_q [0:31], regs_d [0:31];
    logic [31:0] rat_q [0:31], rat_d [0:31];
    logic busy_q [0:N-1], busy_d [0:N-1];
    logic running_q [0:N-1], running_d [0:N-1];
    logic complete_q [0:N-1], complete_d [0:N-1];
    logic [1:0] op_q [0:N-1], op_d [0:N-1];
    logic [4:0] rd_q [0:N-1], rd_d [0:N-1];
    logic [31:0] tag_q [0:N-1], tag_d [0:N-1];
    logic [31:0] qj_q [0:N-1], qj_d [0:N-1];
    logic [31:0] qk_q [0:N-1], qk_d [0:N-1];
    logic [31:0] vj_q [0:N-1], vj_d [0:N-1];
    logic [31:0] vk_q [0:N-1], vk_d [0:N-1];
    logic [31:0] result_q [0:N-1], result_d [0:N-1];
    integer remaining_q [0:N-1], remaining_d [0:N-1];
    logic [31:0] next_tag_q, next_tag_d;
    integer cdb_index, add_index, mul_index, free_index;
    logic add_occupied, mul_occupied;

    assign debug_data = regs_q[debug_addr];
    assign debug_pending = rat_q[debug_addr] != 0;

    // All scheduling decisions use q (start-of-cycle) state. Updates go to d.
    always_comb begin
        next_tag_d = next_tag_q;
        for (integer r = 0; r < 32; r = r + 1) begin
            regs_d[r] = regs_q[r];
            rat_d[r] = rat_q[r];
        end
        idle = 1'b1;
        add_occupied = 1'b0;
        mul_occupied = 1'b0;
        for (integer i = 0; i < N; i = i + 1) begin
            busy_d[i] = busy_q[i];
            running_d[i] = running_q[i];
            complete_d[i] = complete_q[i];
            op_d[i] = op_q[i]; rd_d[i] = rd_q[i]; tag_d[i] = tag_q[i];
            qj_d[i] = qj_q[i]; qk_d[i] = qk_q[i];
            vj_d[i] = vj_q[i]; vk_d[i] = vk_q[i];
            result_d[i] = result_q[i]; remaining_d[i] = remaining_q[i];
            if (busy_q[i]) idle = 1'b0;
            if (busy_q[i] && running_q[i]) begin
                if (i < ADD_RS) add_occupied = 1'b1;
                else mul_occupied = 1'b1;
            end
        end
        cdb_index = -1; add_index = -1; mul_index = -1;
        // Oldest sequence tag wins; physical slot order is not age order.
        for (integer i = 0; i < N; i = i + 1) begin
            if (busy_q[i] && complete_q[i]) begin
                if (cdb_index == -1) cdb_index = i;
                else if (tag_q[i] < tag_q[cdb_index]) cdb_index = i;
            end
            if (busy_q[i] && !running_q[i] && !complete_q[i] &&
                qj_q[i] == 0 && qk_q[i] == 0) begin
                if (i < ADD_RS && !add_occupied) begin
                    if (add_index == -1) add_index = i;
                    else if (tag_q[i] < tag_q[add_index]) add_index = i;
                end
                if (i >= ADD_RS && !mul_occupied) begin
                    if (mul_index == -1) mul_index = i;
                    else if (tag_q[i] < tag_q[mul_index]) mul_index = i;
                end
            end
        end
        cdb_valid = rst_n && cdb_index != -1;
        cdb_tag = 0; cdb_data = 0;
        if (cdb_index != -1) begin
            cdb_tag = tag_q[cdb_index]; cdb_data = result_q[cdb_index];
            for (integer r = 1; r < 32; r = r + 1) begin
                if (rat_q[r] == cdb_tag) begin
                    regs_d[r] = cdb_data;
                    rat_d[r] = 0;
                end
            end
            for (integer i = 0; i < N; i = i + 1) begin
                if (busy_q[i] && qj_q[i] == cdb_tag) begin
                    qj_d[i] = 0; vj_d[i] = cdb_data;
                end
                if (busy_q[i] && qk_q[i] == cdb_tag) begin
                    qk_d[i] = 0; vk_d[i] = cdb_data;
                end
            end
            busy_d[cdb_index] = 1'b0;
            complete_d[cdb_index] = 1'b0;
        end
        for (integer i = 0; i < N; i = i + 1) begin
            if (busy_q[i] && running_q[i]) begin
                remaining_d[i] = remaining_q[i] - 1;
                if (remaining_q[i] == 1) begin
                    running_d[i] = 1'b0;
                    complete_d[i] = 1'b1;
                end
            end
            if (i == add_index || i == mul_index) begin
                case (op_q[i])
                    2'd0: result_d[i] = vj_q[i] + vk_q[i];
                    2'd1: result_d[i] = vj_q[i] - vk_q[i];
                    2'd2: result_d[i] = vj_q[i] * vk_q[i];
                    default: result_d[i] = 0;
                endcase
                if (i < ADD_RS) remaining_d[i] = ADD_LATENCY - 1;
                else remaining_d[i] = MUL_LATENCY - 1;
                running_d[i] = remaining_d[i] != 0;
                complete_d[i] = remaining_d[i] == 0;
            end
        end
        // CDB may free a slot and supply an issue operand on the same edge.
        free_index = -1;
        for (integer i = 0; i < N; i = i + 1) begin
            if (!busy_d[i] && free_index == -1 &&
                ((issue_op < 2 && i < ADD_RS) || (issue_op == 2 && i >= ADD_RS)))
                free_index = i;
        end
        issue_ready = rst_n && !init_valid && free_index != -1 && issue_op != 2'd3;
        if (init_valid && idle && !issue_valid && init_addr != 0) regs_d[init_addr] = init_data;
        if (issue_valid && issue_ready) begin
            busy_d[free_index] = 1'b1;
            running_d[free_index] = 1'b0; complete_d[free_index] = 1'b0;
            op_d[free_index] = issue_op; rd_d[free_index] = issue_rd;
            tag_d[free_index] = next_tag_q;
            // Read both sources before modifying RAT[destination], including
            // ADD R1,R1,R2 and simultaneous CDB/rename of the same register.
            qj_d[free_index] = rat_d[issue_rs1];
            qk_d[free_index] = rat_d[issue_rs2];
            vj_d[free_index] = regs_d[issue_rs1];
            vk_d[free_index] = regs_d[issue_rs2];
            remaining_d[free_index] = 0; result_d[free_index] = 0;
            if (issue_rd != 0) rat_d[issue_rd] = next_tag_q;
            next_tag_d = next_tag_q + 1;
        end
        regs_d[0] = 0; rat_d[0] = 0;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            next_tag_q <= 1;
            for (integer r = 0; r < 32; r = r + 1) begin
                regs_q[r] <= 0; rat_q[r] <= 0;
            end
            for (integer i = 0; i < N; i = i + 1) begin
                busy_q[i] <= 0; running_q[i] <= 0; complete_q[i] <= 0;
                op_q[i] <= 0; rd_q[i] <= 0; tag_q[i] <= 0;
                qj_q[i] <= 0; qk_q[i] <= 0; vj_q[i] <= 0; vk_q[i] <= 0;
                result_q[i] <= 0; remaining_q[i] <= 0;
            end
        end else begin
            next_tag_q <= next_tag_d;
            for (integer r = 0; r < 32; r = r + 1) begin
                regs_q[r] <= regs_d[r]; rat_q[r] <= rat_d[r];
            end
            for (integer i = 0; i < N; i = i + 1) begin
                busy_q[i] <= busy_d[i]; running_q[i] <= running_d[i]; complete_q[i] <= complete_d[i];
                op_q[i] <= op_d[i]; rd_q[i] <= rd_d[i]; tag_q[i] <= tag_d[i];
                qj_q[i] <= qj_d[i]; qk_q[i] <= qk_d[i]; vj_q[i] <= vj_d[i]; vk_q[i] <= vk_d[i];
                result_q[i] <= result_d[i]; remaining_q[i] <= remaining_d[i];
            end
        end
    end
endmodule
