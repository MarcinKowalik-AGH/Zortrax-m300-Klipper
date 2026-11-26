#!/usr/bin/env python3
# Marcin Kowalik <mkowalik@agh.edu.pl>
# package_git_deploy.py - Tworzy z gotowego wydania mały zestaw plików dla gałęzi instalacyjnej orange-pi.
"""Prepare a compact Git checkout from a complete, verified Actions artifact."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from project import digest, manifest


HOST = 'M300_HOST'
FLUIDD = 'M300_FLUIDD.zip'


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
    for name in (FLUIDD, 'MCU/M300APP.M3B', 'MCU/M300_SD.zip',
                 'MCU/klipper.dict', 'install-fresh.py', 'install-new-host.py',
                 'install-orange-pi.py', 'install-camera.py', 'CAMERA_PL.md', 'CAMERA_EN.md',
                 'read-host-temperatures.py', 'HOST_TEMPERATURE_PL.md', 'HOST_TEMPERATURE_EN.md',
                 'CONTACT_RECOVERY_PL.md', 'CONTACT_RECOVERY_EN.md',
                 'BUILD_PROVENANCE.json', 'LICENSE',
                 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(release / name, output / name)
    shutil.copytree(release/'FIRST_INSTALL',output/'FIRST_INSTALL')
    (output / 'README.md').write_text(
        '# M300 Classic ' + provenance['distribution_version'] + ' — Orange Pi\n\n'
        'This checkout contains the tested host, prebuilt Fluidd and MCU image.\n'
        'The matching SD application is `MCU/M300APP.M3B` (MCU '
        + provenance['mcu_release'] + '). Install it through your existing M300 bootloader.\n'
        'For a NEW KIAUH host (including Debian 13 / Python 3.13), run '
        '`python3 install-new-host.py --serial /dev/ttyS2 --baud 750000 --apply`.\n'
        'Substitute the actual enabled UART and bootloader baud for your board. '
        'No previous Pi or personal configuration archive is needed.\n'
        'Run `python3 install-orange-pi.py` as the Klipper user while idle and Ready to update the host.\n'
        'For an explicit Fluidd repair on port 4480, run `python3 install-orange-pi.py --update-fluidd --port 4480`.\n'
        'The updater preserves qualified Z, mesh and PID. Host print-time accounting works on compatible older MCU firmware.\n'
        'With MCU 1.0.8 or newer, Klipper automatically synchronizes print time to the board while idle. '
        'Install the MCU image from SD only if the board still requires the firmware update.\n\n'
        'Optional USB camera (disabled by default): '
        '`python3 install-camera.py --enable --apply`. '
        'Edit `~/printer_data/config/m300_camera.conf` and run '
        '`python3 install-camera.py --apply` to change it or disable streaming. '
        'See CAMERA_PL.md / CAMERA_EN.md.\n\n'
        'Optional host CPU temperature: one Host graph series, enabled with '
        '`[include m300_host_temperature.cfg]`. Other readings: '
        '`python3 read-host-temperatures.py`. See HOST_TEMPERATURE_PL.md / HOST_TEMPERATURE_EN.md.\n\n'
        'The new-host installer copies both optional temperature configs, disabled by default. '
        'Enable STM32 diagnostics with `[include m300_mcu_temperature.cfg]` '
        '(MCU 1.0.9 or newer), run `FIRMWARE_RESTART`, then `M300_MCU_TEMPERATURE`. '
        'The MCU include adds a read-only MCU graph curve using the existing ADC. '
        'Comment either temperature include in printer.cfg to disable that option.\n\n'
        'Contact recovery lowers the bed by 100 mm within the Z travel after a recognized '
        'nozzle-contact failure, invalidates Z and asks for cleaning. MCU shutdown guards remain active. '
        'See CONTACT_RECOVERY_PL.md / CONTACT_RECOVERY_EN.md for the existing-host update.\n\n'
        '[Update instructions](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/'
        + commit + '/docs/en/INSTALL.md)\n\n'
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
