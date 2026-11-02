"""Actual pinned Klipper checker, synthetic thermal traces. No heater operation."""
from pathlib import Path
import importlib.util,json,logging,types
B=Path(__file__).resolve().parents[1]
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--upstream',type=Path,required=True);args=ap.parse_args()
src=args.upstream/'klippy/extras/verify_heater.py'
spec=importlib.util.spec_from_file_location('native_verify_replay',src)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def run(gain_time, values):
    faults=[]
    printer=types.SimpleNamespace(register_event_handler=lambda *a:None,
        get_reactor=lambda:types.SimpleNamespace(NEVER=1e99),
        invoke_shutdown=faults.append)
    cfg=types.SimpleNamespace(get_printer=lambda:printer,get_name=lambda:'verify_heater extruder',
        getfloat=lambda name,default,**kw:gain_time if name=='check_gain_time' else default)
    checker=m.HeaterCheck(cfg)
    current=[0.,0.]
    checker.heater=types.SimpleNamespace(get_temp=lambda t:current)
    when=None
    for t,(temp,target) in enumerate(values):
        current[:]=temp,target
        checker.check_event(float(t))
        if faults:when=t;break
    return when

logging.getLogger().handlers=[logging.FileHandler(B/'evidence/VERIFY_GAIN.log')]
rows=[]
def check(name,actual,expected):
    assert actual==expected,(name,actual,expected)
    rows.append({'case':name,'actual':actual,'expected':expected,'PASS':True})

# Synthetic continuation approximates the observed initial cooling/lag, then
# assumes a 0.18 C/s recovery. It is explicitly NOT a measured future trace.
lag=[(167.-.4*t if t<=10 else 163.+.18*(t-10),220.) for t in range(61)]
check('default20 rejects modeled delayed warm restart',run(20.,lag),21)
check('candidate40 allows modeled recovery',run(40.,lag),None)
check('candidate40 still rejects no heat response',run(40.,[(25.,220.)]*61),41)
check('default20 no heat baseline',run(20.,[(25.,220.)]*61),21)
check('same max_error catches loss after reaching target',
      run(40.,[(220.,220.)]*5+[(190.,220.)]*20),9)
check('target OFF has no heating-demand fault',run(40.,[(25.,0.)]*90),None)
check('steady near target remains valid',run(40.,[(219.,220.)]*90),None)
(B/'evidence/VERIFY_GAIN.json').write_text(json.dumps({'status':'PASS','cases':rows,
    'checker':'unchanged native verify_heater.py','physical_hardware':False,
    'synthetic_continuation_is_not_physical_validation':True,
    'candidate_config':{'check_gain_time':40,'heating_gain':2,'hysteresis':5,'max_error':120}},indent=2)+'\n')
print(json.dumps({'status':'PASS','cases':len(rows),'physical_hardware':False}))
