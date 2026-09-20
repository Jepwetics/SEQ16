<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

SEQ16B is a small programmable sequencer: a 16-instruction state machine
that drives 16 output pins.

You shift a program into it over a simple SPI-like port, raise the RUN
pin, and it starts executing from address 0. Each instruction either
writes a new pattern to one of the two output ports, pauses for a
programmable length of time, or jumps, optionally depending on one of
two input pins.

The behaviour is not baked into the silicon. One chip can be a traffic
light, a stepper-motor driver, an LED chaser, a test pattern generator,
or a servo pulse source, depending only on the 16 words you load.

### Blocks

- **Program memory**: 16 words x 10 bits, written by the loader, read by
  the program counter.
- **Loader**: a shift register clocked by SCK while CS_N is low. Every 10
  bits it writes one instruction and auto-increments the write address.
- **Tick generator**: a 12-bit counter that makes one tick every 1, 16,
  256 or 4096 clock cycles, chosen by pins ui[7:6]. WAIT counts ticks.
- **Core**: a 4-bit program counter, an 8-bit wait counter and two 8-bit
  output registers.

### Instruction set

Every instruction is 10 bits: a 2-bit opcode and an 8-bit operand.

| Opcode | Name | Operand | Effect |
|--------|------|---------|--------|
| 00 | OUTA | 8-bit value | drive port A (`uo_out`) |
| 01 | WAIT | count | pause for (count + 1) ticks |
| 10 | JMP  | cond[7:6], addr[3:0] | jump; see below |
| 11 | OUTB | 8-bit value | drive port B (`uio_out`) |

Jump conditions (operand bits 7:6):

| cond | Behaviour |
|------|-----------|
| 00 | always jump to addr |
| 01 | jump to addr if IN0 (ui[4]) is high, otherwise continue |
| 10 | jump to addr if IN1 (ui[5]) is high, otherwise continue |
| 11 | HALT: stop and hold the current outputs |

The program counter is 4 bits, so it wraps from address 15 back to 0 by
itself. A program that fills all 16 words loops with no JMP at all. A
shorter program must end with a JMP or HALT, otherwise it runs on into
memory that was never loaded.

### Tick speed

| ui[7:6] | Clock cycles per tick |
|---------|-----------------------|
| 00 | 1 |
| 01 | 16 |
| 10 | 256 |
| 11 | 4096 |

With ui[7:6] = 11 and a 4096 Hz clock, one tick is one second, so
`WAIT 9` lasts 10 seconds.

### Loading a program

1. Hold RUN low. The core stays in reset while you load.
2. Pull CS_N low. The write address resets to 0.
3. For each instruction, shift 10 bits on the rising edge of SCK, most
   significant bit first. Instructions are written back to back starting
   at address 0.
4. Raise CS_N.
5. Set ui[7:6] for the tick speed, then raise RUN. Execution starts at
   address 0.

The chip samples SCK, MOSI and CS_N with its own clock, so keep every
pin steady for at least 4 clock cycles per step. In practice, load the
program with a fast clock (for example 1 MHz), then switch to the slow
clock you want for running.

Dropping RUN low at any time clears the outputs and rewinds to address 0,
so you can restart a program without reloading it.

## How to test

The easiest way is with the RP2350 on the demo board driving the load
pins in MicroPython. Shift in a program, raise RUN, and watch the output
pins.

Four worked examples are in `tools/`: a traffic light with a pedestrian
signal, a version that waits for a pedestrian button, an LED chaser and
a stepper-motor half-step driver. The assembler `tools/seq16asm.py`
turns those source files into the words you shift in.

For a quick manual check without any software, load this two instruction
program and confirm that all eight port A pins go high:
`OUTA 0xFF` (0x0FF), `HALT` (0x2C0).

The cocotb test suite in `test/` covers reset behaviour, the loader, both
output ports, WAIT timing, the tick speed select, both conditional jumps,
jumps to the upper half of memory, program counter wraparound and a full
traffic-light sequence.

## External hardware

None required. LEDs with series resistors on the output pins make the
behaviour visible. The design can also drive a 7-segment display, an
H-bridge motor driver, or anything else that takes logic-level signals.
