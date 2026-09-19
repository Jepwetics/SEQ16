# SPDX-License-Identifier: Apache-2.0
"""
Tests for the SEQ16 sequencer.

Run them with:   cd test && make
Waveforms land in test/tb.vcd, open that with GTKWave.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

# ui_in bit positions
SCK = 0
MOSI = 1
CSN = 2
RUN = 3
PIN0 = 4
PIN1 = 5
PIN2 = 6
PIN3 = 7

# Opcodes
NOP, OUTL, OUTH, WAIT, JMP, JIF, JIFN, LDL, LOOP, PSCL, HALT = range(11)


def enc(op, imm=0):
    """Encode one 12-bit instruction."""
    return ((op & 0xF) << 8) | (imm & 0xFF)


class Pins:
    """Small helper that keeps track of the ui_in value."""

    def __init__(self, dut):
        self.dut = dut
        self.value = 1 << CSN  # CS_N idles high, everything else low
        dut.ui_in.value = self.value

    def set(self, bit, level):
        if level:
            self.value |= 1 << bit
        else:
            self.value &= ~(1 << bit)
        self.dut.ui_in.value = self.value


async def reset(dut):
    dut.ena.value = 1
    dut.uio_in.value = 0
    pins = Pins(dut)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    return pins


async def load_program(dut, pins, words):
    """Shift a list of 12-bit instructions in over the SPI-like port."""
    pins.set(RUN, 0)  # core stays in reset while loading
    await ClockCycles(dut.clk, 3)

    pins.set(CSN, 0)
    await ClockCycles(dut.clk, 4)

    for word in words:
        for i in range(11, -1, -1):
            pins.set(MOSI, (word >> i) & 1)
            pins.set(SCK, 0)
            await ClockCycles(dut.clk, 4)
            pins.set(SCK, 1)
            await ClockCycles(dut.clk, 4)

    pins.set(SCK, 0)
    await ClockCycles(dut.clk, 4)
    pins.set(CSN, 1)
    await ClockCycles(dut.clk, 4)


async def start(dut, pins):
    pins.set(RUN, 1)
    await ClockCycles(dut.clk, 4)  # let the synchronisers catch up


@cocotb.test()
async def test_reset_clears_outputs(dut):
    """After reset, with RUN low, both output ports read zero."""
    dut._log.info("start")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset(dut)

    assert dut.uo_out.value == 0
    assert dut.uio_out.value == 0
    # All bidirectional pins are configured as outputs
    assert dut.uio_oe.value == 0xFF


@cocotb.test()
async def test_outl_outh_halt(dut):
    """OUTL and OUTH drive the two output ports, then HALT freezes them."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    pins = await reset(dut)

    await load_program(dut, pins, [
        enc(OUTL, 0xA5),
        enc(OUTH, 0x3C),
        enc(HALT),
    ])
    await start(dut, pins)
    await ClockCycles(dut.clk, 10)

    assert dut.uo_out.value == 0xA5, f"uo_out = {dut.uo_out.value}"
    assert dut.uio_out.value == 0x3C, f"uio_out = {dut.uio_out.value}"

    # Halted means halted: nothing changes no matter how long we wait
    await ClockCycles(dut.clk, 200)
    assert dut.uo_out.value == 0xA5
    assert dut.uio_out.value == 0x3C


@cocotb.test()
async def test_run_low_resets_core(dut):
    """Dropping RUN clears the outputs and rewinds to address 0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    pins = await reset(dut)

    await load_program(dut, pins, [enc(OUTL, 0xFF), enc(HALT)])
    await start(dut, pins)
    await ClockCycles(dut.clk, 10)
    assert dut.uo_out.value == 0xFF

    pins.set(RUN, 0)
    await ClockCycles(dut.clk, 6)
    assert dut.uo_out.value == 0x00

    # And it restarts cleanly from the same program
    pins.set(RUN, 1)
    await ClockCycles(dut.clk, 10)
    assert dut.uo_out.value == 0xFF


@cocotb.test()
async def test_wait_timing(dut):
    """WAIT n holds for the expected number of cycles at PSCL 0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    pins = await reset(dut)

    n = 3
    await load_program(dut, pins, [
        enc(PSCL, 0),      # tick every clock cycle
        enc(OUTL, 0x01),
        enc(WAIT, n),
        enc(OUTL, 0x02),
        enc(HALT),
    ])
    await start(dut, pins)

    # Wait until the first value appears, then count until the second
    while dut.uo_out.value != 0x01:
        await RisingEdge(dut.clk)

    cycles = 0
    while dut.uo_out.value != 0x02:
        await RisingEdge(dut.clk)
        cycles += 1

    expected = n + 3
    assert cycles == expected, f"WAIT {n} took {cycles} cycles, expected {expected}"


@cocotb.test()
async def test_prescaler_slows_wait(dut):
    """A bigger PSCL value makes the same WAIT take proportionally longer."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    durations = {}
    for pscl in (0, 2):
        pins = await reset(dut)
        await load_program(dut, pins, [
            enc(PSCL, pscl),
            enc(OUTL, 0x01),
            enc(WAIT, 3),
            enc(OUTL, 0x02),
            enc(HALT),
        ])
        await start(dut, pins)

        while dut.uo_out.value != 0x01:
            await RisingEdge(dut.clk)
        cycles = 0
        while dut.uo_out.value != 0x02:
            await RisingEdge(dut.clk)
            cycles += 1
        durations[pscl] = cycles

    dut._log.info(f"durations: {durations}")
    # WAIT 3 at PSCL 0 takes 6 cycles; at PSCL 2 each tick is 4 cycles
    assert durations[2] >= durations[0] * 2, (
        f"prescaler had little effect: {durations}"
    )


@cocotb.test()
async def test_jump_loops_forever(dut):
    """JMP makes a program repeat."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    pins = await reset(dut)

    await load_program(dut, pins, [
        enc(PSCL, 0),
        enc(OUTL, 0x11),
        enc(WAIT, 2),
        enc(OUTL, 0x22),
        enc(WAIT, 2),
        enc(JMP, 1),
    ])
    await start(dut, pins)

    seen = set()
    for _ in range(200):
        await RisingEdge(dut.clk)
        seen.add(int(dut.uo_out.value))

    assert 0x11 in seen and 0x22 in seen, f"saw {seen}"


@cocotb.test()
async def test_jif_branches_on_input(dut):
    """JIF takes the branch only while the selected input pin is high."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    pins = await reset(dut)

    # addr 0: PSCL 0
    # addr 1: JIF pin0 -> 3
    # addr 2: OUTL 0xAA ; HALT   (pin low path)
    # addr 4: OUTL 0x55 ; HALT   (pin high path)
    await load_program(dut, pins, [
        enc(PSCL, 0),
        enc(JIF, (0 << 4) | 4),
        enc(OUTL, 0xAA),
        enc(HALT),
        enc(OUTL, 0x55),
        enc(HALT),
    ])

    pins.set(PIN0, 0)
    await start(dut, pins)
    await ClockCycles(dut.clk, 20)
    assert dut.uo_out.value == 0xAA, "pin low should fall through"

    # Now rerun with the pin high
    pins.set(RUN, 0)
    pins.set(PIN0, 1)
    await ClockCycles(dut.clk, 6)
    pins.set(RUN, 1)
    await ClockCycles(dut.clk, 20)
    assert dut.uo_out.value == 0x55, "pin high should take the branch"


@cocotb.test()
async def test_loop_counter(dut):
    """LDL + LOOP repeats a block a fixed number of times."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    pins = await reset(dut)

    # Toggle the output 3 extra times, then fall through and halt with 0xFF
    await load_program(dut, pins, [
        enc(PSCL, 0),
        enc(LDL, 3),
        enc(OUTL, 0x01),     # addr 2: body
        enc(OUTL, 0x00),
        enc(LOOP, 2),
        enc(OUTL, 0xFF),
        enc(HALT),
    ])
    await start(dut, pins)
    await ClockCycles(dut.clk, 100)

    assert dut.uo_out.value == 0xFF, (
        f"loop did not terminate, uo_out = {dut.uo_out.value}"
    )


@cocotb.test()
async def test_traffic_light_sequence(dut):
    """The real traffic-light program cycles through all four phases."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    pins = await reset(dut)

    A_GREEN = 0b00001100
    A_YELLOW = 0b00001010
    B_GREEN = 0b00100001
    B_YELLOW = 0b00010001

    await load_program(dut, pins, [
        enc(PSCL, 0),            # fast, so the test finishes quickly
        enc(OUTL, A_GREEN),      # addr 1
        enc(WAIT, 9),
        enc(OUTL, A_YELLOW),
        enc(WAIT, 4),
        enc(OUTL, B_GREEN),
        enc(WAIT, 9),
        enc(OUTL, B_YELLOW),
        enc(WAIT, 4),
        enc(JMP, 1),
    ])
    await start(dut, pins)

    # Record the order phases appear in
    order = []
    last = None
    for _ in range(400):
        await RisingEdge(dut.clk)
        val = int(dut.uo_out.value)
        if val != last:
            order.append(val)
            last = val

    expected = [A_GREEN, A_YELLOW, B_GREEN, B_YELLOW]
    # Find the first full cycle in what we recorded
    assert A_GREEN in order, f"never saw A green, got {order}"
    i = order.index(A_GREEN)
    got = order[i:i + 4]
    assert got == expected, f"phase order was {got}, expected {expected}"

    # Green and red must never be on together for one direction
    for val in order:
        assert not (val & 0b001) or not (val & 0b100), "A red and green together"
        assert not (val & 0b001000) or not (val & 0b100000), "B red and green together"
