#!/usr/bin/env python3
"""Start the actual first-install configuration in pinned Klippy FILEOUTPUT."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from project import ROOT,META,stage_host_update
from install_fresh import render_config

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,required=True)
parser.add_argument('--dictionary',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
package=args.output/'package';package.mkdir(exist_ok=True)
first=package/'FIRST_INSTALL';first.mkdir(exist_ok=True)
for name in ('m300_classic_base.cfg','m300_classic_services.cfg','m300_classic_sensors.cfg'):
    shutil.copy2(ROOT/'host/config'/name,first/name)
stage_host_update(package/'M300_HOST_R16_12_NORMAL_UI')
config=args.output/'config';config.mkdir(exist_ok=True)
data=args.output/'data';(data/'gcodes').mkdir(parents=True,exist_ok=True)
(data/'config').mkdir(exist_ok=True)
render_config(package,config,data.resolve(),Path('/dev/ttyS1'),750000,'M300_FIRST_INSTALL_FILEOUTPUT')
source=args.output/'input.gcode'
source.write_text('ZORTRAX_NATIVE_STATUS\nZORTRAX_SETTINGS_STATUS\nZORTRAX_PAD_MESH_STATUS\nPRINT_CONTROL_STATUS\nZORTRAX_OLED_STATUS\n')
log=args.output/'klippy.log'
result=subprocess.run([sys.executable,str(args.root/'klippy/klippy.py'),str(config/'printer.cfg'),
    '-i',str(source),'-o',str(args.output/'protocol.bin'),'-d',str(args.dictionary),'-l',str(log)],
    capture_output=True,text=True,timeout=30)
text=result.stdout+result.stderr+log.read_text()
assert result.returncode==0,(result.returncode,text[-5000:])
for marker in ('Configured MCU', 'M300_NATIVE ', 'M300_PAD_MESH ', 'M300_PRINT_CONTROL '):
    assert marker in text,(marker,text[-5000:])
# Validate the runtime's complete revision and state, not a stale substring
# from one previous release. A mismatched installed module still fails CI.
print_states=[json.loads(line.split('M300_PRINT_CONTROL ',1)[1])
              for line in text.splitlines() if line.startswith('M300_PRINT_CONTROL ')]
assert print_states,('missing parsed print-control status',text[-5000:])
for state in print_states:
    assert state['revision']==META['print_control_revision'],state
    assert state['state']=='IDLE' and state['phase']=='IDLE',state
    assert state['busy'] is False and state['paused'] is False,state
assert 'Traceback' not in text and 'Error loading printer config' not in text,text[-5000:]
report=dict(status='PASS_ACTUAL_FIRST_INSTALL_KLIPPY',FILEOUTPUT=True,physical_hardware=False,
            MCU_executed=False,serial_baud=750000,native_mesh=True,CI_helpers_in_config=False,
            print_control_revision=META['print_control_revision'])
(args.output/'REPORT.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
