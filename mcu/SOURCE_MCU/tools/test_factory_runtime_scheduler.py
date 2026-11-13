#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile the production transformed scheduler against a host clock model."""
import argparse
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import patch_upstream

KIT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    args = parser.parse_args()

    sources = {}
    for name, digest in patch_upstream.EXPECTED.items():
        raw = (args.upstream / name).read_bytes()
        if patch_upstream.sha(raw) != digest:
            raise ValueError('Not pristine pinned source: ' + name)
        sources[name] = raw.decode()
    scheduler = patch_upstream.transformed(sources)['src/sched.c']

    with TemporaryDirectory(prefix='m300-factory-scheduler-') as directory:
        work = Path(directory)
        (work / 'native_sched.c').write_text(scheduler)
        (work / 'sched.h').write_text((args.upstream / 'src/sched.h').read_text())
        # The C fixture supplies the MCU clocks, IRQ functions and callbacks.
        for name in ('autoconf.h', 'basecmd.h', 'board/io.h', 'board/irq.h',
                     'board/misc.h', 'board/pgm.h', 'board/m300_errors.h',
                     'board/m300.h', 'board/gpio.h', 'command.h', 'ctr.h',
                     'stepper.h'):
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        executable = work / 'test-factory-scheduler'
        subprocess.run([
            'cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-Wno-unused-parameter', '-I' + str(work),
            str(KIT / 'tests/test_m300_factory_runtime_scheduler.c'),
            '-o', str(executable),
        ], check=True)
        subprocess.run([str(executable)], check=True)


if __name__ == '__main__':
    main()
