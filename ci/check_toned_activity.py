#!/usr/bin/env python3
"""Audit native icon geometry, tonal transport and ROM budget; no printer I/O."""
import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zlib

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT/'host/klippy/extras'

def load(name, path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def levels(raw):
    return [v for b in raw for v in (b >> 4,b & 15)]

def packets(raw, transport):
    ops=list(transport.fast_blocks(raw))
    out=bytearray()
    for _,(dc,encoding,count,data),_ in ops:
        assert dc==1 and len(data)<=32 and count<=256
        before=len(out)
        if not encoding:out.extend(data)
        else:
            at=0
            while at<len(data):
                code=data[at];at+=1;n=(code&127)+1
                if code&128:out.extend(bytes([data[at]])*n);at+=1
                else:out.extend(data[at:at+n]);at+=n
            assert at==len(data)
        assert len(out)-before==count
    assert bytes(out)==raw
    return dict(encoded_payload=sum(len(op[1][3]) for op in ops),packets=len(ops))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.ci/reports/OLED_TONES.json')
    args=parser.parse_args()
    before=json.loads((ROOT/'docs/assets/ui-symbols/native_frames_beta20.json').read_text())
    now=json.loads((HOST/'m300_activity_sprites.json').read_text())
    assert len(now['symbols'])==24 and set(now['symbols'])==set(before['symbols'])
    transport=load('tone_transport',HOST/'m300_oled_transport.py')
    decoder=load('tone_artwork',HOST/'m300_activity_graphics.py').ActivityGraphics()
    all_frames=[]
    for name,record in now['symbols'].items():
        assert (record['width'],record['height'],record['frame_ms'])==(50,50,500)
        assert len(record['frames'])==4
        frame_hashes=[]
        for index,record_frame in enumerate(record['frames']):
            raw=zlib.decompress(base64.b64decode(record_frame['zlib_b64'],validate=True))
            old=bytes.fromhex(before['symbols'][name]['frames'][index])
            assert len(raw)==1250 and len(old)==1250
            digest=hashlib.sha256(raw).hexdigest();frame_hashes.append(digest)
            assert digest==record_frame['sha256']
            assert decoder.get('activity:'+name,index*0.5)==(50,50,raw)
            x,y=levels(old),levels(raw)
            assert {0,15}<=set(y) and any(0<v<15 for v in y)
            assert {v for v in y} <= set(range(16))
            # Never erase/dim the original high-contrast signal.
            assert all(v==15 for u,v in zip(x,y) if u==15)
            for i,(u,v) in enumerate(zip(x,y)):
                if not u and v:
                    assert v<=6
                    px,py=i%50,i//50
                    assert any(x[qy*50+qx] for qy in range(max(0,py-1),min(50,py+2))
                               for qx in range(max(0,px-1),min(50,px+2)))
            all_frames.append(dict(symbol=name,frame=index,levels=sorted(set(y)),
                                   before=packets(old,transport),after=packets(raw,transport)))
        assert len(set(frame_hashes))==4
    assert decoder._frame.cache_info().currsize<=32
    mcu=ROOT/'mcu/SOURCE_MCU/overlay/src/stm32'
    rom=0
    for prefix,file in [('local_activity','m300_oled_activity.inc'),('local_error','m300_error_icons.inc')]:
        s=(mcu/file).read_text()
        encoded=int(re.search(prefix+r'_rle\[(\d+)\]',s)[1])
        banks=int(re.search(prefix+r'_frames\[(\d+)\]\[4\]\[50\]',s)[1])
        rom+=encoded+banks*4*50*2
    assert rom<=16000,rom
    assert 'static uint8_t local_row[128];' in (mcu/'m300_oled_local.inc').read_text()
    report=dict(status='PASS_OLED_TONES',symbols=24,frames=len(all_frames),
                native_icon_bytes=1250,frame_ms=500,original_bright_pixels_preserved=True,
                rle_lossless_all_frames=True,mcu_icon_rom_bytes=rom,
                mcu_scanline_sram_bytes=128,physical_hardware_tested=False,results=all_frames)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))

if __name__=='__main__':main()
