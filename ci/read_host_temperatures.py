#!/usr/bin/env python3
"""Read Linux thermal zones on demand, without modifying Klipper or its graph."""
import argparse
import json
import math
from pathlib import Path


def read_zones(root):
    result = []
    zones = sorted(root.glob('thermal_zone*'),
                   key=lambda path: (len(path.name), path.name))
    for zone in zones:
        row = {'zone': zone.name, 'sensor_path': str(zone/'temp')}
        try:
            row['type'] = (zone/'type').read_text().strip()
            value = float((zone/'temp').read_text().strip()) / 1000.
            if not math.isfinite(value):
                raise ValueError('non-finite temperature')
            row['temperature'] = value
        except (OSError, ValueError) as error:
            row['error'] = str(error)
        result.append(row)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Print machine-readable readings')
    parser.add_argument('--thermal-root', type=Path, default=Path('/sys/class/thermal'),
                        help='Linux thermal directory (default /sys/class/thermal)')
    args = parser.parse_args()
    rows = read_zones(args.thermal_root)
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    elif rows:
        for row in rows:
            reading = (f"{row['temperature']:.1f} °C" if 'temperature' in row
                       else 'unavailable: '+row['error'])
            print(f"{row['zone']:16} {row.get('type', 'unknown'):24} {reading}")
    else:
        print('No Linux thermal zones found.')
    return 0 if any('temperature' in row for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
