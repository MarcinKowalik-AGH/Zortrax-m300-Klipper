#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Export ONE native 4bpp master to host JSON, MCU ROM and review assets.

Run --check in CI. Authoring requires Pillow for previews only; runtime never
imports it. Export is byte-preserving; it does not shade, sharpen or resize.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile
import zlib
from tone_activity import indexed_rows
from render_ui_symbols import SYMBOLS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/assets/ui-symbols'
HOST=ROOT/'host/klippy/extras'
MCU=ROOT/'mcu/SOURCE_MCU/overlay/src/stm32'

def derived():
    master=json.loads((OUT/'native_frames.json').read_text())
    assert master['style']=='OEM_NATIVE_TONES_V1'
    assert (master['width'],master['height'],master['frame_ms'])==(50,50,500)
    assert len(master['symbols'])==24
    raw={name:[bytes.fromhex(f) for f in rec['frames']]for name,rec in master['symbols'].items()}
    runtime={'format':'M300_ACTIVITY_SPRITES_V1','style':master['style'],
             'source_sha256':hashlib.sha256((OUT/'native_frames.json').read_bytes()).hexdigest(),'symbols':{}}
    for name,frames in raw.items():
        assert len(frames)==4 and all(len(f)==1250 for f in frames)
        checks=[hashlib.sha256(f).hexdigest() for f in frames]
        assert checks==master['symbols'][name]['sha256']
        runtime['symbols'][name]={'width':50,'height':50,'frame_ms':500,
            'frames':[{'sha256':c,'zlib_b64':base64.b64encode(zlib.compress(f,9)).decode()}
                      for c,f in zip(checks,frames)]}
    spec=json.loads((HOST/'m300_error_codes.json').read_text())
    names=list(dict.fromkeys(x['icon']for x in spec['codes']+spec['native']))
    return raw,{
        HOST/'m300_activity_sprites.json':(json.dumps(runtime,indent=2)+'\n').encode(),
        MCU/'m300_oled_activity.inc':indexed_rows([raw[n]for n in ('waiting_klipper','connection_lost')],'local_activity').encode(),
        MCU/'m300_error_icons.inc':indexed_rows([raw[n]for n in names],'local_error').encode(),
    }

def image(raw):
    from PIL import Image
    return Image.frombytes('L',(50,50),bytes(v*17 for b in raw for v in (b>>4,b&15)))

def svg_frame(raw):
    # Every path is an exact native pixel; no curves, antialias or inference.
    groups={}
    for i,v in enumerate(v for b in raw for v in (b>>4,b&15)):
        if v:groups.setdefault(v,[]).append('M%d %dh1v1h-1z'%(i%50,i//50))
    return ''.join('<path fill="#%02x%02x%02x" d="%s"/>'%(v*17,v*17,v*17,' '.join(parts))for v,parts in sorted(groups.items()))

def visuals(raw):
    from PIL import Image,ImageDraw,ImageFont
    import sys
    sys.path.insert(0,str(ROOT/'host'))
    from klippy.extras.m300_oled_preview import PALETTE
    font=ImageFont.load_default()
    images={name:[image(f)for f in frames]for name,frames in raw.items()}
    result={}
    for name,frames in raw.items():
        groups=[]
        for i,f in enumerate(frames):
            values=';'.join('1'if n==i else'0'for n in(0,1,2,3,0))
            groups.append('<g opacity="%d">%s<animate attributeName="opacity" values="%s" keyTimes="0;.25;.5;.75;1" dur="2s" repeatCount="indefinite" calcMode="discrete"/></g>'%(i==0,svg_frame(f),values))
        result[OUT/(name+'.svg')]=('<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" viewBox="0 0 50 50" shape-rendering="crispEdges"><title>'+name+' — native 4bpp project artwork</title><rect width="50" height="50" fill="black"/>'+''.join(groups)+'</svg>\n').encode()
    # Existing download contract is retained; images are replaced by exact master pixels.
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED)as z:
        def put(n,data):
            info=zipfile.ZipInfo(n,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,data)
        for name,frames in images.items():
            put('svg/'+name+'.svg',result[OUT/(name+'.svg')]);gif=io.BytesIO()
            frames[0].save(gif,format='GIF',save_all=True,append_images=frames[1:],duration=500,loop=0,disposal=2,optimize=False)
            put('gif/'+name+'.gif',gif.getvalue())
            for i,f in enumerate(frames):
                png=io.BytesIO();f.save(png,format='PNG');put('frames/%s_%d.png'%(name,i),png.getvalue())
        for name in('catalog.json','native_frames.json'):put(name,(OUT/name).read_bytes())
    result[OUT/'M300_ACTIVITY_SYMBOLS_24.zip']=buffer.getvalue()
    for prefix,entries in(('preview',SYMBOLS[:12]),('preview_additional',SYMBOLS[12:])):
        # Contact sheets use the same exact native pixels as individual SVGs.
        cells=[]
        from xml.sax.saxutils import escape
        for i,(name,_,_) in enumerate(entries):
            x=(i%4)*180+15; y=(i//4)*195+8
            groups=[]
            for j,frame in enumerate(raw[name]):
                values=';'.join('1' if k==j else '0' for k in (0,1,2,3,0))
                groups.append('<g opacity="%d">%s<animate attributeName="opacity" values="%s" keyTimes="0;.25;.5;.75;1" dur="2s" repeatCount="indefinite" calcMode="discrete"/></g>'%(j==0,svg_frame(frame),values))
            cells.append('<g transform="translate(%d %d) scale(3)"><rect width="50" height="50" fill="black"/>%s</g><text x="%d" y="%d" fill="white" font-family="monospace" font-size="12">%s</text>'%(x,y,''.join(groups),x,y+170,escape(name)))
        result[OUT/(prefix+'.svg')]=('<svg xmlns="http://www.w3.org/2000/svg" width="720" height="585" viewBox="0 0 720 585" shape-rendering="crispEdges"><title>Native master activity frames</title><rect width="720" height="585" fill="#101418"/>'+''.join(cells)+'</svg>\n').encode()
        pages=[]
        for f in range(4):
            p=Image.new('RGB',(4*180,3*195),(16,20,24));d=ImageDraw.Draw(p)
            for i,(name,_,_)in enumerate(entries):
                x=(i%4)*180+15;y=(i//4)*195+8
                gray=images[name][f];rgb=Image.frombytes('RGB',(50,50),bytes(c for v in gray.tobytes()for c in PALETTE[v//17]))
                p.paste(rgb.resize((150,150),Image.Resampling.NEAREST),(x,y));d.text((x,y+156),name,fill='white',font=font)
            pages.append(p)
        for ext in('png','gif'):
            b=io.BytesIO()
            if ext=='png':pages[0].save(b,format='PNG')
            else:pages[0].save(b,format='GIF',save_all=True,append_images=pages[1:],duration=500,loop=0,disposal=2,optimize=False)
            result[OUT/(prefix+'.'+ext)]=b.getvalue()
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--check',action='store_true');ap.add_argument('--visuals',action='store_true');a=ap.parse_args()
    raw,files=derived()
    if a.visuals: files.update(visuals(raw))
    for path,data in files.items():
        if a.check:
            if not path.exists()or path.read_bytes()!=data:raise SystemExit('Stale derived artwork: '+str(path.relative_to(ROOT)))
        else:path.write_bytes(data)
    print('PASS unified master export: %d generated files'%len(files))

if __name__=='__main__':main()
