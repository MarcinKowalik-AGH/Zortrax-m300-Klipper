#!/usr/bin/env python3
"""Validate the compiled M300 MCU numeric firmware identity and application image.

Read-only. Never opens a serial connection, writes to SD, or flashes hardware.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = '1.0.1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check(dictionary_path, binary_path=None, m3b_path=None):
    meta = json.loads((ROOT / 'PORT.json').read_text())
    require(meta['model'] == 'M300_CLASSIC', 'Wrong printer model')
    require(meta['mcu_release'] == EXPECTED, 'PORT.json MCU release mismatch')
    require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', EXPECTED) is not None,
            'MCU release requires exactly three numeric components')
    data = json.loads(Path(dictionary_path).read_text())
    require(data['version'] == EXPECTED, 'MCU dictionary build version contains suffix')
    require(data['config']['M300_MCU_RELEASE'] == EXPECTED,
            'MCU firmware release constant differs from dictionary version')
    require(data['config']['M300_MODEL'] == 'M300_CLASSIC', 'MCU model mismatch')
    require(data['config']['M300_ABI'] == 1, 'MCU ABI mismatch')
    require(data['config']['M300_FAN_POLICY'] == 3,
            'Independent cooling fan policy changed')
    require(data['config']['M300_UART_RATE_COUNT'] == 8,
            'Saved UART speed compatibility changed')
    require(data['config']['M300_XY_STEP_TIMER_ABI'] == 1,
            'XY timer ABI changed')
    require(data['config']['M300_OLED_FAST_ABI'] == 1,
            'OLED fast transfer ABI changed')
    binary = None
    if binary_path is not None:
        binary = Path(binary_path).read_bytes()
        require(b'1.0.1\0' in binary, 'Compiled MCU image lacks numeric release')
        require(b'TONED-OLED-UART8' not in binary,
                'Old development suffix remains in actual MCU image')
    info = None
    if m3b_path is not None:
        spec = importlib.util.spec_from_file_location(
            'm300_m3b', ROOT/'mcu/SOURCE_MCU/tools/test01_m3b.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        packed = Path(m3b_path).read_bytes()
        info = module.inspect(packed)
        require(info['application_base'] == '0x8008000', 'Application base changed')
        require(info['bootloader_modified'] is False, 'Unexpected bootloader inclusion')
        if binary is not None:
            require(info['payload_sha256'] == hashlib.sha256(binary).hexdigest(),
                    'Packed application does not match the compiled image')
    print(json.dumps({'status': 'PASS_M300_MCU_NUMERIC_IDENTITY',
                      'firmware_version': EXPECTED,
                      'dictionary_version': data['version'],
                      'mcu_abi': data['config']['M300_ABI'],
                      'bootloader_modified': False,
                      'physical_hardware_tested': False,
                      'm3b': info}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dictionary', type=Path, required=True)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--m3b', type=Path)
    args = parser.parse_args()
    check(args.dictionary, args.binary, args.m3b)
