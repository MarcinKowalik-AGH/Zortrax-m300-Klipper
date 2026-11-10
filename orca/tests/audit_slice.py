#!/usr/bin/env python3
"""Slice a disconnected two-tower STL using the real, pinned OrcaSlicer binary.
This is an offline slicing test: never upload generated G-code to a printer.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile


def test_stl(path):
    triangles = []
    for x in (140, 160):
        vertices = [(x,140,0),(x+6,140,0),(x+6,146,0),(x,146,0),
                    (x,140,5),(x+6,140,5),(x+6,146,5),(x,146,5)]
        faces = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
                 (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
        for face in faces:
            triangles.append('facet normal 0 0 0\n outer loop\n' + ''.join(
                '  vertex %s %s %s\n' % vertices[i] for i in face) + ' endloop\nendfacet\n')
    path.write_text('solid m300_retraction_test\n' + ''.join(triangles) + 'endsolid m300_retraction_test\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--orca', required=True)
    ap.add_argument('--bundle', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    out = Path(args.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    bundle = Path(args.bundle).resolve()
    extracted = out / 'presets'; extracted.mkdir(exist_ok=True)
    with zipfile.ZipFile(bundle) as z:
        bad = z.testzip()
        if bad: raise RuntimeError('CRC failure: '+bad)
        for name in z.namelist():
            target = (extracted / name).resolve()
            if not target.is_relative_to(extracted): raise RuntimeError('Unsafe ZIP path')
        z.extractall(extracted)
    manifest = json.loads((extracted/'bundle_structure.json').read_text())
    printer = extracted / manifest['printer_config'][0]
    process = extracted / manifest['process_config'][0]
    p = json.loads(printer.read_text()); pr = json.loads(process.read_text())
    print('PRINTER_RELEVANT='+json.dumps({k:v for k,v in p.items() if any(s in k for s in ('gcode','retract','extrud','bed_type','z_hop','host'))},sort_keys=True))
    print('PROCESS_RELEVANT='+json.dumps({k:v for k,v in pr.items() if any(s in k for s in ('speed','acceleration','jerk','raft','post_process','flow'))},sort_keys=True))
    stl = out/'two_towers.stl'; test_stl(stl)
    exe = str(Path(args.orca).resolve())
    env = dict(os.environ, LIBGL_ALWAYS_SOFTWARE='1', WEBKIT_DISABLE_DMABUF_RENDERER='1')
    results=[]
    for index, relative in enumerate(manifest['filament_config']):
        fp=extracted/relative; f=json.loads(fp.read_text())
        label = re.sub('[^A-Za-z0-9_-]', '_', f['name'])
        folder=out/label; folder.mkdir(exist_ok=True)
        effective=folder/'effective.json'
        command=[exe,'--load-settings',str(printer)+';'+str(process),
                 '--load-filaments',str(fp),'--export-settings',str(effective),
                 '--slice','0','--outputdir',str(folder),str(stl)]
        r=subprocess.run(command,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        (folder/'orca.log').write_text(r.stdout)
        gcodes=list(folder.glob('*.gcode'))
        gcode=gcodes[0].read_text(errors='replace') if gcodes else ''
        # Some versions store sliced G-code only inside a 3MF when requested.
        if not gcode:
            for project in folder.glob('*.3mf'):
                with zipfile.ZipFile(project) as z:
                    for n in z.namelist():
                        if n.endswith('.gcode'):
                            gcode=z.read(n).decode(errors='replace')
                            (folder/'extracted.gcode').write_text(gcode)
                            break
        start_lines=[l for l in gcode.splitlines() if re.match(r'^(?:START_PRINT|END_PRINT|M8[23]|M10[49]|M1[49]0|SET_PRESSURE_ADVANCE|SET_VELOCITY_LIMIT|M204)\b',l)]
        negative_e=[]
        for l in gcode.splitlines():
            if l.startswith(('G0 ','G1 ')):
                m=re.search(r'\bE(-[0-9.]+)',l)
                if m: negative_e.append(l)
        ef=json.loads(effective.read_text()) if effective.exists() else {}
        interesting={k:v for k,v in ef.items() if any(s in k for s in ('retract','filament_flow_ratio','filament_diameter','filament_max_volumetric','z_hop','curr_bed_type','temperature_initial_layer'))}
        entry=dict(name=f['name'],rc=r.returncode,gcode_bytes=len(gcode),
                   start_end=start_lines[:35],negative_e_count=len(negative_e),
                   negative_e_examples=negative_e[:5],effective=interesting,
                   filament={k:v for k,v in f.items() if any(s in k for s in ('retract','flow_ratio','volumetric','printable','plate_temp','temperature','pressure_advance','start_gcode','end_gcode'))},
                   last_log=r.stdout[-7000:])
        results.append(entry)
        print('MATERIAL_RESULT='+json.dumps(entry,sort_keys=True),flush=True)
        (out/'results.json').write_text(json.dumps(results,indent=2))
    print('SUMMARY='+json.dumps({'bundle_sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),'materials':len(results),'sliced':sum(x['gcode_bytes']>0 for x in results),'nonzero_return':sum(x['rc']!=0 for x in results)}))


if __name__=='__main__': main()
