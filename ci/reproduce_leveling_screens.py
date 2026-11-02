"""Generate reference pixels by executing the recovered OEM register-C code.

Input: source_evidence_m04_binary from the supplied source archive. Only the
SPI flush and physical button boundary are modeled; text, font mapping,
compressed-image decode and drawing execute their recovered instructions.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'host/klippy'))
from extras.m300_leveling_oem import describe, render, turn_unit
from extras.m300_oem_procedure_ui import describe as describe_service
from extras.m300_oem_graphics import OEMGraphics, STOCK_SHA256
from extras.m300_oled_render import Frame


def reproduce(source, working, output):
    working.mkdir(parents=True, exist_ok=True)
    model = source/'source/model'
    binary = (model/'source/M300_stock_1.3.1_application.bin').read_bytes()
    assert hashlib.sha256(binary).hexdigest() == STOCK_SHA256
    instructions = 0
    code_bytes = 0
    for address, code in re.findall(r'^L_([0-9A-F]+): ; /\* ([0-9a-f]+)  .*? \*/',
                    (model/'ALL_FUNCTIONS_semantic_names.c').read_text(), re.M):
        offset = int(address,16)-0x08008000
        raw = bytes.fromhex(code)
        assert binary[offset:offset+len(raw)] == raw, address
        instructions += 1
        code_bytes += len(raw)
    command = ['cc', '-shared', '-fPIC', '-O0', '-I'+str(model),
               str(model/'ALL_FUNCTIONS_semantic_names.c'),
               str(source/'tests/dispatch_test.c'), str(source/'tests/harness.c'),
               '-o', str(working/'harness.so')]
    subprocess.run(command, check=True)
    py = (source/'tests/fw_model.py').read_text().replace(
        "BASE=HERE.parent/'source/model'", 'BASE=pathlib.Path('+repr(str(model))+')')
    (working/'fw_model.py').write_text(py)
    spec = importlib.util.spec_from_file_location('m300_oem_reference', working/'fw_model.py')
    fw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fw)
    sprites = OEMGraphics()
    statuses = [dict(state=s) for s in ('WAIT_WARNING','WAIT_TIGHTEN','HOMING','HEATING')]
    statuses += [dict(state='PROBING', measurement_stage=s)
                 for s in ('initial','rear','front','center')]
    statuses += [dict(state='ADJUST', instruction=dict(screw=s, action=a,
                      delta_mm=-.4 if a=='LOOSEN' else .4, turns=.75))
                 for s in ('rear_left','rear_right','front') for a in ('LOOSEN','TIGHTEN')]
    statuses += [dict(state='FAULT',reason='NO_RELEASE: PC7 remains active'),
                 dict(state='FAULT',reason='maximum screw instructions reached'),
                 dict(state='REVIEW',review=[-.2,.1,0.,-.4,-.1])]
    statuses += [dict(state=state,operation=operation,native_control=True,oem_owner=owner)
        for owner,operation,state in (
            ('m300_maintenance','HOTEND','WAIT_CONFIRM'),
            ('m300_filament','LOAD','WAIT_INSERT'),('m300_filament','LOAD','LOADING'),
            ('m300_filament','UNLOAD','UNLOADING'),('m300_filament','UNLOAD','WAIT_REMOVE'))]
    records = []
    for li, language in enumerate(('EN','PL','FR','DE','ES')):
        for status in statuses:
            f = fw.Firmware()
            f.w(0x200015b0, li, 1)
            display = bytearray(8192)
            def flush(cpu):
                raw = f.bytes(0x200016c8,8192)
                offset = cpu.r[0]
                if offset == 0:
                    display[:] = raw
                elif offset == 48:
                    display[96*64:] = raw[:32*64]
                else:
                    raise AssertionError('Unexpected OLED column offset '+str(offset))
                return 1
            f.hook(0x0800c290, flush)
            screen = (describe_service(status['oem_owner'],status,language)
                      if 'oem_owner' in status else describe(status, language))
            if status['state'] == 'REVIEW':
                # Original result display assumes 800 counts/mm. Its physical
                # composition is the reference; the port fixes HW05 units.
                f.write(0x2000a000, struct.pack('<5i', *[round(v*800) for v in status['review']]))
                f.call(0x0800f0d8,0x2000a000)
            else:
                if screen['descriptor']:
                    offset = int(screen['descriptor'],16)-0x08008000
                    table, flags, sprite = struct.unpack_from('<III',binary,offset)
                else:
                    table, flags, sprite = 0x0801b96c, 0, 0x0801c2b8
                if status['state'] == 'ADJUST':
                    instruction = status['instruction']
                    unit = turn_unit(instruction,language).encode()+b'\0'
                    f.write(0x2000a000,unit)
                    delta = struct.unpack('<f',struct.pack('<f',instruction['delta_mm']))[0]
                    f.write(0x2000f000, struct.pack('<ddI',delta,instruction['turns'],0x2000a000))
                    f.call(0x08018b90,table,flags,sprite,0)
                else:
                    f.call(0x08018ab4,table,flags,sprite,0)
            reference = Frame()
            reference.raw[:] = display
            expected = reference.wire_bytes()
            actual = render(screen,sprites,Frame)
            different = sum(a!=b for a,b in zip(expected,actual))
            if different:
                raise AssertionError((language,status,different))
            records.append(dict(language=language,status=status,
                sha256=hashlib.sha256(expected).hexdigest(),
                wire_zlib_b64=base64.b64encode(zlib.compress(expected,9)).decode()))
    provenance = {'source_application_sha256': hashlib.sha256(binary).hexdigest(),
                  'model_files': {str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (model/'ALL_FUNCTIONS_semantic_names.c',model/'arm_semantics.h',
                              source/'tests/dispatch_test.c',source/'tests/harness.c')},
                  'verified_instruction_comments':instructions, 'verified_code_bytes':code_bytes,
                  'method':'Original recovered instruction model; SPI flush boundary only is intercepted',
                  'frames':records}
    output.write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'matched_original_frames':len(records),'bytes_per_frame':8192}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('working',type=Path)
    p.add_argument('output',type=Path)
    a = p.parse_args()
    reproduce(a.source.resolve(),a.working.resolve(),a.output.resolve())
