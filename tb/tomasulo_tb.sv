`timescale 1ns/1ps
module tomasulo_tb #(
    parameter integer ADD_RS = 3, MUL_RS = 2,
    parameter integer ADD_LATENCY = 2, MUL_LATENCY = 5
);
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, issue_valid = 0, issue_ready;
    logic [1:0] issue_op = 0;
    logic [4:0] issue_rd = 0, issue_rs1 = 0, issue_rs2 = 0;
    logic init_valid = 0;
    logic [4:0] init_addr = 0, debug_addr = 0;
    logic [31:0] init_data = 0, debug_data;
    logic debug_pending, idle, cdb_valid;
    logic [31:0] cdb_tag, cdb_data;
    tomasulo_core #(.ADD_RS(ADD_RS), .MUL_RS(MUL_RS),
        .ADD_LATENCY(ADD_LATENCY), .MUL_LATENCY(MUL_LATENCY)) dut(.*);
    integer count, cycles, fd, rc, issued, expected_valid, expected_tag;
    integer op [0:4095], rd [0:4095], rs1 [0:4095], rs2 [0:4095], issue_cycle [0:4095];
    logic [31:0] initial_regs [0:31], final_regs [0:31], expected_data;
    string filename, wavefile;
    initial begin
        if (!$value$plusargs("CASE=%s", filename)) $fatal(1, "Missing +CASE=path");
        if ($value$plusargs("WAVES=%s", wavefile)) begin
            $dumpfile(wavefile);
            $dumpvars(0, tomasulo_tb);
        end
        fd = $fopen(filename, "r");
        if (fd == 0) $fatal(1, "Cannot open case %s", filename);
        rc = $fscanf(fd, "%d %d", count, cycles);
        if (rc != 2 || count > 4096) $fatal(1, "Bad case header");
        for (integer r = 0; r < 32; r++) begin
            rc = $fscanf(fd, "%h", initial_regs[r]);
            if (rc != 1) $fatal(1, "Bad register input");
        end
        for (integer i = 0; i < count; i++) begin
            rc = $fscanf(fd, "%d %d %d %d %d", op[i], rd[i], rs1[i], rs2[i], issue_cycle[i]);
            if (rc != 5) $fatal(1, "Bad instruction input");
        end
        repeat (2) @(negedge clk);
        rst_n = 1;
        for (integer r = 1; r < 32; r++) begin
            init_valid = 1; init_addr = 5'(r); init_data = initial_regs[r];
            @(negedge clk);
        end
        init_valid = 0;
        issued = 0;
        for (integer cycle = 1; cycle <= cycles; cycle++) begin
            issue_valid = issued < count;
            if (issued < count) begin
                issue_op = 2'(op[issued]); issue_rd = 5'(rd[issued]);
                issue_rs1 = 5'(rs1[issued]); issue_rs2 = 5'(rs2[issued]);
            end
            rc = $fscanf(fd, "%d %d %h", expected_valid, expected_tag, expected_data);
            if (rc != 3) $fatal(1, "Bad CDB expectation");
            @(posedge clk);
            if (cdb_valid !== (expected_valid != 0))
                $fatal(1, "Cycle %0d: CDB valid mismatch", cycle);
            if ((expected_valid != 0) && (cdb_tag !== 32'(expected_tag) || cdb_data !== expected_data))
                $fatal(1, "Cycle %0d: expected tag=%0d data=%h, got tag=%0d data=%h",
                    cycle, expected_tag, expected_data, cdb_tag, cdb_data);
            if (issue_valid && issue_ready) begin
                if (issue_cycle[issued] != cycle) $fatal(1, "Issue cycle mismatch at I%0d", issued+1);
                issued++;
            end else if (issued < count && issue_cycle[issued] <= cycle)
                $fatal(1, "Unexpected issue stall at cycle %0d", cycle);
            @(negedge clk);
        end
        issue_valid = 0;
        if (issued != count || !idle) $fatal(1, "Did not drain");
        for (integer r = 0; r < 32; r++) begin
            rc = $fscanf(fd, "%h", final_regs[r]);
            if (rc != 1) $fatal(1, "Bad final register input");
            debug_addr = 5'(r);
            #1;
            if (debug_data !== final_regs[r] || debug_pending)
                $fatal(1, "R%0d: expected %h, got %h pending=%b", r, final_regs[r], debug_data, debug_pending);
        end
        // Reset must discard in-flight work, clear registers, and restart tags.
        @(negedge clk);
        issue_valid = 1; issue_op = 2; issue_rd = 1; issue_rs1 = 2; issue_rs2 = 3;
        @(negedge clk);
        issue_valid = 0; rst_n = 0;
        @(negedge clk);
        rst_n = 1;
        #1;
        if (!idle || cdb_valid || dut.next_tag_q != 1) $fatal(1, "Reset failed");
        for (integer r = 0; r < 32; r++) begin
            debug_addr = 5'(r); #1;
            if (debug_data !== 0 || debug_pending) $fatal(1, "Reset register failure");
        end
        $fclose(fd);
        $display("PASS %s (%0d instructions, %0d cycles)", filename, count, cycles);
        $finish;
    end
    initial begin
        #10000000;
        $fatal(1, "Testbench watchdog timeout");
    end
endmodule
