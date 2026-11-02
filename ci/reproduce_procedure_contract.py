"""Execute OEM 1.3.1 procedure control flow with declared environment hooks.

The supplied application is an input, never a release payload. Heating, UI
acknowledgements and motor peripherals are modeled. Material busy-wait loops
are accelerated at the motor boundary; their terminal request counts are read
independently from checked binary literals. Z reference arithmetic executes
all five original approach/release bodies without replacing their control flow.
"""
import argparse
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess

STOCK_SHA = '11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75'


def load_model(source, working):
    working.mkdir(parents=True, exist_ok=True)
    model = source/'source/model'
    binary = (model/'source/M300_stock_1.3.1_application.bin').read_bytes()
    assert hashlib.sha256(binary).hexdigest() == STOCK_SHA
    code = (model/'ALL_FUNCTIONS_semantic_names.c').read_text()
    count = 0
    for address, raw in re.findall(r'^L_([0-9A-F]+): ; /\* ([0-9a-f]+)  .*? \*/',code,re.M):
        offset = int(address,16)-0x08008000
        assert binary[offset:offset+len(bytes.fromhex(raw))] == bytes.fromhex(raw),address
        count += 1
    subprocess.run(['cc','-shared','-fPIC','-O0','-I'+str(model),
        str(model/'ALL_FUNCTIONS_semantic_names.c'),str(source/'tests/dispatch_test.c'),
        str(source/'tests/harness.c'),'-o',str(working/'harness.so')],check=True)
    py = (source/'tests/fw_model.py').read_text().replace(
        "BASE=HERE.parent/'source/model'",'BASE=pathlib.Path('+repr(str(model))+')')
    (working/'fw_model.py').write_text(py)
    spec = importlib.util.spec_from_file_location('oem_contract_model',working/'fw_model.py')
    fw = importlib.util.module_from_spec(spec);spec.loader.exec_module(fw)
    return fw,binary,count


def material(fw, operation, accept=True):
    f = fw.Firmware();events=[];direction=[1];totals=[]
    for address in (0x0800ccc8,0x0800cdec,0x08009bc0,0x080125dc,
                    0x08012df4,0x080098d8):
        f.stub(address)
    def heat(cpu):
        events.append(dict(kind='heat',target=int(cpu.r[0]),ready=int(cpu.r[1])))
        cpu.r[0]=1;return 1
    f.hook(0x080197c8,heat)
    def off(cpu):
        events.append(dict(kind='target',value=int(cpu.r[0])));return 1
    f.hook(0x080111d8,off)
    def screen(cpu):
        table=int(cpu.r[0]);index=(table-0x0801afd0)//20
        events.append(dict(kind='dialog',text_id=index,confirmation=bool(cpu.r[3])))
        cpu.r[0]=int(accept);return 1
    f.hook(0x08018ab4,screen);f.hook(0x08018bfc,screen)
    def gpio(cpu,sign):
        direction[0]=sign;return 1
    f.hook(0x0800c948,lambda cpu:gpio(cpu,1))
    f.hook(0x0800c8d4,lambda cpu:gpio(cpu,-1))
    def pulses(cpu):
        requests = 124800 if operation=='LOAD' else 105600 if direction[0]<0 else 144000
        totals.append(direction[0]*requests)
        events.append(dict(kind='transport',requested_pulses=direction[0]*requests))
        cpu.r[4]=requests-1  # accelerate only the physical transport boundary
        return 1
    f.hook(0x0800cfe8,pulses)
    def menu(cpu):
        events.append(dict(kind='menu',node=hex(f.u(0x200004e0))))
        return 1
    f.hook(0x08018c40,menu)
    entry={'LOAD':0x08014f24,'UNLOAD':0x08015004,'CHANGE':0x08015384}[operation]
    result=f.call(entry,limit=200000)
    return dict(operation=operation,accept=accept,events=events,requested_pulses=totals,
                terminal_menu=hex(f.u(0x200004e0)),instructions=result['steps'],
                motor_boundary_accelerated=True)


def z_reference(fw, revision, contacts):
    f=fw.Firmware();f.default_profile(revision)
    events=[];physical=[2000];direction=[-1];index=[-1]
    f.w(0x200004dc,physical[0])
    for addr in (0x0801329c,):f.stub(addr)
    f.stub(0x0801820c,1)
    f.hook(0x0800c948,lambda cpu:direction.__setitem__(0,-1) or 1)
    f.hook(0x0800c8d4,lambda cpu:direction.__setitem__(0,1) or 1)
    f.hook(0x0800ab3c,lambda cpu:physical.__setitem__(0,physical[0]+direction[0]*int(cpu.r[0])) or 1)
    f.hook(0x0800d068,lambda cpu:physical.__setitem__(0,physical[0]+direction[0]) or 1)
    def query(cpu):
        cpu.r[0]=int(physical[0]<=contacts[index[0]])
        return 1
    f.hook(0x08009a84,query)
    original=fw.lib.z_home_contact_approach_release__0800AC10
    original.argtypes=[ctypes.POINTER(fw.Arm),ctypes.c_uint32]
    def cycle(cpu):
        index[0]+=1
        original(ctypes.byref(cpu),0x0800ac10)
        events.append(dict(iteration=index[0]+1,contact_raw=contacts[index[0]],
                           release_raw=fw.signed(f.u(0x200004dc))))
        return 1
    f.hook(0x0800ac10,cycle)
    result=f.result(0x0800ab90,limit=1000000)
    assert len(events)==5 and result==events[-1]['release_raw']
    return dict(revision=revision,steps_per_mm=int(f.f(0x20006d30+68)),
                events=events,result_raw=result,averaging=False)


def wizard(fw, converge=True, pad_error=False):
    f=fw.Firmware();f.default_profile(5)
    events=[];heights={0:160,1:0,4:0,3:20,2:160}
    for address in (0x0800c8d4,0x0800ab3c,0x0800bba4,0x0800c1d4,
                    0x08019640,0x0801958c,0x0800b9e4,0x0800ba20,
                    0x080159e8,0x08019378):f.stub(address)
    f.stub(0x0801820c,1)
    def event(address,kind,**values):
        def emit(cpu):events.append(dict(kind=kind,**values));cpu.r[0]=1;return 1
        f.hook(address,emit)
    def heat(cpu):
        events.append(dict(kind='heat',target=int(cpu.r[0]),ready=int(cpu.r[1])))
        cpu.r[0]=1;return 1
    f.hook(0x080197c8,heat)
    event(0x0800b588,'home',axis='Y');event(0x0800b504,'home',axis='X')
    def center(cpu):
        events.append(dict(kind='center_contact'));cpu.r[0]=0xdead if pad_error else 0;return 1
    f.hook(0x0801456c,center)
    event(0x080111d8,'target',value=0)
    def menu(cpu):
        events.append(dict(kind='menu',node=hex(f.u(0x200004e0))));return 1
    f.hook(0x08018c40,menu)
    def offsets(cpu):f.w(cpu.r[0],0);f.w(cpu.r[1],0);return 1
    f.hook(0x080159a0,offsets)
    def screen(cpu):
        events.append(dict(kind='dialog',text_id=(int(cpu.r[0])-0x0801afd0)//20,
                           confirmation=bool(cpu.r[3])));return 1
    f.hook(0x08018ab4,screen)
    def point(cpu):
        p=int(cpu.r[0]);events.append(dict(kind='probe',point=p,raw=heights[p]))
        cpu.r[0]=heights[p];return 1
    f.hook(0x0800dc1c,point)
    def instruction(cpu):
        table=int(cpu.r[0]);delta,turns=struct.unpack('<dd',f.bytes(cpu.r[13],16))
        events.append(dict(kind='instruction',table=hex(table),delta_mm=delta,turns=turns))
        if converge:
            if table in (0x0801ba0c,0x0801ba20):heights[4]=160
            elif table in (0x0801ba34,0x0801ba48):heights[3]=160
            else:heights[0]=heights[1]=160
        return 1
    f.hook(0x08018b90,instruction)
    def failure(cpu):events.append(dict(kind='failure',error=41 if cpu.r[0]==0 else 42));return 1
    f.hook(0x0800b490,failure)
    def diagram(cpu):
        events.append(dict(kind='diagram',raw=[fw.signed(f.u(cpu.r[0]+4*i)) for i in range(5)]))
        return 1
    f.hook(0x0800f0d8,diagram)
    f.call(0x0800ad1c,limit=2000000)
    return dict(converge=converge,pad_error=pad_error,events=events)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('working',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();fw,binary,instructions=load_model(a.source.resolve(),a.working.resolve())
    offsets=[]
    for seed in (0,1,42,1000,0x7fffffff,0xffffffff):
        f=fw.Firmware();f.result(0x08008188,seed);f.w(0x200015b1,0,1)
        f.call(0x080159a0,0x2000a000,0x2000a004)
        offsets.append(dict(seed=seed,xy=[fw.signed(f.u(0x2000a000)),fw.signed(f.u(0x2000a004))]))
    # Verified literals at the exact loop comparison sites, independent of hooks.
    def word(a):return struct.unpack_from('<I',binary,a-0x08008000)[0]
    assert word(0x08014fdc)==124800
    assert word(0x0801971c-4)==105600
    record=dict(source_sha256=STOCK_SHA,verified_instructions=instructions,
        method='Recovered OEM instructions with declared physical/UI boundary models',
        material=[material(fw,op,accept) for op in ('LOAD','UNLOAD') for accept in (True,False)]
                 +[material(fw,'CHANGE')],
        z_references=[z_reference(fw,revision,[1500,1520,1480,1510,1490]) for revision in (4,5)],
        wizard=[wizard(fw,True),wizard(fw,False),wizard(fw,True,pad_error=True)],xy_offsets=offsets)
    a.output.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(status='PASS_OEM_PROCEDURE_REPRODUCTION',material_cases=len(record['material']),
                         z_profiles=len(record['z_references']),wizard_cases=len(record['wizard']))))


if __name__=='__main__':main()
