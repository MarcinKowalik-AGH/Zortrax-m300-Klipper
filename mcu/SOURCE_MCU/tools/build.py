#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the M300 M01-M08 MCU from a verified upstream archive. Never flashes."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import zipfile

KIT = Path(__file__).resolve().parents[1]
PIN = 'ee2c6fb6b00b2b5d097ef70d0868df7d74943b51'
ARCHIVE_SHA256 = 'fe4c6a25c370c32f519a008e46e14612ddb116a5ac135146afeee7d0bc4c2bf0'
APP_START = 0x08008000
NVM_START = 0x0803A000
REQUIRED_COMMANDS = ('m300_config ', 'm300_heartbeat', 'm300_arm ',
                     'm300_disarm', 'm300_query', 'm300_oled_',
                     'm300_factory_query', 'm300_factory_info_query', 'm300_uart_query',
                     'm300_local_oled_query', 'm300_oled_host state=',
                     'm300_sd_config ', 'm300_sd_open ', 'm300_sd_read ',
                     'm300_sd_chunk ', 'm300_sd_close ',
                     'm300_panel_release_arm ', 'm300_panel_release_disarm ')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(args, cwd=None, env=None, log=None):
    args = list(map(str, args))
    result = subprocess.run(args, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log:
        log.write('$ ' + ' '.join(args) + '\n' + result.stdout + '\n')
        log.flush()
    if result.returncode:
        print(result.stdout[-12000:], file=sys.stderr)
        raise RuntimeError('Command failed (%d): %s' % (result.returncode, args))
    return result.stdout

def stage(archive, work, fresh=False):
    archive = archive.resolve()
    if sha(archive) != ARCHIVE_SHA256:
        raise ValueError('Wrong upstream archive SHA-256; expected pinned Klipper')
    marker = work / '.m300-build-owner.json'
    if work.exists():
        if not marker.is_file() or json.loads(marker.read_text()).get('archive_sha256') != ARCHIVE_SHA256:
            raise ValueError('Refusing to alter an unowned build directory: ' + str(work))
        if not fresh:
            raise ValueError('Existing private build directory: use --fresh to rebuild from the verified archive; incremental source reuse is disabled')
        shutil.rmtree(work)
    work.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            parts = Path(item.filename).parts
            if not parts or parts[0] != 'klipper-' + PIN:
                raise ValueError('Unexpected upstream archive root')
            rel = Path(*parts[1:])
            if not rel.parts or item.is_dir():
                continue
            if '..' in rel.parts or rel.is_absolute() or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Unsafe archive member')
            target = work / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read(item))
            target.chmod(0o755 if (item.external_attr >> 16) & 0o111 else 0o644)
    marker.write_text(json.dumps({'archive_sha256': ARCHIVE_SHA256,
                                 'upstream_commit': PIN}, indent=2) + '\n')

def read_config(path):
    return dict(line.split('=', 1) for line in Path(path).read_text().splitlines()
                if line.startswith('CONFIG_') and '=' in line)

def check_config(path):
    cfg = read_config(path)
    expected = {'CONFIG_MACH_STM32': 'y', 'CONFIG_MACH_STM32F103': 'y',
                'CONFIG_STM32_FLASH_START_8000': 'y',
                'CONFIG_STM32_CLOCK_REF_8M': 'y',
                'CONFIG_STM32_SERIAL_USART1': 'y'}
    for key, value in expected.items():
        if cfg.get(key) != value:
            raise ValueError('Wrong MCU configuration: ' + key)
    numbers = {'CONFIG_FLASH_APPLICATION_ADDRESS': APP_START,
               'CONFIG_CLOCK_FREQ': 72000000,
               'CONFIG_FLASH_SIZE': 0x10000, 'CONFIG_RAM_SIZE': 0x5000}
    for key, value in numbers.items():
        if int(cfg.get(key, '-1'), 0) != value:
            raise ValueError('Wrong MCU configuration: ' + key)
    if cfg.get('CONFIG_USBSERIAL') == 'y' or cfg.get('CONFIG_MACH_STM32F207') == 'y':
        raise ValueError('Wrong host transport or chip family')
    for feature in ('WANT_SPI', 'WANT_SOFTWARE_SPI', 'WANT_I2C',
                    'WANT_SOFTWARE_I2C', 'WANT_HARD_PWM'):
        if cfg.get('CONFIG_' + feature) == 'y':
            raise ValueError('Unowned generic peripheral enabled: ' + feature)
    return cfg

def validate(work, output, env, log):
    cfg = check_config(work / '.config')
    binary = work / 'out/klipper.bin'
    data = binary.read_bytes()
    if len(data) < 64 or len(data) > int(cfg['CONFIG_FLASH_SIZE'], 0):
        raise ValueError('Application outside conservative linker region')
    if APP_START + len(data) > NVM_START:
        raise ValueError('Application overlaps M300 settings area')
    msp, reset = struct.unpack_from('<II', data)
    if msp != 0x20005000 or not reset & 1 or not APP_START <= (reset & ~1) < APP_START + len(data):
        raise ValueError('Invalid application vector table')
    dictionary = json.loads((work / 'out/klipper.dict').read_text())
    constants = dictionary['config']
    for key, expected in {'M300_ABI': 1, 'M300_MODEL': 'M300_CLASSIC',
                          'M300_FACTORY_ABI': 1, 'M300_FACTORY_HW_ADDRESS': 0x0803f848,
                          'M300_FACTORY_INFO_ABI': 1,
                          'M300_SOFTWARE_PWM_ONLY': 1, 'M300_FAN_POLICY': 3,
                          'M300_LOCAL_COOLING_ABI': 1, 'M300_LOCAL_COOLING_ON_RAW': 314,
                          'M300_LOCAL_COOLING_OFF_RAW': 281,
                          'M300_OUTPUT_MODE': 'SOFTWARE_PWM_ONLY',
                          'M300_SD_ABI': 1, 'M300_SD_READ_ONLY': 1,
                          'M300_SD_MAX_CHUNK': 32, 'M300_SD_TASK_BYTES': 32,
                          'M300_SD_POLL_US': 1000, 'M300_UART_PERSIST_ABI': 1, 'M300_UART_RATE_COUNT': 8,
                          'M300_LOCAL_OLED_ABI': 1, 'M300_OLED_SPI_BURST_ABI': 1,
                          'M300_LOCAL_OLED_STARTUP_FIX': 1,
                          'M300_OLED_HOSTLINK_ABI': 1, 'M300_OLED_HOSTLINK_TIMEOUT_US': 1500000,
                          'M300_OLED_FAST_ABI': 1, 'M300_OLED_FAST_QUEUE': 4,
                          'M300_OLED_FAST_WIRE': 256, 'M300_MCU_RELEASE': '0.13.14.7-PANEL-STOP-UART8',
                          'M300_PANEL_CAPTURE_ABI': 3, 'M300_PANEL_RELEASE_ABI': 1,
                          'M300_PANEL_IRQ_PRIORITY': 3, 'M300_OLED_DMA_IRQ_PRIORITY': 4,
                          'CLOCK_FREQ': 72000000}.items():
        if constants.get(key) != expected:
            raise ValueError('Wrong compiled dictionary constant: ' + key)
    commands = dictionary['commands']
    if 'm300_local_cooling_query' not in commands:
        raise ValueError('Missing autonomous cooling query command')
    if ('m300_factory_state header=%u raw=%c valid=%c revision=%c z_steps=%hu'
            not in dictionary['responses']):
        raise ValueError('Missing or incompatible factory identity response')
    if ('m300_factory_info serial=%u time_valid=%c print_minutes=%u'
            not in dictionary['responses']):
        raise ValueError('Missing or incompatible factory information response')
    for prefix in REQUIRED_COMMANDS:
        if not any(command.startswith(prefix) for command in commands):
            raise ValueError('Missing MCU command prefix: ' + prefix)
    forbidden = ('debug_write ', 'debug_read ', 'config_spi', 'spi_set_bus',
                 'spi_transfer', 'spi_send', 'config_i2c', 'i2c_set_bus',
                 'i2c_read', 'i2c_write', 'config_pwm_out')
    exposed = [command for command in commands
               if any(command.startswith(prefix) for prefix in forbidden)]
    if exposed:
        raise ValueError('Bypass-capable unowned MCU commands present: ' + repr(exposed))
    symbols_text = run(['arm-none-eabi-nm', '-n', work / 'out/klipper.elf'], env=env, log=log)
    symbols = {}
    for line in symbols_text.splitlines():
        parts = line.split()
        if len(parts) == 3:
            try: symbols[parts[2]] = int(parts[0], 16)
            except ValueError: pass
    bss_end = symbols['_bss_end']
    stack_start = symbols['_stack_start']
    if bss_end >= stack_start:
        raise ValueError('Static data overlaps reserved MCU stack')
    report = {'version': '0.13.14.7-PANEL-STOP-UART8',
              'mcu_stage': 'P01_LAB + M04_SD + R9_HOST_LEASE_LOCAL_WAITING', 'upstream_commit': PIN,
              'upstream_archive_sha256': ARCHIVE_SHA256,
              'model': 'M300_CLASSIC', 'abi': 1,
              'application_start': hex(APP_START), 'application_bytes': len(data),
              'application_end_exclusive': hex(APP_START + len(data)),
              'linker_rom_bytes': int(cfg['CONFIG_FLASH_SIZE'], 0),
              'protected_boot_assets_start': hex(NVM_START), 'nvm_start': '0x803e000', 'msp': hex(msp), 'reset_vector': hex(reset),
              'ram_region_bytes': 0x5000,
              'ram_static_end': hex(bss_end), 'stack_start': hex(stack_start),
              'heap_budget_before_stack_bytes': stack_start - bss_end,
              'heap_budget_note': 'Static link budget; not a measured runtime high-water mark',
              'full_arm_link': True, 'physical_mcu_execution': False,
              'unowned_peripheral_and_debug_write_commands_absent': True,
              'physical_hardware_tests': False, 'flashed': False,
              'built_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'files': {}}
    output.mkdir(parents=True, exist_ok=True)
    for name in ['klipper.bin', 'klipper.elf', 'klipper.dict', 'klipper.map']:
        source = work / 'out' / name
        if not source.is_file():
            raise ValueError('Build artifact absent: ' + name)
        shutil.copyfile(source, output / name)
        report['files'][name] = {'bytes': source.stat().st_size, 'sha256': sha(source)}
    shutil.copyfile(work / '.config', output / 'build.config')
    (output / 'klipper.symbols.txt').write_text(symbols_text)
    (output / 'BUILD_REPORT.json').write_text(json.dumps(report, indent=2) + '\n')
    return report

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive', type=Path, default=KIT / 'UPSTREAM_KLIPPER_PINNED.zip')
    ap.add_argument('--work', type=Path, default=KIT / '.work/klipper')
    ap.add_argument('--output', type=Path, default=KIT / 'firmware')
    ap.add_argument('--toolchain-dir', type=Path)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--fresh', action='store_true', help='recreate only an owned private build directory')
    args = ap.parse_args()
    if not 1 <= args.jobs <= 32: raise ValueError('jobs must be 1..32')
    env = os.environ.copy()
    if args.toolchain_dir:
        env['PATH'] = str(args.toolchain_dir.resolve()) + os.pathsep + env.get('PATH', '')
    for name in ['arm-none-eabi-gcc', 'arm-none-eabi-cpp', 'arm-none-eabi-objcopy',
                 'arm-none-eabi-nm', 'arm-none-eabi-readelf', 'make']:
        if not shutil.which(name, path=env['PATH']): raise ValueError('Missing program: ' + name)
    args.work = args.work.resolve()
    args.output = args.output.resolve()
    stage(args.archive, args.work, args.fresh)
    from patch_upstream import patch
    patch(args.work)
    shutil.copyfile(KIT / 'config/m300_f103.defconfig', args.work / '.config')
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / 'FULL_ARM_BUILD.log').open('w') as log:
        compiler = run(['arm-none-eabi-gcc', '--version'], env=env, log=log)
        nano = run(['arm-none-eabi-gcc', '--print-file-name=libc_nano.a'], env=env, log=log).strip()
        if nano == 'libc_nano.a' or not Path(nano).is_file():
            raise ValueError('Toolchain lacks libc_nano.a')
        opts = ['PYTHON=' + sys.executable, 'CPP=arm-none-eabi-cpp', 'CROSS_PREFIX=arm-none-eabi-']
        run(['make', 'olddefconfig'] + opts, args.work, env, log)
        check_config(args.work / '.config')
        run(['make', 'clean'] + opts, args.work, env, log)
        run(['make', '-j' + str(args.jobs)] + opts, args.work, env, log)
        report = validate(args.work, args.output, env, log)
    (args.output / 'TOOLCHAIN.json').write_text(json.dumps({
        'compiler': compiler, 'python': sys.version, 'platform': platform.platform(),
        'command': sys.argv}, indent=2) + '\n')
    print(json.dumps({'result': 'FULL_ARM_BUILD_PASS', 'output': str(args.output),
                      'bytes': report['application_bytes'], 'flashed': False}, indent=2))

if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print('M300 BUILD STOPPED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
