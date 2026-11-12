#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native-grid art direction for the existing 24 activity silhouettes.

Authoring only. No blur, dilation, resampling, runtime filters or new lighted
pixels outside the approved native silhouette. The exported JSON is the one
master consumed by both host and autonomous MCU exporters. Original OEM assets
are never edited. Explicit semantic regions keep warnings/active marks bright.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'docs/assets/ui-symbols/native_frames_beta20.json'
MASTER = ROOT/'docs/assets/ui-symbols/native_frames.json'
STYLE = 'OEM_NATIVE_TONES_V1'
PALETTE = (0, 4, 8, 11, 14, 15)
# Rectangles specify intentionally secondary structures, not blur kernels.
# Coordinates are inclusive and always clipped to the original foreground mask.
SECONDARY = {
    'bed_mesh': [(5,9,44,42)],
    'heat_nozzle': [(14,6,35,17)],
    'heat_bed': [(4,33,45,46)],
    'cooling': [(8,4,24,45)],
    'fan_upper': [], 'fan_lower': [],
    'sd_read': [(9,3,40,45)],
    'file_convert': [(2,6,20,32),(29,6,47,32)],
    'clean_nozzle': [(14,6,35,33)],
    'link_status': [(2,13,13,34),(36,13,47,34)],
    'oled_brightness': [(3,4,46,41)],
    'led_brightness': [(8,3,41,40)],
    'filament_jam': [(5,7,21,23),(29,7,45,23)],
    'filament_runout': [(4,4,32,32)],
    'waiting_klipper': [(2,11,15,35),(34,11,47,35)],
    'connection_lost': [(2,11,15,35),(34,11,47,35)],
    'hotend_overheat': [(3,7,25,35)],
    'bed_overheat': [(2,28,27,43)],
    'sensor_fault': [(5,4,23,45)],
    'heating_failed': [(4,7,25,35)],
    'probe_contact_fault': [(5,4,29,32),(5,39,30,45)],
    'platform_connector': [(2,10,23,42),(26,10,47,42)],
    'emergency_stop': [],
    'firmware_update': [(10,16,39,43)],
}
# Meaning-bearing elements keep full luminance throughout every animation.
ACCENTS = {
    'bed_mesh': [(20,0,30,8),(22,24,28,30)],
    'heat_nozzle': [(9,28,41,49),(21,30,29,34)],
    'heat_bed': [(7,0,43,31)],
    'cooling': [(27,5,44,38),(12,31,20,40)],
    'fan_upper': [(18,0,32,5),(22,22,28,28)],
    'fan_lower': [(18,44,32,49),(22,22,28,28)],
    'sd_read': [(14,5,34,16)],
    'file_convert': [(5,33,43,46)],
    'clean_nozzle': [(15,30,45,48)],
    'link_status': [(14,14,36,30)],
    'oled_brightness': [(11,12,38,28),(1,43,49,49)],
    'led_brightness': [(0,12,7,21),(43,12,49,21),(1,43,49,49)],
    'filament_jam': [(21,0,29,49),(34,30,49,49)],
    'filament_runout': [(33,30,49,46)],
    'waiting_klipper': [(16,20,33,28),(16,39,34,45)],
    'connection_lost': [(19,17,31,31),(15,38,35,42)],
    'hotend_overheat': [(30,5,49,49),(24,0,49,13)],
    'bed_overheat': [(30,5,49,49),(24,0,49,13)],
    'sensor_fault': [(23,18,34,28),(34,7,48,19),(10,32,18,41)],
    'heating_failed': [(21,17,49,45)],
    'probe_contact_fault': [(32,5,49,21),(30,32,49,46)],
    'platform_connector': [(19,0,31,15)],
    'emergency_stop': [(22,12,28,40),(17,7,33,11)],
    'firmware_update': [(17,0,33,18)],
}

def unpack(raw):
    if len(raw) != 1250: raise ValueError('Expected 50x50 packed 4bpp')
    return [v for b in raw for v in (b>>4, b&15)]

def pack(values):
    if len(values) != 2500 or set(values)-set(range(16)):
        raise ValueError('Invalid native luminance array')
    return bytes((values[i]<<4)|values[i+1] for i in range(0,2500,2))

def inside(x,y,boxes):
    return any(x0<=x<=x1 and y0<=y<=y1 for x0,y0,x1,y1 in boxes)

def author(name, original, varying):
    def occupied(x,y):
        return 0<=x<50 and 0<=y<50 and original[y*50+x]>0
    output=[]
    for i,old in enumerate(original):
        if not old:
            output.append(0);continue
        x,y=i%50,i//50
        # Fixed one-pixel bevel INSIDE the silhouette. Upper/left light,
        # lower/right shade. No glow or fractional coverage beyond the shape.
        lit=not occupied(x,y-1) or not occupied(x-1,y)
        shade=not occupied(x,y+1) or not occupied(x+1,y)
        if name.startswith('fan_'):
            r2=(x-25)**2+(y-25)**2
            if r2<14**2:
                # Four deliberate, hard-edged blade planes; not a gradient.
                tone=14 if x+y<40 else 11 if x+y<52 else 8
                if lit: tone=15
                if shade and not lit: tone=4
            else:
                tone=14 if lit else 8 if shade else 11
        elif inside(x,y,SECONDARY[name]):
            tone=14 if lit else 8 if shade else 11
        else:
            tone=15 if lit else 11 if shade else 14
        if (i in varying and not name.startswith('fan_')) or inside(x,y,ACCENTS[name]): tone=15
        output.append(tone)
    return pack(output)

def build_master():
    base=json.loads(BASE.read_text())
    if set(base['symbols'])!=set(SECONDARY) or set(ACCENTS)!=set(SECONDARY):
        raise ValueError('Every symbol needs an explicit art-direction recipe')
    master={k:base[k] for k in ('format','width','height','packing','frame_ms','foreground','background')}
    master.update(style=STYLE,palette=list(PALETTE),
        design='Native one-pixel interior bevel; semantic accents; no outside halo',
        source_silhouette_sha256=hashlib.sha256(BASE.read_bytes()).hexdigest(),symbols={})
    for name,record in base['symbols'].items():
        masks=[unpack(bytes.fromhex(f)) for f in record['frames']]
        varying={i for i in range(2500) if len({m[i] for m in masks})>1}
        frames=[author(name,mask,varying) for mask in masks]
        master['symbols'][name]={'frames':[f.hex() for f in frames],
            'sha256':[hashlib.sha256(f).hexdigest() for f in frames]}
    return master

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--check',action='store_true')
    a=ap.parse_args();text=json.dumps(build_master(),indent=2)+'\n'
    if a.check:
        if MASTER.read_text()!=text: raise SystemExit('Native icon master differs from explicit design recipes')
    else: MASTER.write_text(text)
    print('PASS native-grid design recipes: 24 symbols, 96 frames, no halo')

if __name__=='__main__':main()
