#!/usr/bin/env python3
"""Real Orca smoke test, offline only. GUI export metadata is adapted only in
scratch copies: type from manifest and from=system for standalone flat files.
2.3.2 CLI wrongly compares empty user inherits instead of printer_settings_id.
All slicer settings and compatibility names remain identical to the bundle.
"""
import argparse,hashlib,json,os,re,subprocess,zipfile
from pathlib import Path


def test_stl(path):
    t=[]
    for x in (140,160):
        v=[(x,140,0),(x+6,140,0),(x+6,146,0),(x,146,0),(x,140,5),(x+6,140,5),(x+6,146,5),(x,146,5)]
        for f in [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]:
            t.append('facet normal 0 0 0\n outer loop\n'+''.join('  vertex %s %s %s\n'%v[i] for i in f)+' endloop\nendfacet\n')
    path.write_text('solid m300\n'+''.join(t)+'endsolid m300\n')


def main():
    ap=argparse.ArgumentParser()
    for key in ('orca','bundle','out'):ap.add_argument('--'+key,required=True)
    a=ap.parse_args();out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    bundle=Path(a.bundle).resolve();root=out/'presets';root.mkdir(exist_ok=True)
    with zipfile.ZipFile(bundle) as z:
        if z.testzip():raise RuntimeError('ZIP CRC failure')
        for n in z.namelist():
            if not (root/n).resolve().is_relative_to(root):raise RuntimeError('Unsafe ZIP path')
        z.extractall(root)
    manifest=json.loads((root/'bundle_structure.json').read_text())
    for kind,field in [('machine','printer_config'),('process','process_config'),('filament','filament_config')]:
        for n in manifest[field]:
            f=root/n;j=json.loads(f.read_text());j['type']=kind;j['from']='system';f.write_text(json.dumps(j,indent=2))
    machine=root/manifest['printer_config'][0];process=root/manifest['process_config'][0]
    stl=out/'two_towers.stl';test_stl(stl)
    env=dict(os.environ,LIBGL_ALWAYS_SOFTWARE='1',WEBKIT_DISABLE_DMABUF_RENDERER='1')
    results=[]
    for rel in manifest['filament_config']:
        fp=root/rel;f=json.loads(fp.read_text());folder=out/re.sub('[^A-Za-z0-9_-]','_',f['name']);folder.mkdir(exist_ok=True)
        effective=folder/'effective.json'
        cmd=[str(Path(a.orca).resolve()),'--load-settings',str(machine)+';'+str(process),'--load-filaments',str(fp),
             '--export-settings',str(effective),'--slice','0','--outputdir',str(folder),str(stl)]
        r=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        (folder/'orca.log').write_text(r.stdout)
        paths=list(folder.glob('*.gcode'));g=paths[0].read_text(errors='replace') if paths else '';lines=g.splitlines()
        ef=json.loads(effective.read_text()) if effective.exists() else {}
        start=[l for l in lines if l.startswith('START_PRINT ')];end=[l for l in lines if l=='END_PRINT']
        neg=[l for l in lines if l.startswith(('G0 ','G1 ')) and re.search(r'\bE-[0-9]',l)]
        before=lines[:next((i for i,l in enumerate(lines) if l.startswith('START_PRINT ')),len(lines))]
        interesting={k:v for k,v in ef.items() if any(s in k for s in ('retract','filament_flow_ratio','filament_diameter','filament_max_volumetric','z_hop','curr_bed_type','temperature_initial_layer','pressure_advance'))}
        entry=dict(name=f['name'],rc=r.returncode,gcode_bytes=len(g),start=start,end=end,
                   pre_start_commands=[l for l in before if l and not l.startswith(';')][-20:],
                   negative_e_count=len(neg),negative_e_examples=neg[:6],effective=interesting,
                   all_commands=sorted(set(l.split()[0] for l in lines if l and not l.startswith(';'))),last_log=r.stdout[-3500:])
        results.append(entry);print('MATERIAL_RESULT='+json.dumps(entry,sort_keys=True),flush=True)
        (out/'results.json').write_text(json.dumps(results,indent=2))
    summary=dict(bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),materials=len(results),sliced=sum(x['gcode_bytes']>0 for x in results),nonzero_return=sum(x['rc']!=0 for x in results))
    print('SUMMARY='+json.dumps(summary),flush=True);(out/'summary.json').write_text(json.dumps(summary,indent=2))
    bad=[x['name'] for x in results if 'Z-PEEK' not in x['name'] and (x['rc']!=0 or not x['start'] or not x['end'] or not x['negative_e_count'])]
    if bad:raise RuntimeError('Slicing validation failed: '+', '.join(bad))


if __name__=='__main__':main()
