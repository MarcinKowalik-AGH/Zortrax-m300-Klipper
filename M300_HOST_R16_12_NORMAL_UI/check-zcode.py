#!/usr/bin/env python3
"""Read-only Z-code preflight. Never imports Klippy or sends printer commands."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent/'payload'))
from m300_binary import compile_m300, _bounds


def check(path,limits):
    row=dict(file=str(path),executed=False,physical_print_validated=False)
    try:
        with path.open('rb') as stream:data=stream.read(8*1024*1024+1)
        result=compile_m300(data,heater_limits=limits['heater_limits'],
            axis_limits=limits['axis_limits'],native=True,max_bytes=8*1024*1024,
            max_records=250000,max_output_bytes=16*1024*1024)
        row.update(status='PASS',source_sha256=result.metadata['source_sha256'],
            source_bytes=len(data),records=result.metadata['records'],
            opcode_counts=result.metadata['opcode_counts'],targets=result.targets,
            profile=result.metadata['profile'],gcode_sha256=result.metadata['gcode_sha256'],
            start='START_PRINT MESH=AUTO',end='END_PRINT')
    except (OSError,ValueError) as exc:
        row.update(status='REJECTED',reason=str(exc))
    return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limits',required=True,type=Path,
        help='JSON with heater_limits and axis_limits copied from actual printer configuration')
    parser.add_argument('files',nargs='+',type=Path)
    args=parser.parse_args()
    try:
        limits=json.loads(args.limits.read_text())
        if set(limits)!={'heater_limits','axis_limits'}:raise ValueError('expected heater_limits and axis_limits')
        if (not isinstance(limits['axis_limits'],dict) or not isinstance(limits['heater_limits'],dict)
                or set(limits['axis_limits'])!=set('XYZ')):raise ValueError('explicit XYZ and heater bounds are required')
        _bounds(limits['heater_limits'],limits['axis_limits'])
    except (OSError,ValueError,TypeError) as exc:parser.error(str(exc))
    rows=[check(path,limits) for path in args.files]
    print(json.dumps(dict(files=rows,all_passed=all(r['status']=='PASS' for r in rows)),indent=2))
    return 0 if all(r['status']=='PASS' for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
