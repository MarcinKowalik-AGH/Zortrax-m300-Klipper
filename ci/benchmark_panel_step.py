#!/usr/bin/env python3
"""Count instructions in selected M300 F103 firmware paths using emulated GPIO."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from struct import pack, unpack
import subprocess
import tempfile

from unicorn import Uc, UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_MCLASS, UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP


FLASH = 0x08008000
SRAM = 0x20000000
STOP = 0x08038000
EXTI = 0x40010400
GPIOA, GPIOB, GPIOC, GPIOE = 0x40010800, 0x40010c00, 0x40011000, 0x40011800
CYCCNT = 0xe0001004
SCHED_SHUTDOWN_STATUS = 10  # Offset in the pinned 32-bit Klipper SchedStatus.


def measure(elf):
    symbols = {}
    for line in subprocess.check_output(['arm-none-eabi-nm', str(elf)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            address, _, name = parts
            symbols[name] = int(address, 16)

    def symbol(name):
        addresses = [addr for key, addr in symbols.items()
                     if key == name or key.startswith(name + '.lto_priv.')]
        if len(addresses) != 1:
            raise ValueError(f'Expected one firmware symbol for {name}: {addresses}')
        return addresses[0]

    with tempfile.TemporaryDirectory(prefix='m300-panel-step-') as temp:
        raw = Path(temp) / 'firmware.bin'
        subprocess.run(['arm-none-eabi-objcopy', '-O', 'binary', str(elf), str(raw)], check=True)
        image = raw.read_bytes()
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    cpu.mem_map(FLASH, 0x31000)
    cpu.mem_write(FLASH, image)
    cpu.mem_map(SRAM, 0x5000)
    cpu.mem_map(0x40010000, 0x2000)
    cpu.mem_map(0xe0001000, 0x1000)
    instructions = 0

    def count_instruction(_cpu, _address, _size, _user_data):
        nonlocal instructions
        instructions += 1

    cpu.hook_add(UC_HOOK_CODE, count_instruction)

    def word(address, value):
        cpu.mem_write(address, pack('<I', value & 0xffffffff))

    def read_word(address):
        return unpack('<I', cpu.mem_read(address, 4))[0]

    def byte(name, value):
        cpu.mem_write(symbol(name), bytes([value & 255]))

    def call(name, r0=0, r1=0):
        nonlocal instructions
        instructions = 0
        for register, value in ((UC_ARM_REG_R0, r0), (UC_ARM_REG_R1, r1),
                                (UC_ARM_REG_SP, SRAM + 0x4ff0), (UC_ARM_REG_LR, STOP | 1)):
            cpu.reg_write(register, value)
        cpu.emu_start(symbol(name) | 1, STOP, count=1024)
        assert cpu.reg_read(UC_ARM_REG_PC) == STOP, name
        return instructions

    byte('panel_configured', 1)
    byte('panel_nav_enabled', 1)
    byte('nav_steps', 4)
    quadrature = (0, 1, -1, 0, -1, 0, 0, 1, 1, 0, 0, -1, 0, -1, 1, 0)
    counts = {key: [] for key in ('same_level', 'valid_edge', 'commit_detent', 'invalid_jump')}
    for previous in range(4):
        for current in range(4):
            direction = quadrature[previous * 4 + current]
            for partial in (-3, 0, 3):
                byte('last_ab', previous)
                byte('nav_partial', partial)
                word(symbol('position'), 0)
                word(symbol('nav_position'), 0)
                word(symbol('invalid_transitions'), 0)
                word(EXTI + 0x14, 1 << 7)
                word(GPIOE + 8, current << 7)
                used = call('m300_encoder_irq')
                invalid = previous ^ current == 3
                commit = abs(partial + direction) == 4
                assert read_word(symbol('position')) == direction & 0xffffffff
                assert read_word(symbol('nav_position')) == (
                    (4 * direction if commit else 0) & 0xffffffff)
                assert read_word(symbol('invalid_transitions')) == int(invalid)
                expected_partial = 0 if invalid or commit else partial + direction
                assert cpu.mem_read(symbol('nav_partial'), 1)[0] == expected_partial & 255
                kind = ('same_level' if previous == current else 'invalid_jump' if invalid
                        else 'commit_detent' if commit else 'valid_edge')
                counts[kind].append(used)

    # A stable released button before the next heartbeat.
    for name, value in (('pressed', 0), ('candidate', 0), ('debounce_count', 5), ('changed', 0)):
        byte(name, value)
    for name, addr in symbols.items():
        if name == 'poll_ticks' or name.startswith('poll_ticks.lto_priv.'):
            word(addr, 72000)
    word(symbol('heartbeat_ticks'), 18000000)
    word(symbol('last_report'), 0)
    word(GPIOC + 8, 1 << 5)
    word(CYCCNT, 72000)
    timer = symbol('panel_timer')
    word(timer + 8, 72000)
    button_idle = call('panel_event', timer)
    assert cpu.reg_read(UC_ARM_REG_R0) == 1 and read_word(timer + 8) == 144000

    step = {}
    for axis, port, bit in (('X', GPIOB, 1 << 3), ('Y', GPIOB, 1 << 4),
                            ('Z', GPIOB, 1 << 7), ('E', GPIOA, 1)):
        step[axis] = {}
        cases = {'rising': (1, 0, 0, 1, 0, bit),
                 'falling': (1, 0, 0, 1, bit, bit << 16),
                 'unarmed': (0, 0, 0, 1, 0, bit << 16),
                 'fault': (1, 1, 0, 1, 0, bit << 16),
                 'shutdown': (1, 0, 1, 1, 0, bit << 16),
                 'gate_closed': (1, 0, 0, 0, 0, bit << 16)}
        for label, (armed, fault, shutdown, gate, level, expected) in cases.items():
            byte('armed', armed)
            byte('fault', fault)
            byte('gates', gate)
            cpu.mem_write(symbol('SchedStatus') + SCHED_SHUTDOWN_STATUS, bytes([shutdown]))
            word(port + 12, level)
            word(port + 16, 0)
            step[axis][label] = call('gpio_out_toggle_noirq', port, bit)
            assert read_word(port + 16) == expected, (axis, label)

    return {'elf_sha256': sha256(elf.read_bytes()).hexdigest(),
            'unit': 'Emulated instructions in function body, excluding IRQ entry and scheduling.',
            'hardware_cycles_measured': False,
            'encoder_irq': {key: sorted(set(values)) for key, values in counts.items()},
            'encoder_transitions_checked': sum(map(len, counts.values())),
            'panel_idle_poll': button_idle, 'step_gpio_only': step}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = json.dumps(measure(args.elf), indent=2)
    args.output.write_text(result + '\n')
    print(result)


if __name__ == '__main__':
    main()
