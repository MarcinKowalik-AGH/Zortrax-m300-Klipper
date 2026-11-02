#!/usr/bin/env python3
"""Native C guard equivalence; no physical MCU execution or cycle benchmark."""
from pathlib import Path
import argparse,hashlib,json,subprocess,tempfile
import patch_upstream
KIT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    original={}
    for rel,digest in patch_upstream.EXPECTED.items():
        path=args.upstream/rel
        if patch_upstream.sha(path.read_bytes())!=digest:raise ValueError('Not pristine pinned source: '+rel)
        original[rel]=path.read_text()
    native=patch_upstream.transformed(original)
    with tempfile.TemporaryDirectory(prefix='m300-stepfast-') as td:
        temp=Path(td);mock=temp/'mock'
        for n in ('autoconf.h','board/irq.h','board/misc.h','command.h','internal.h','sched.h','gpio.h','compiler.h','generic/armcm_timer.h'):
            p=mock/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('/* Definitions supplied by the native C fixture. */\n')
        for name,rel in (('native_gpio.c','src/stm32/gpio.c'),('native_adc.c','src/stm32/adc.c')):(temp/name).write_text(native[rel])
        command=['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-sign-compare','-O2','-I'+str(mock),'-I'+str(KIT/'overlay/src/stm32'),'-DM300_NATIVE_GPIO_FILE="'+str(temp/'native_gpio.c')+'"','-DM300_NATIVE_ADC_FILE="'+str(temp/'native_adc.c')+'"',str(KIT/'tests/test_m300_stepfast_equivalence.c'),'-o',str(temp/'test')]
        subprocess.run(command,check=True)
        result=subprocess.run([str(temp/'test')],capture_output=True,text=True)
        if result.returncode:print(result.stderr)
        result.check_returncode()
    report={'status':'PASS','guard_equivalence_cases':6720,'existing_guard_rejection_scenarios':31,'physical_hardware':False,'measured_F103_cycles':False,'upstream_commit':patch_upstream.PIN,'source_sha256':hashlib.sha256((KIT/'overlay/src/stm32/m300_board.c').read_bytes()).hexdigest(),'summary':result.stdout}
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
