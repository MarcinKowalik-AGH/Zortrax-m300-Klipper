from pathlib import Path
import importlib.util,json,shutil,subprocess,tempfile
B=Path(__file__).resolve().parents[1]
KIT=B/'SOURCE_MCU'
OLD=B/'tests/reference/R14_3'
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--upstream',type=Path,required=True);args=ap.parse_args()
UP=args.upstream
spec=importlib.util.spec_from_file_location('snapshot_patcher',KIT/'tools/patch_upstream.py')
pu=importlib.util.module_from_spec(spec);spec.loader.exec_module(pu)
original={}
for rel,digest in pu.EXPECTED.items():
    assert pu.sha((UP/rel).read_bytes())==digest,rel
    original[rel]=(UP/rel).read_text()
native=pu.transformed(original)
reports=[]
with tempfile.TemporaryDirectory(prefix='m300-guard-snapshot-') as td:
    root=Path(td);mock=root/'mock'
    for name in ['autoconf.h','board/irq.h','board/misc.h','command.h','internal.h','sched.h','gpio.h','compiler.h','generic/armcm_timer.h']:
        p=mock/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('/* fixture supplies declarations */\n')
    for name,rel in [('native_gpio.c','src/stm32/gpio.c'),('native_adc.c','src/stm32/adc.c')]:
        (root/name).write_text(native[rel])
    for label,source in [('R14_3_negative_control',OLD),('R14_4_candidate',KIT)]:
        r=root/label;r.mkdir();shutil.copytree(source/'overlay',r/'overlay')
        (r/'tests').mkdir()
        h=(KIT/'tests/test_m300_board.c').read_text()
        if source==OLD:h=h.replace('guard_check()','guard_check(now_ticks)').replace('sync_fan_policy()','sync_fan_policy(now_ticks)')
        (r/'tests/test_m300_board.c').write_text(h)
        shutil.copy2(KIT/'tests/test_guard_snapshot.c',r/'tests/test_guard_snapshot.c')
        args=['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-sign-compare','-O2',
            '-I'+str(mock),'-I'+str(r/'overlay/src/stm32'),
            '-DM300_NATIVE_GPIO_FILE="'+str(root/'native_gpio.c')+'"',
            '-DM300_NATIVE_ADC_FILE="'+str(root/'native_adc.c')+'"']
        if source==OLD:args+=['-DM300_OLD_SNAPSHOT_API=1']
        subprocess.run(args+[str(r/'tests/test_guard_snapshot.c'),'-o',str(r/'test')],check=True)
        result=subprocess.run([str(r/'test')],capture_output=True,text=True)
        (B/'evidence'/f'{label}.log').write_text(result.stdout+result.stderr)
        reports.append({'variant':label,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'physical_hardware':False})
        if source==OLD:assert result.returncode!=0,'negative control did not reproduce race'
        else:assert result.returncode==0,result.stderr
(B/'evidence/GUARD_SNAPSHOT.json').write_text(json.dumps({'status':'PASS_REPRODUCTION_AND_CANDIDATE','reports':reports},indent=2)+'\n')
print(json.dumps({'status':'PASS_REPRODUCTION_AND_CANDIDATE','old_exit':reports[0]['exit_code'],'new_exit':reports[1]['exit_code'],'new_cases':6,'physical_hardware':False}))
