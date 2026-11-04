#!/usr/bin/env python3
"""Replay the real patched stepper and gated-timer driver with STM32 register doubles."""
import argparse
from pathlib import Path
import subprocess
import tempfile

import patch_upstream

KIT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    args = parser.parse_args()
    original = {}
    for name, digest in patch_upstream.EXPECTED.items():
        data = (args.upstream / name).read_bytes()
        if patch_upstream.sha(data) != digest:
            raise ValueError('Not pristine pinned source: ' + name)
        original[name] = data.decode()
    with tempfile.TemporaryDirectory(prefix='m300-xy-timer-') as directory:
        work = Path(directory)
        (work / 'native_stepper.c').write_text(patch_upstream.transformed(original)['src/stepper.c'])
        for name in ('autoconf.h', 'basecmd.h', 'board/gpio.h', 'board/irq.h',
                     'board/misc.h', 'command.h', 'generic/armcm_boot.h',
                     'internal.h', 'sched.h', 'stepper.h', 'trsync.h'):
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        overlay = KIT / 'overlay/src/stm32'
        (work / 'board/m300.h').symlink_to(overlay / 'm300.h')
        (work / 'board/m300_xy_step_timer.h').symlink_to(overlay / 'm300_xy_step_timer.h')
        executable = work / 'xy-timer-test'
        subprocess.run([
            'cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-Wno-unused-parameter',
            '-I' + str(work), '-I' + str(overlay),
            str(KIT / 'tests/test_m300_xy_step_timer.c'), '-o', str(executable),
        ], check=True)
        subprocess.run([str(executable)], check=True)


if __name__ == '__main__':
    main()
