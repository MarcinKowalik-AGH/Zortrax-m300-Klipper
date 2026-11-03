"""Reproduce OEM Maintenance with declared UI/heater/button boundaries.

Fan entry, toggles, saved-request restoration and PWM register writes execute
their recovered bodies. Fan-menu font/layout execute the original renderer.
The private firmware remains an input, never part of the release.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import zlib

from reproduce_procedure_contract import STOCK_SHA, load_model

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'host/klippy'))
from extras.m300_maintenance_ui import fan_frame
from extras.m300_oled_render import Frame


def fans(fw, initial):
    f=fw.Firmware()
    f.call(0x0800c0ac,initial[0]);f.call(0x0800c0c4,initial[1])
    events=[]
    def record():
        events.append(dict(requests=[f.u(0x2000000a,1),f.u(0x2000000b,1)],
            ccr=[f.u(0x40012c3c,2),f.u(0x40012c40,2)]))
    f.call(0x08014940);record()
    for callback in (0x080157f0,0x080157c8,0x080157f0,0x080157c8):
        f.call(callback);record()
    event=fw.signed(f.u(0x08021c5c,1),8)
    f.call(0x08014980,event);record()
    assert events[0]['requests']==[0,0]
    assert [e['requests'] for e in events[1:5]]==[[0,150],[150,150],[150,0],[0,0]]
    assert events[-1]['requests']==list(initial)
    for e in events:assert e['ccr']==[255-v for v in e['requests']]
    return dict(initial=list(initial),actions=['ENTER','UPPER','LOWER','UPPER','LOWER','BACK'],events=events)


def heat(fw, accept):
    f=fw.Firmware();events=[]
    for a in (0x08009adc,0x0800c290):f.stub(a)
    def ready(c):
        events.append(dict(kind='heat',target=int(c.r[0]),ready=int(c.r[1])))
        c.r[0]=int(accept);return 1
    def dialog(c):
        events.append(dict(kind='dialog',table=hex(c.r[0]),confirmation=bool(c.r[3])));return 1
    def off(c):events.append(dict(kind='target',value=int(c.r[0])));return 1
    def menu(c):events.append(dict(kind='menu',node=hex(f.u(0x200004e0))));return 1
    f.hook(0x080197c8,ready);f.hook(0x08018ab4,dialog)
    f.hook(0x080111d8,off);f.hook(0x08018c40,menu)
    f.call(0x08015ed0,1)
    assert events[0]==dict(kind='heat',target=260,ready=258)
    assert events[-2:]==[dict(kind='target',value=0),dict(kind='menu',node='0x20000680')]
    return dict(accept=accept,events=events)


def platform(fw, selected, pressed, current=0x20000680):
    f=fw.Firmware();f.w(0x200004e0,current);f.w(0x20000680+13,selected,1)
    f.stub(0x0800c808,0 if pressed else 1)
    for a in (0x08015324,0x08015354):f.stub(a,label='Z motor boundary')
    f.call(0x08015d1c)
    calls=[e['call'] for e in f.events if e['label']=='Z motor boundary']
    return dict(selected=selected,pressed=pressed,menu=hex(current),motor_calls=calls)


def frame(fw, upper, lower, selected):
    f=fw.Firmware();f.w(0x200004e0,0x20000748);f.w(0x20000748+13,selected,1)
    f.w(0x200005fb,upper,1);f.w(0x200005fa,lower,1);f.w(0x200015b0,0,1)
    # Only the final physical SPI transfer is intercepted.
    f.stub(0x0800c290)
    f.call(0x08018c40,limit=500000)
    actual=Frame();actual.raw[:]=f.bytes(0x200016c8,8192)
    reference=actual.wire_bytes()
    expected=fan_frame('(Enabled)' if upper else '(Disabled)',
        '(Enabled)' if lower else '(Disabled)','',selected,Frame)
    assert reference==expected,(upper,lower,selected)
    return dict(upper=upper,lower=lower,selected=selected,
        sha256=hashlib.sha256(reference).hexdigest(),
        wire_zlib_b64=base64.b64encode(zlib.compress(reference,9)).decode())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('working',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();fw,binary,instructions=load_model(a.source.resolve(),a.working.resolve())
    result=dict(source_sha256=STOCK_SHA,verified_instructions=instructions,
        method='Recovered OEM instruction semantics; declared UI/heater/button boundaries',
        fans=[fans(fw,pair) for pair in ((0,0),(99,33),(255,150))],
        heat=[heat(fw,accept) for accept in (False,True)],
        platform=[platform(fw,selected,pressed) for selected in range(7) for pressed in (False,True)]
                 +[platform(fw,4,True,0x20000748)],
        frames=[frame(fw,u,l,s) for u in (False,True) for l in (False,True) for s in range(3)])
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='PASS_OEM_MAINTENANCE_REPRODUCTION',fan_sessions=3,
        heat_branches=2,platform_cases=len(result['platform']),matched_original_frames=12)))


if __name__=='__main__':main()
