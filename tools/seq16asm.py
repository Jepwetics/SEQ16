#!/usr/bin/env python3
"""
seq16asm - a tiny assembler for the SEQ16B sequencer.

Usage:
    python3 seq16asm.py program.s

Prints the assembled 10-bit words and a Python list you can paste into
the MicroPython loader.

Syntax (one instruction per line, # starts a comment):

    label:              name the next instruction
    OUTA  <0-255>       drive port A (uo_out, 8 pins)
    OUTB  <0-255>       drive port B (uio_out, 8 pins)
    WAIT  <0-255>       pause for (n+1) ticks
    JMP   <label|0-15>  jump
    JIN0  <label|0-15>  jump if input pin IN0 (ui_in[4]) is HIGH
    JIN1  <label|0-15>  jump if input pin IN1 (ui_in[5]) is HIGH
    HALT                stop, holding the current outputs

Numbers may be decimal (10), hex (0x0A) or binary (0b1010).

The chip holds 16 instructions. The program counter wraps from 15 back
to 0 by itself, so a program with exactly 16 instructions loops with no
JMP. A shorter program must end with JMP or HALT, otherwise it would run
on into memory you never loaded.
"""

import re
import sys

MAX_WORDS = 16

OP_OUTA, OP_WAIT, OP_JMP, OP_OUTB = 0, 1, 2, 3
C_ALWAYS, C_IN0, C_IN1, C_HALT = 0, 1, 2, 3

JUMPS = {"JMP": C_ALWAYS, "JIN0": C_IN0, "JIN1": C_IN1}


def parse_number(tok):
    try:
        return int(tok.strip(), 0)
    except ValueError:
        raise SyntaxError(f"not a number: {tok.strip()!r}")


def assemble(text):
    lines, labels = [], {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#")[0].strip()
        while line:
            m = re.match(r"^([A-Za-z_]\w*)\s*:\s*", line)
            if not m:
                break
            name = m.group(1)
            if name in labels:
                raise SyntaxError(f"line {lineno}: duplicate label {name!r}")
            labels[name] = len(lines)
            line = line[m.end():].strip()
        if line:
            lines.append((lineno, line))

    if len(lines) > MAX_WORDS:
        raise SyntaxError(
            f"program is {len(lines)} instructions, the limit is {MAX_WORDS}"
        )

    def resolve(tok, lineno):
        tok = tok.strip()
        if tok in labels:
            return labels[tok]
        try:
            value = parse_number(tok)
        except SyntaxError:
            raise SyntaxError(f"line {lineno}: unknown label or number {tok!r}")
        return value

    words, mnemonics = [], []
    for lineno, line in lines:
        parts = line.split(None, 1)
        mnem = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""
        mnemonics.append(mnem)

        if mnem in ("OUTA", "OUTB", "WAIT"):
            imm = parse_number(args)
            if not 0 <= imm <= 255:
                raise SyntaxError(f"line {lineno}: {mnem} needs 0-255")
            op = {"OUTA": OP_OUTA, "OUTB": OP_OUTB, "WAIT": OP_WAIT}[mnem]
            word = (op << 8) | imm
        elif mnem in JUMPS:
            target = resolve(args, lineno)
            if not 0 <= target < MAX_WORDS:
                raise SyntaxError(f"line {lineno}: address must be 0-{MAX_WORDS - 1}")
            word = (OP_JMP << 8) | (JUMPS[mnem] << 6) | target
        elif mnem == "HALT":
            if args:
                raise SyntaxError(f"line {lineno}: HALT takes no argument")
            word = (OP_JMP << 8) | (C_HALT << 6)
        else:
            raise SyntaxError(f"line {lineno}: unknown instruction {mnem!r}")
        words.append(word)

    if 0 < len(words) < MAX_WORDS and mnemonics[-1] not in ("JMP", "HALT"):
        raise SyntaxError(
            f"program has {len(words)} instructions, so it must end with JMP or "
            "HALT (or fill all 16 slots so it wraps). Otherwise it runs on into "
            "memory you never loaded."
        )

    return words, lines


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    with open(sys.argv[1]) as f:
        text = f.read()
    try:
        words, lines = assemble(text)
    except SyntaxError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    print(f"{len(words)} instruction(s), {MAX_WORDS - len(words)} slot(s) free\n")
    print("addr  hex    binary       source")
    for addr, (word, (_, src)) in enumerate(zip(words, lines)):
        print(f" {addr:2d}   0x{word:03X}  {word:010b}   {src}")
    print("\nPaste into MicroPython:")
    print("program = [" + ", ".join(f"0x{w:03X}" for w in words) + "]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
