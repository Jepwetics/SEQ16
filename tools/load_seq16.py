# MicroPython loader for SEQ16B, to run on the RP2350 of the Tiny Tapeout
# demo board.
#
# Copy this onto the board (Thonny works well), edit `program`, and run it.
#
# NOTE: I could not test this against real hardware. The exact names of
# the DemoBoard calls below can differ between SDK versions, so if a line
# errors, check the Tiny Tapeout docs for the current names. Also run
# dir(tt.shuttle) on the board to find your project's exact name.

from ttboard.demoboard import DemoBoard

SCK, MOSI, CSN, RUN = 0, 1, 2, 3
IN0, IN1 = 4, 5
TICK0, TICK1 = 6, 7

# Assembled with tools/seq16asm.py from tools/traffic.s
program = [0x302, 0x00C, 0x109, 0x00A, 0x104, 0x301, 0x021, 0x109,
           0x302, 0x011, 0x104, 0x201]

# Tick speed: 0 = 1 cycle, 1 = 16, 2 = 256, 3 = 4096 clock cycles per tick.
# With speed 3 and a 4096 Hz clock, one tick is one second.
TICK_SPEED = 3
CLOCK_HZ = 4096

# Loading needs a FAST clock. MicroPython changes the pins far quicker
# than a 4096 Hz clock could see, so the chip would miss bits. Load at a
# high clock, then switch to the slow run clock.
LOAD_HZ = 1000000


def setup():
    tt = DemoBoard.get()
    tt.shuttle.tt_um_jet_seq16.enable()
    tt.mode = "ASIC_RP_CONTROL"   # the RP2350 drives the input pins
    tt.reset_project(True)
    tt.reset_project(False)
    return tt


def set_bit(tt, bit, level):
    v = tt.input_byte
    if level:
        v |= 1 << bit
    else:
        v &= ~(1 << bit)
    tt.input_byte = v


def load(tt, words):
    set_bit(tt, RUN, 0)     # hold the core in reset
    set_bit(tt, CSN, 1)
    set_bit(tt, SCK, 0)

    set_bit(tt, CSN, 0)     # start of a load session, address resets to 0
    for word in words:
        for i in range(9, -1, -1):
            set_bit(tt, MOSI, (word >> i) & 1)
            set_bit(tt, SCK, 0)
            set_bit(tt, SCK, 1)
    set_bit(tt, SCK, 0)
    set_bit(tt, CSN, 1)


def run(tt):
    set_bit(tt, TICK0, TICK_SPEED & 1)
    set_bit(tt, TICK1, (TICK_SPEED >> 1) & 1)
    tt.clock_project_PWM(CLOCK_HZ)
    set_bit(tt, RUN, 1)


if __name__ == "__main__":
    tt = setup()
    tt.clock_project_PWM(LOAD_HZ)
    load(tt, program)
    run(tt)
    print("SEQ16B running. Port A:", bin(tt.output_byte))
