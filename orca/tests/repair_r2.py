#!/usr/bin/env python3
"""Idempotent R2 repair for M300 Classic's single physical factory bed.
No change to print speeds, accelerations, extrusion multipliers or retractions.
No firmware changes. PEEK stays catalog-only; its mask is NOT a safety barrier.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def repair(source: Path, target: Path):
    with zipfile.ZipFile(source) as z:
        if z.testzip(): raise ValueError('Invalid source ZIP CRC')
        files = {n: json.loads(z.read(n)) for n in z.namelist()}
    changes = []
    for path, obj in files.items():
        old = json.loads(json.dumps(obj))
        if path.startswith('printer/'):
            obj['default_bed_type'] = 'High Temp Plate'
            obj['printer_notes'] = ('M300 Classic 0.4 mm / Klipper R2. One physical factory bed: '
                'all Orca plate slots use the same per-filament temperatures to prevent a '
                'hidden/default Cool Plate choice from setting BED_TEMP=0. '
                'PEEK is catalog-only and exceeds host max_temp; never print it.')
        elif path.startswith('process/'):
            # Modern upstream Klipper removed ACCEL_TO_DECEL in August 2025.
            # Leave minimum_cruise_ratio and SCV in the host configuration.
            obj['accel_to_decel_enable'] = '0'
        elif path.startswith('filament/'):
            first = obj['hot_plate_temp_initial_layer'][0]
            normal = obj['hot_plate_temp'][0]
            for k in list(obj):
                if k.endswith('_plate_temp_initial_layer'):
                    obj[k] = [first]
                elif k.endswith('_plate_temp'):
                    obj[k] = [normal]
            if obj['name'].startswith('Z-PEEK '):
                obj['filament_notes'] = [
                    'CATALOG ONLY: NOT FOR PRINTING ON M300 CLASSIC. 380C exceeds the '
                    'host heater limit 270C. filament_printable=0 is NOT a reliable '
                    'slicing block: Orca 2.3.2 CLI still emits G-code. The M300 '
                    'START_PRINT temperature validation rejects this target before '
                    'heating/motion. No safety or temperature limit is changed.']
        if set(old) != set(obj): raise AssertionError('Key schema changed: '+path)
        for k in old:
            if old[k] != obj[k]: changes.append({'file': path, 'field': k, 'old': old[k], 'new': obj[k]})
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, obj in files.items():
            info = zipfile.ZipInfo(name, (2026, 11, 11, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, json.dumps(obj, ensure_ascii=False, indent=4)+'\n')
    with zipfile.ZipFile(target) as z:
        if z.testzip(): raise AssertionError('Generated ZIP CRC failure')
    report = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'target_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'changes': changes, 'firmware_changed': False,
              'extrusion_retraction_tuning_changed': False}
    target.with_suffix('.changes.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print('R2_REPAIR='+json.dumps({k:v for k,v in report.items() if k!='changes'}))
    return report


if __name__ == '__main__':
    ap=argparse.ArgumentParser();ap.add_argument('source',type=Path);ap.add_argument('target',type=Path)
    a=ap.parse_args();repair(a.source,a.target)
