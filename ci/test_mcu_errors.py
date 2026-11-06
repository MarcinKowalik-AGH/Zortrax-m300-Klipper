#!/usr/bin/env python3
"""Exercise the production MCU error store and board guard in native models."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'mcu/SOURCE_MCU'
sys.path.insert(0, str(KIT / 'tools'))
import patch_upstream


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    args = parser.parse_args()
    original = {}
    for rel, digest in patch_upstream.EXPECTED.items():
        path = args.upstream / rel
        if patch_upstream.sha(path.read_bytes()) != digest:
            raise ValueError('Not pristine pinned source: ' + rel)
        original[rel] = path.read_text()
    native = patch_upstream.transformed(original)
    with tempfile.TemporaryDirectory(prefix='m300-errors-') as td:
        temp = Path(td)
        mock = temp / 'mock'
        for name in ('autoconf.h','board/irq.h','board/misc.h','command.h','internal.h',
                     'sched.h','gpio.h','compiler.h','generic/armcm_timer.h'):
            path = mock / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('/* Supplied by the native register fixture. */\n')
        flags = []
        for tag, rel in (('GPIO', 'src/stm32/gpio.c'), ('ADC', 'src/stm32/adc.c')):
            path = temp / ('native_' + tag.lower() + '.c')
            path.write_text(native[rel])
            flags.append('-DM300_NATIVE_%s_FILE="%s"' % (tag, path))
        exe = temp / 'test'
        subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror',
            '-Wno-unused-parameter','-Wno-sign-compare','-I'+str(mock),
            '-I'+str(KIT/'overlay/src/stm32'),*flags,
            str(KIT/'tests/test_m300_errors.c'),'-o',str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    main()
