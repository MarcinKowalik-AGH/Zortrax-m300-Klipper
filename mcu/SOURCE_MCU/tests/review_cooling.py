#!/usr/bin/env python3
"""Independent firmware-source cooling checks; native register models, no hardware."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,subprocess,tempfile,zipfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sdk',required=True,type=Path)
parser.add_argument('--report',type=Path)
args=parser.parse_args();sdk=args.sdk.resolve()
spec=importlib.util.spec_from_file_location('r14_independent_patcher',sdk/'tools/patch_upstream.py')
patcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(patcher)
with zipfile.ZipFile(sdk/'UPSTREAM_KLIPPER_PINNED.zip') as archive:
    original={}
    for rel,digest in patcher.EXPECTED.items():
        data=archive.read('klipper-'+patcher.PIN+'/'+rel)
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Wrong pinned native source: '+rel)
        original[rel]=data.decode()
native=patcher.transformed(original)
case=Path(__file__).resolve().with_name('review_cooling.c')
with tempfile.TemporaryDirectory(prefix='m300-independent-cooling-') as td:
    work=Path(td);mock=work/'mock'
    for name in ('autoconf.h','board/irq.h','board/misc.h','command.h','internal.h','sched.h','gpio.h','compiler.h','generic/armcm_timer.h'):
        p=mock/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('/* Native fixture supplies definitions. */\n')
    (work/'native_gpio.c').write_text(native['src/stm32/gpio.c'])
    (work/'native_adc.c').write_text(native['src/stm32/adc.c'])
    command=['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-sign-compare','-O2',
        '-I'+str(mock),'-I'+str(sdk/'overlay/src/stm32'),
        '-DM300_REVIEW_BOARD_FIXTURE="'+str(sdk/'tests/test_m300_board.c')+'"',
        '-DM300_NATIVE_GPIO_FILE="'+str(work/'native_gpio.c')+'"',
        '-DM300_NATIVE_ADC_FILE="'+str(work/'native_adc.c')+'"',str(case),'-o',str(work/'review')]
    subprocess.run(command,check=True)
    result=subprocess.run([str(work/'review')],capture_output=True,text=True)
    if result.returncode:print(result.stderr)
    result.check_returncode()
source=sdk/'overlay/src/stm32'
report={'status':'PASS_EXISTING_COOLING_ORACLE_REGRESSION','physical_hardware':False,
    'physical_F103_cycles_measured':False,'cases_or_assertion_groups':int(re.search(r'review: (\d+)',result.stdout)[1]),
    'scope':['all4096raw x2hysteresisstates against independent stock transfer','ADC1 register sentinels unchanged through ADC2 acquisition','local data does not populate native ARM sensor flags','cold/hot boot and simulated complete power cycle','bounded calibration and conversion timeout, wrong-channel rejection','conversion-start timestamps prevent delayed EOC freshness extension','configured range inclusive boundaries for native/local cooling sources','hardfault latch versus communication/disarm/shutdown thermostat','GPIO write/toggle override and native cached handoff','stale-cache eviction across CYCCNT wrap','balanced IRQ ownership in all checked states'],
    'source_sha256':{name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in ('m300_board.c','m300_cooling.inc')},
    'review_test_sha256':hashlib.sha256(case.read_bytes()).hexdigest(),
    'native_pinned_commit':patcher.PIN,'result':result.stdout,
    'resolved_findings':['Paused local samples could revive after CYCCNT wrap; source now evicts age tags, clears paused local_seen and keeps cooling-native tags separate from ARM-native flags.','Delayed ADC2 EOC reads no longer stamp old conversions newly fresh; timestamps retain conversion-start time.','Fallback cooling cannot relax configured native ADC guard limits; local validity intersects configured and fixed envelopes.'],
    'blocking_findings_remaining':[],
    'physical_validation_remaining':['ADC2 measured temperature/analog settling on printer','actual no-host cold/hot power-cycle behavior','physical hotend fan handoff and RPM/airflow','CPU timing headroom under printing load']}
if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
