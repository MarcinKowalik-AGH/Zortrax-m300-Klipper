#!/usr/bin/env python3
"""Offline Orca 2.3.2 checks; never upload G-code or contact a printer."""
import argparse, hashlib, json, os, re, subprocess, zipfile
from pathlib import Path
from audit_slice import inspect_gcode, test_stl


def main():
    ap=argparse.ArgumentParser()
    for key in ('orca','bundle','out'):ap.add_argument('--'+key,required=True)
    a=ap.parse_args();out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    bundle=Path(a.bundle).resolve();root=out/'presets';root.mkdir(exist_ok=True)
    with zipfile.ZipFile(bundle) as z:
        assert z.testzip() is None
        for name in z.namelist():
            assert (root/name).resolve().is_relative_to(root)
        z.extractall(root)
    m=json.loads((root/'bundle_structure.json').read_text())
    p=json.loads((root/m['printer_config'][0]).read_text())
    assert len(p)==144 and p['use_relative_e_distances']=='1'
    assert len(json.loads((root/m['process_config'][0]).read_text()))==334
    original_filaments={n:json.loads((root/n).read_text()) for n in m['filament_config']}
    assert len(original_filaments)==18
    for f in original_filaments.values():
        assert len(f)==123
        assert f['enable_pressure_advance']==['1'] and f['pressure_advance']==['0']
        for k,v in f.items():
            if '_plate_temp' in k:assert 0<=float(v[0])<=105
    for kind,field in [('machine','printer_config'),('process','process_config'),('filament','filament_config')]:
        for name in m[field]:
            path=root/name;j=json.loads(path.read_text());j['type']=kind;j['from']='system'
            path.write_text(json.dumps(j))
    stl=out/'two_towers.stl';test_stl(stl)
    env=dict(os.environ,LIBGL_ALWAYS_SOFTWARE='1',WEBKIT_DISABLE_DMABUF_RENDERER='1')
    machine=root/m['printer_config'][0];process=root/m['process_config'][0]
    rows=[]
    def run(fp, label, expected_pa):
        f=json.loads(fp.read_text());folder=out/label;folder.mkdir(exist_ok=True)
        effective=folder/'effective.json'
        cmd=[a.orca,'--load-settings',str(machine)+';'+str(process),'--load-filaments',str(fp),
             '--export-settings',str(effective),'--slice','0','--outputdir',str(folder),str(stl)]
        r=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        (folder/'orca.log').write_text(r.stdout)
        files=list(folder.glob('*.gcode'));g=files[0].read_text() if files else ''
        ef=json.loads(effective.read_text()) if effective.exists() else {}
        details=inspect_gcode(g,f,p,ef) if g else {'errors':['No G-code generated']}
        commands=[l.split(';',1)[0].strip() for l in g.splitlines() if l.split(';',1)[0].strip()]
        start=next((i for i,l in enumerate(commands) if l.startswith('START_PRINT ')),None)
        pa=[]
        for i,l in enumerate(commands):
            if l.startswith('SET_PRESSURE_ADVANCE '):
                match=re.search(r'\bADVANCE=([0-9.]+)',l)
                if match:pa.append((i,float(match[1]),l))
        if start is None or not any(i<start and value==0 for i,value,line in pa):
            details['errors'].append('Missing PA reset before machine purge')
        if start is None or not any(i>start and abs(value-expected_pa)<1e-8 for i,value,line in pa):
            details['errors'].append('Per-filament PA not emitted after machine start')
        if r.returncode:details['errors'].append('CLI failed '+str(r.returncode))
        peek=f['name'].startswith('Z-PEEK ')
        row=dict(name=f['name'],label=label,returncode=r.returncode,gcode_bytes=len(g),
            status='UNSUPPORTED_CATALOG_ONLY' if peek else ('FAIL' if details['errors'] else 'PASS'),
            expected_pressure_advance=expected_pa,pa_commands=[line for i,value,line in pa],details=details)
        rows.append(row);print(json.dumps({'label':label,'status':row['status'],'errors':details['errors']}),flush=True)
        (out/'results.json').write_text(json.dumps(rows,indent=2))
    for rel in m['filament_config']:
        label=re.sub('[^A-Za-z0-9_-]','_',original_filaments[rel]['name'])
        run(root/rel,label,0.)
    # Test only. 0.035 is NOT published as an alleged measured PA value.
    rel=next(n for n in m['filament_config'] if 'Z-PLA Pro ' in n)
    f=json.loads((root/rel).read_text());f['pressure_advance']=['0.035']
    trial=out/'calibration_only_pa_0035.json';trial.write_text(json.dumps(f))
    run(trial,'CALIBRATION_ONLY_PA_0035',.035)
    summary=dict(revision='R3',orca='2.3.2',bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        material_pass=sum(x['status']=='PASS' for x in rows[:18]),
        material_fail=sum(x['status']=='FAIL' for x in rows[:18]),
        unsupported_catalog_count=sum(x['status']=='UNSUPPORTED_CATALOG_ONLY' for x in rows[:18]),
        pa_propagation_test=rows[-1]['status'],host_unit_tests=756,
        metadata_adapter=['type','from=system'],gui_test=False,physical_test=False,
        nozzle_temperature_offset=0,bed_target_max=105,hotend_sensor_limit_increased=False)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('R3_SUMMARY='+json.dumps(summary),flush=True)
    assert summary['material_pass']==17 and summary['material_fail']==0 and summary['pa_propagation_test']=='PASS'

if __name__=='__main__':main()
