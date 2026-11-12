#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare master -> live host -> PNG and real C autonomous MCU pixels.

Uses native isolated register doubles, not a printer. Existing pixel/browser
and UART transport checks remain separate; no hardware acceptance is inferred.
"""
import base64
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT=Path(__file__).resolve().parents[1]
HOST=ROOT/'host/klippy/extras'
sys.path.insert(0,str(ROOT/'host'))
from klippy.extras.m300_oem_graphics import OEMGraphics, ICON_STYLE
from klippy.extras.m300_oled_preview import encoded_png
from klippy.extras.m300_menu_ui import M300MenuUI
from design_activity_artwork import PALETTE, build_master
from export_activity_artwork import derived


def unpack(raw):return [v for b in raw for v in (b>>4,b&15)]

def extract_icon(wire):
    assert len(wire)==8192
    return b''.join(wire[(7+y)*128+100:(7+y)*128+125]for y in range(50))

def png_wire(png):
    assert png[:8]==b'\x89PNG\r\n\x1a\n'
    at=8;compressed=b''
    while at<len(png):
        n=struct.unpack_from('>I',png,at)[0];typ=png[at+4:at+8];body=png[at+8:at+8+n]
        if typ==b'IHDR':assert struct.unpack('>IIBBBBB',body)==(256,64,4,3,0,0,0)
        if typ==b'IDAT':compressed+=body
        at+=12+n
    data=zlib.decompress(compressed);assert len(data)==64*129
    assert all(data[y*129]==0 for y in range(64))
    return b''.join(data[y*129+1:(y+1)*129]for y in range(64))

def main():
    master=json.loads((ROOT/'docs/assets/ui-symbols/native_frames.json').read_text())
    assert master==build_master()
    raw,generated=derived()
    assert all(p.read_bytes()==v for p,v in generated.items())
    assert ICON_STYLE==master['style']=='OEM_NATIVE_TONES_V1'
    original=json.loads((ROOT/'docs/assets/ui-symbols/native_frames_beta20.json').read_text())
    runtime=OEMGraphics()
    compatibility=[OEMGraphics(sharp=False),OEMGraphics(sharp=True)]
    count=0
    for name,frames in raw.items():
        for f,expected in enumerate(frames):
            got=runtime.get('activity:'+name,f*.5)
            assert got==(50,50,expected)
            assert all(x.get('activity:'+name,f*.5)==got for x in compatibility)
            old=bytes.fromhex(original['symbols'][name]['frames'][f])
            a,b=unpack(old),unpack(expected)
            assert set(b)<=set(PALETTE) and len(set(b))>=3
            assert all(bool(x)==bool(y)for x,y in zip(a,b)),(name,f,'halo or erased pixel')
            wire=bytearray(8192)
            for y in range(50):wire[(7+y)*128+100:(7+y)*128+125]=expected[y*25:y*25+25]
            assert png_wire(encoded_png(bytes(wire)))==wire
            count+=1
    assert count==96
    assert hashlib.sha256((HOST/'m300_oem_sprites_131.json').read_bytes()).hexdigest()=='006058afcac0b9b888762a336935675bcac625b6f888e1fb10fca2872187c387'
    oem_count=0
    for addr,desc in runtime.frames.items():
        for f,item in enumerate(desc['frames']):
            now=f*desc['period_ticks']/1000+.00001
            expected=zlib.decompress(base64.b64decode(item['zlib_b64']))
            assert all(x.get(addr,now)==(50,50,expected)for x in [runtime]+compatibility)
            oem_count+=1
    assert oem_count==61
    spec=json.loads((HOST/'m300_error_codes.json').read_text())
    cases=[(1,0,0,'waiting_klipper'),(2,0,0,'connection_lost')]
    cases += [(3,x['code'],0,x['icon'])for x in spec['codes']]
    cases += [(3,0,x['kind'],x['icon'])for x in spec['native']if x['kind']]
    with tempfile.TemporaryDirectory(prefix='m300-common-pixels-')as td:
        exe=Path(td)/'renderer'
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
            str(ROOT/'mcu/SOURCE_MCU/tests/test_shared_artwork.c'),'-o',str(exe)],check=True)
        mcu_count=0
        for reason,code,kind,name in cases:
            for f in range(4):
                wire=subprocess.check_output([str(exe),str(reason),str(code),str(kind),str(f)])
                expected=raw[name][f]
                assert extract_icon(wire)==expected,(reason,code,kind,name,f,'actual C pixel mismatch')
                assert png_wire(encoded_png(wire))==wire
                mcu_count+=1
    # Exercise the real UI constructor, not only direct asset access.
    from project import stage_host_update
    package=stage_host_update(ROOT/'.ci/artwork-host')
    sys.path[:0]=[str(package),str(package/'tests')]
    from test_settings_information import session
    from test_activity_graphics import right_icon
    for legacy in (False,True):
        with session() as h:
            before=h.config.getboolean
            h.config.getboolean=lambda key,default:legacy if key=='sharp_icons'else before(key,default)
            h.oled.menu_reverse=True
            h.ui=M300MenuUI(h.config);h.objects['m300_menu_ui']=h.ui
            assert h.ui.get_status(h.now)['icon_style']==ICON_STYLE
            h.menu.page='klipper';h.menu.rows=lambda now:('Klipper',[
                ('Back',('page','main')),('Bed mesh',('native_gcode','BED_MESH'))])
            h.oled.page,h.oled.selection='m04',1;h.oled._render_key=None
            h.oled._render(h.now)
            assert right_icon(h.oled._render_wire)==raw['bed_mesh'][0]
            assert not any(x[0]in('move','heat','fan')for x in h.events)
    report=dict(status='PASS_UNIFIED_OLED_ARTWORK',style=ICON_STYLE,
        activity_symbols=24,activity_frames=count,oem_descriptors=37,oem_frames=oem_count,
        real_c_rendered_frames=mcu_count,real_c_compared_icon_pixels=mcu_count*2500,
        host_png_roundtrips=count,autonomous_png_roundtrips=mcu_count,
        original_oem_file_unchanged=True,native_silhouettes_unchanged=True,
        outside_halo_pixels=0,legacy_sharp_option_has_no_pixel_effect=True,
        mcu_subset_matches_host=True,physical_printer_tested=False)
    out=ROOT/'.ci/reports/OLED_UNIFIED.json';out.parent.mkdir(exist_ok=True,parents=True)
    out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
