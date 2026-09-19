<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

SEQ16 is a very small programmable sequencer: a 16-instruction state
machine that drives 16 output pins.

You shift a program into it over a simple SPI-like port, raise the RUN
pin, and it starts executing from address 0. Each instruction either
writes a new pattern to the output pins, pauses for a programmable
length of time, or changes the flow of control based on one of four
input pins.

The point is that the behaviour is not baked into the silicon. One chip
can be a traffic light, a stepper-motor driver, an LED chaser, a test
pattern generator, or a servo pulse source, depending only on the 16
words you load into it.

### Blocks

- **Program memory**: 16 words x 12 bits, written by the loader, read by
  the program counter.
- **Loader**: a shift register clocked by SCK while CS_N is low. Every 12
  bits it writes one instruction and auto-increments the write address.
- **Prescaler**: a 16-bit counter producing a tick every 2^n clock
  cycles, with n set by the PSCL instruction. This is what makes WAIT
  useful across a huge range of clock speeds.
- **Core**: program counter, wait counter, loop counter and two 8-bit
  output registers.

### Instruction set

Every instruction is 12 bits: a 4-bit opcode and an 8-bit operand.

| Opcode | Name | Operand | Effect |
|--------|------|---------|--------|
| 0x0 | NOP  | -                  | do nothing |
| 0x1 | OUTL | 8-bit value        | drive `uo_out` |
| 0x2 | OUTH | 8-bit value        | drive `uio_out` |
| 0x3 | WAIT | count              | pause for (count + 1) prescaler ticks |
| 0x4 | JMP  | address 0-15       | jump |
| 0x5 | JIF  | pin[5:4], addr[3:0] | jump if that input pin is high |
| 0x6 | JIFN | pin[5:4], addr[3:0] | jump if that input pin is low |
| 0x7 | LDL  | count              | load the loop counter |
| 0x8 | LOOP | address 0-15       | if the loop counter is non-zero, decrement it and jump |
| 0x9 | PSCL | n (0-15)           | tick period becomes 2^n clock cycles |
| 0xA | HALT | -                  | stop, holding the current output values |

Undefined opcodes behave as NOP.

### Loading a program

1. Hold RUN low. The core stays in reset while you load.
2. Pull CS_N low. The write address resets to 0.
3. For each instruction, shift 12 bits on the rising edge of SCK, most
   significant bit first. Instructions are written back to back starting
   at address 0.
4. Raise CS_N.
5. Raise RUN. Execution starts at address 0.

Dropping RUN low at any time clears the outputs and rewinds to address 0,
so you can restart a program without reloading it.

## How to test

The easiest way is with the RP2350 on the demo board driving the four
load pins in MicroPython. Shift in a program, raise RUN, and watch the
output pins.

A worked example, the two-direction traffic light, is in
`tools/traffic.s` along with an assembler (`tools/seq16asm.py`) that
turns that source into the words you shift in.

For a quick manual check without any software, load this two
instruction program and confirm that all eight `uo_out` pins go high:
`OUTL 0xFF` (0x1FF), `HALT` (0xA00).

The cocotb test suite in `test/` covers reset behaviour, the loader, WAIT
timing, the prescaler, all branch instructions, the loop counter and a
full traffic-light sequence.

## External hardware

None required. LEDs with series resistors on the output pins make the
behaviour visible. The design is also happy driving a 7-segment display,
motor driver inputs, or anything else that takes logic-level signals.
