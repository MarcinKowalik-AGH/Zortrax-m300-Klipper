#!/usr/bin/env python3
"""Validate actual compiled firmware and collect matching host artifacts."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import zipfile

from project import ROOT, META, KIT, OWNER, digest, source_digest, fresh_directory, stage_host_update


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    build = args.build.resolve()
    report = json.loads((build / 'BUILD_REPORT.json').read_text())
    if report['version'] != META['mcu_release'] or not report['full_arm_link']:
        raise ValueError('Wrong or incomplete ARM build')
    for name, expected in report['files'].items():
        if digest(build / name) != expected['sha256']:
            raise ValueError('Compiled file changed: ' + name)
    validation = json.loads((ROOT / '.ci/reports/VALIDATION.json').read_text())
    if (validation['status'] != 'PASS_M300_PUBLIC_SOFTWARE_CHECKS'
            or not validation['actual_klippy_fileoutput_executed']):
        raise ValueError('Complete validation is required before packaging')
    if validation['source_sha256'] != source_digest():
        raise ValueError('Source changed after validation')
    if validation['compiled_dictionary_sha256'] != digest(build / 'klipper.dict'):
        raise ValueError('Dictionary differs from the one exercised by real Klippy')
    release = fresh_directory(ROOT / 'dist/release')
    mcu = release / 'MCU'
    mcu.mkdir()
    for source in build.iterdir():
        if source.is_file():
            shutil.copy2(source, mcu / source.name)
    m3b = module('m300_container', KIT / 'tools/test01_m3b.py')
    packed = m3b.pack((mcu / 'klipper.bin').read_bytes())
    (mcu / 'M300APP.M3B').write_bytes(packed)
    container = m3b.inspect(packed)
    (mcu / 'M3B_REPORT.json').write_text(json.dumps(container, indent=2) + '\n')
    with zipfile.ZipFile(mcu / 'M300_R14_5_SD.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(mcu / 'M300APP.M3B', 'M300APP.M3B')
    stage = stage_host_update(ROOT / '.ci/release-host-update')
    host = release / 'M300_HOST_R16_9_NORMAL_UI'
    shutil.copytree(stage, host, ignore=shutil.ignore_patterns(OWNER, '__pycache__', '*.pyc'))
    with zipfile.ZipFile(release / 'M300_HOST_R16_9_NORMAL_UI.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(host.rglob('*')):
            if path.is_file():
                archive.write(path, str(path.relative_to(release)))
    shutil.copytree(ROOT / 'host/klippy', release / 'HOST_SOURCE/klippy',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / '.ci/reports', release / 'REPORTS',
                    ignore=shutil.ignore_patterns('timer-test', 'factory-test', 'sd-card-test'))
    if (ROOT / '.ci/fileoutput/REPORT.json').exists():
        shutil.copy2(ROOT / '.ci/fileoutput/REPORT.json', release / 'REPORTS/KLIPPY_FILEOUTPUT.json')
    provenance = {'model': META['model'], 'upstream_commit': META['upstream_commit'],
        'mcu_release': META['mcu_release'], 'host_update': META['host_update'],
        'github_commit': os.environ.get('GITHUB_SHA', 'LOCAL_UNPUBLISHED'),
        'github_run_id': os.environ.get('GITHUB_RUN_ID'),
        'physical_hardware': False, 'flashed': False,
        'factory_Z_requires_MCU_factory_ABI': 1,
        'normal_motion': True, 'z_homing_temperature': 180,
        'xy_velocity_profile': 300, 'calibration_temperature': 260,
        'filament_temperature': 240, 'release_stage': 'TEST_READY'}
    (release / 'BUILD_PROVENANCE.json').write_text(json.dumps(provenance, indent=2) + '\n')
    (release / 'INSTALL_EN.md').write_text((ROOT / 'docs/en/INSTALL.md').read_text())
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / name, release / name)
    (release / 'README.txt').write_text(
        'M300 Classic only. MCU application starts at 0x08008000. No bootloader image.\n'
        'Use R14.5 MCU with the English-only R16.9 host; see INSTALL_EN.md.\n'
        'HOST_SOURCE is the complete source snapshot, not an automatic installer.\n'
        'CI performs software checks and a real ARM build, not physical printer tests.\n')
    (release / OWNER).unlink()
    hashes = {str(p.relative_to(release)): digest(p) for p in sorted(release.rglob('*'))
              if p.is_file() and p.name != 'SHA256SUMS'}
    (release / 'SHA256SUMS').write_text(''.join(value + '  ' + name + '\n' for name, value in hashes.items()))
    print(json.dumps({'status': 'PASS_M300_RELEASE_PACKAGE', 'files': len(hashes),
                      'm3b_payload_bytes': container['payload_bytes'], 'flashed': False}))


if __name__ == '__main__':
    main()
