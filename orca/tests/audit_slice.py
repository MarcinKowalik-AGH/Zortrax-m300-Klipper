#!/usr/bin/env python3
"""Real OrcaSlicer smoke test. Offline only; never submit files to a printer.
The GUI bundle importer knows types from the manifest; --load-settings needs
an extra 'type' metadata field. This adapter adds only that metadata in test
copies, without changing any printer/process/material setting.
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
    triangles=[]
    for x in (140,160):
        vertices=[(x,140,0),(x+6,140,0),(x+6,146,0),(x,146,0),
                  (x,140,5),(x+6,140,5),(x+6,146,5),(x,146,5)]
        faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
               (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
        for face in faces:
            triangles.append('facet normal 0 0 0\n outer loop\n'+''.join(
                '  vertex %s %s %s\n'%vertices[i] for i in face)+' endloop\nendfacet\n')
    path.write_text('solid m300_retraction_test\n'+''.join(triangles)+'endsolid m300_retraction_test\n')


def main():
    ap=argparse.ArgumentParser()
    for arg in ('orca','bundle','out'): ap.add_argument('--'+arg,required=True)
    args=ap.parse_args()
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
    bundle=Path(args.bundle).resolve();extracted=out/'presets';extracted.mkdir(exist_ok=True)
    with zipfile.ZipFile(bundle) as z:
        if z.testzip():raise RuntimeError('ZIP CRC failure')
        for n in z.namelist():
            if not (extracted/n).resolve().is_relative_to(extracted):raise RuntimeError('Unsafe ZIP path')
        z.extractall(extracted)
    manifest=json.loads((extracted/'bundle_structure.json').read_text())
    for kind,field in [('machine','printer_config'),('process','process_config'),('filament','filament_config')]:
        for n in manifest[field]:
            f=extracted/n;j=json.loads(f.read_text());j['type']=kind
            f.write_text(json.dumps(j,indent=2))
    printer=extracted/manifest['printer_config'][0];process=extracted/manifest['process_config'][0]
    p=json.loads(printer.read_text());pr=json.loads(process.read_text())
    stl=out/'two_towers.stl';test_stl(stl)
    exe=str(Path(args.orca).resolve())
    env=dict(os.environ,LIBGL_ALWAYS_SOFTWARE='1',WEBKIT_DISABLE_DMABUF_RENDERER='1')
    results=[]
    for rel in manifest['filament_config']:
        fp=extracted/rel;f=json.loads(fp.read_text());label=re.sub('[^A-Za-z0-9_-]','_',f['name'])
        folder=out/label;folder.mkdir(exist_ok=True);effective=folder/'effective.json'
        cmd=[exe,'--load-settings',str(printer)+';'+str(process),'--load-filaments',str(fp),
             '--export-settings',str(effective),'--slice','0','--outputdir',str(folder),str(stl)]
        r=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        (folder/'orca.log').write_text(r.stdout)
        gcodes=list(folder.glob('*.gcode'));gcode=gcodes[0].read_text(errors='replace') if gcodes else ''
        ef=json.loads(effective.read_text()) if effective.exists() else {}
        lines=gcode.splitlines()
        start=[l for l in lines if l.startswith('START_PRINT ')]
        end=[l for l in lines if l=='END_PRINT']
        negative=[l for l in lines if l.startswith(('G0 ','G1 ')) and re.search(r'\bE-[0-9]',l)]
        first=lines[:next((i for i,l in enumerate(lines) if l.startswith('START_PRINT ')),len(lines))]
        relevant={k:v for k,v in ef.items() if any(s in k for s in ('retract','filament_flow_ratio','filament_diameter','filament_max_volumetric','z_hop','curr_bed_type','temperature_initial_layer','pressure_advance'))}
        nominal={k:v for k,v in f.items() if any(s in k for s in ('retract','flow_ratio','volumetric','printable'))}
        entry=dict(name=f['name'],rc=r.returncode,gcode_bytes=len(gcode),start=start,end=end,
                   pre_start_commands=[l for l in first if l and not l.startswith(';')][-20:],
                   negative_e_count=len(negative),negative_e_examples=negative[:6],effective=relevant,filament=nominal,
                   all_commands=sorted(set(l.split()[0] for l in lines if l and not l.startswith(';'))),
                   last_log=r.stdout[-4000:])
        results.append(entry)
        print('MATERIAL_RESULT='+json.dumps(entry,sort_keys=True),flush=True)
        (out/'results.json').write_text(json.dumps(results,indent=2))
    summary=dict(bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),materials=len(results),
                 sliced=sum(x['gcode_bytes']>0 for x in results),nonzero_return=sum(x['rc']!=0 for x in results))
    print('SUMMARY='+json.dumps(summary),flush=True)
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    failures=[x['name'] for x in results if 'Z-PEEK' not in x['name'] and (x['rc']!=0 or not x['start'] or not x['end'] or not x['negative_e_count'])]
    if failures:raise RuntimeError('Slicing validation failed: '+', '.join(failures))


if __name__=='__main__':main()
