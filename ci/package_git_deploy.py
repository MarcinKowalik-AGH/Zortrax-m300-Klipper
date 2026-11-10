#!/usr/bin/env python3
"""Prepare a compact Git checkout from a complete, verified Actions artifact."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from project import digest, manifest


HOST = 'M300_HOST_R16_12_NORMAL_UI'
FLUIDD = 'M300_FLUIDD_1_37_7_R16_12.zip'


def package(release, output, commit):
    subprocess.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS'], cwd=release, check=True)
    provenance = json.loads((release / 'BUILD_PROVENANCE.json').read_text())
    if provenance['github_commit'] != commit or provenance['release_stage'] != 'VERIFIED':
        raise ValueError('Actions artifact does not match this build')

    output.mkdir()
    shutil.copytree(release / HOST, output / HOST,
                    ignore=shutil.ignore_patterns('docs', 'tests', '__pycache__', '*.pyc'))
    manifest(output / HOST)
    subprocess.run([sys.executable, '-B', 'VERIFY.py'], cwd=output / HOST, check=True)

    (output / 'MCU').mkdir()
    for name in (FLUIDD, 'MCU/M300APP.M3B', 'MCU/M300_R14_19_SD.zip',
                 'install-orange-pi.py', 'BUILD_PROVENANCE.json', 'LICENSE',
                 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(release / name, output / name)
    (output / 'README.md').write_text(
        '# M300 Classic Orange Pi deployment\n\n'
        'This checkout contains the tested host, prebuilt Fluidd and MCU image.\n'
        'Run `python3 install-orange-pi.py` as the Klipper user while idle.\n'
        'The MCU image is for separate SD flashing.\n\n'
        'Source commit: `' + commit + '`\n')
    files = sorted(path for path in output.rglob('*') if path.is_file())
    (output / 'SHA256SUMS').write_text(''.join(
        f'{digest(path)}  {path.relative_to(output)}\n' for path in files))
    subprocess.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS'], cwd=output, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    package(args.release, args.output, args.commit)
