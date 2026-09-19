/*
 * Copyright (c) 2026 Jet Ryan S. Meneses
 *
 * SEQ16 - a tiny programmable output sequencer
 * A 16-instruction programmable state machine. You shift a program in
 * over a simple SPI-like interface, raise RUN, and it drives 16 output
 * pins according to that program.
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none
 
module tt_um_jet_seq16 (
    input  wire [7:0] ui_in,    // dedicated inputs
    output wire [7:0] uo_out,   // dedicated outputs
    input  wire [7:0] uio_in,   // bidirectional: input path (unused)
    output wire [7:0] uio_out,  // bidirectional: output path
    output wire [7:0] uio_oe,   // bidirectional: 1 = drive as output
    input  wire       ena,      // always 1 when the design is selected
    input  wire       clk,      // clock
    input  wire       rst_n     // reset, active low
);
 
  // --------------------------------------------------------------------
  // Input synchronisers.
  // ui_in comes from the outside world and can change at any moment, so
  // we pass every input through two flip-flops before using it. This
  // avoids metastability. Standard practice, cheap, worth it.
  // --------------------------------------------------------------------
  reg [7:0] sync0, sync1;
 
  always @(posedge clk) begin
    if (!rst_n) begin
      sync0 <= 8'b0000_0100;  // CS_N idles high
      sync1 <= 8'b0000_0100;
    end else begin
      sync0 <= ui_in;
      sync1 <= sync0;
    end
  end
 
  wire       sck  = sync1[0];  // program clock
  wire       mosi = sync1[1];  // program data
  wire       csn  = sync1[2];  // program chip-select, active low
  wire       run  = sync1[3];  // 1 = execute, 0 = reset the core
  wire [3:0] pins = sync1[7:4];  // 4 general inputs the program can test
 
  // Edge detectors for the loader
  reg sck_d, csn_d;
  always @(posedge clk) begin
    if (!rst_n) begin
      sck_d <= 1'b0;
      csn_d <= 1'b1;
    end else begin
      sck_d <= sck;
      csn_d <= csn;
    end
  end
 
  wire sck_rise = sck & ~sck_d;
  wire csn_fall = ~csn & csn_d;
 
  // --------------------------------------------------------------------
  // Program memory and the loader.
  //
  // 16 words x 12 bits. Pull CS_N low, then clock 12 bits per
  // instruction on the rising edge of SCK, most significant bit first.
  // The write address starts at 0 and auto-increments, so you just shift
  // in your whole program back to back and raise CS_N when done.
  // --------------------------------------------------------------------
  reg [11:0] pmem [0:15];
  reg [10:0] shreg;  // holds the 11 bits shifted in so far; the 12th is MOSI
  reg [3:0]  bitcnt;
  reg [3:0]  ldaddr;
 
  wire [11:0] shreg_next = {shreg[10:0], mosi};
  wire        word_done  = (bitcnt == 4'd11);
 
  always @(posedge clk) begin
    if (!rst_n) begin
      shreg  <= 11'd0;
      bitcnt <= 4'd0;
      ldaddr <= 4'd0;
    end else if (csn_fall) begin
      // A new load session starts at address 0
      bitcnt <= 4'd0;
      ldaddr <= 4'd0;
    end else if (!csn && sck_rise) begin
      shreg <= shreg_next[10:0];
      if (word_done) begin
        pmem[ldaddr] <= shreg_next;
        ldaddr       <= ldaddr + 4'd1;
        bitcnt       <= 4'd0;
      end else begin
        bitcnt <= bitcnt + 4'd1;
      end
    end
  end
 
  // --------------------------------------------------------------------
  // Prescaler.
  //
  // Generates a slow "tick" used by the WAIT instruction. PSCL n makes
  // one tick every 2^n clock cycles, so WAIT can span anything from one
  // clock up to about 8 million.
  // --------------------------------------------------------------------
  reg  [15:0] ps_cnt;
  reg  [3:0]  ps_sel;
 
  wire [15:0] ps_mask = (16'd1 << ps_sel) - 16'd1;
  wire        tick    = (ps_cnt == ps_mask);
 
  always @(posedge clk) begin
    if (!rst_n) ps_cnt <= 16'd0;
    else        ps_cnt <= tick ? 16'd0 : (ps_cnt + 16'd1);
  end
 
  // --------------------------------------------------------------------
  // The core.
  // --------------------------------------------------------------------
  reg [3:0] pc;        // program counter
  reg [7:0] wait_cnt;  // ticks remaining in a WAIT
  reg [7:0] loop_cnt;  // loop counter for LDL / LOOP
  reg [7:0] outl;      // value on uo_out
  reg [7:0] outh;      // value on uio_out
  reg       waiting;
  reg       halted;
 
  wire [11:0] ir  = pmem[pc];
  wire [3:0]  op  = ir[11:8];
  wire [7:0]  imm = ir[7:0];
 
  // Opcode names
  localparam OP_NOP  = 4'h0;
  localparam OP_OUTL = 4'h1;
  localparam OP_OUTH = 4'h2;
  localparam OP_WAIT = 4'h3;
  localparam OP_JMP  = 4'h4;
  localparam OP_JIF  = 4'h5;
  localparam OP_JIFN = 4'h6;
  localparam OP_LDL  = 4'h7;
  localparam OP_LOOP = 4'h8;
  localparam OP_PSCL = 4'h9;
  localparam OP_HALT = 4'hA;
 
  wire sel_pin = pins[imm[5:4]];
 
  always @(posedge clk) begin
    if (!rst_n || !run) begin
      // RUN low holds the core in reset. Load your program while RUN is
      // low, then raise it to start execution from address 0.
      pc       <= 4'd0;
      wait_cnt <= 8'd0;
      loop_cnt <= 8'd0;
      outl     <= 8'd0;
      outh     <= 8'd0;
      ps_sel   <= 4'd0;
      waiting  <= 1'b0;
      halted   <= 1'b0;
    end else if (halted) begin
      // stay put, outputs hold their last value
      halted <= 1'b1;
    end else if (waiting) begin
      if (tick) begin
        if (wait_cnt == 8'd0) begin
          waiting <= 1'b0;
          pc      <= pc + 4'd1;
        end else begin
          wait_cnt <= wait_cnt - 8'd1;
        end
      end
    end else begin
      case (op)
        OP_NOP:  pc <= pc + 4'd1;
        OP_OUTL: begin outl <= imm; pc <= pc + 4'd1; end
        OP_OUTH: begin outh <= imm; pc <= pc + 4'd1; end
        OP_WAIT: begin wait_cnt <= imm; waiting <= 1'b1; end
        OP_JMP:  pc <= imm[3:0];
        OP_JIF:  pc <= sel_pin ? imm[3:0] : (pc + 4'd1);
        OP_JIFN: pc <= sel_pin ? (pc + 4'd1) : imm[3:0];
        OP_LDL:  begin loop_cnt <= imm; pc <= pc + 4'd1; end
        OP_LOOP: begin
          if (loop_cnt != 8'd0) begin
            loop_cnt <= loop_cnt - 8'd1;
            pc       <= imm[3:0];
          end else begin
            pc <= pc + 4'd1;
          end
        end
        OP_PSCL: begin ps_sel <= imm[3:0]; pc <= pc + 4'd1; end
        OP_HALT: halted <= 1'b1;
        default: pc <= pc + 4'd1;  // NOP and anything undefined
      endcase
    end
  end
 
  // --------------------------------------------------------------------
  // Outputs
  // --------------------------------------------------------------------
  assign uo_out  = outl;
  assign uio_out = outh;
  assign uio_oe  = 8'hFF;  // all 8 bidirectional pins used as outputs
 
  // Tie off unused inputs so the linter stays quiet
  wire _unused = &{ena, uio_in, 1'b0};
 
endmodule
