#!/usr/bin/env python3
"""Render approved menu animation without hardware, heating or bitmap edits."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
from PIL import Image
from project import ROOT, stage_host_update


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    args=p.parse_args()
    package=stage_host_update(ROOT/'.ci/menu-animation-render')
    sys.path[:0]=[str(package/'tests'),str(package)]
    from test_settings_information import session
    from test_temperature_editor import enter
    from payload.m300_oled_preview import encoded_png
    from test_menu_animation import APPROVED
    out=ROOT/'docs/img/oled-animation-rc6';out.mkdir(parents=True,exist_ok=True)
    records=[]
    for name,kind in (('hotend_menu','menu'),('hotend_editor','HOTEND'),
                      ('bed_editor','BED'),('led_brightness','brightness')):
        with session() as h:
            if kind in ('HOTEND','BED'):
                enter(h,kind)
                h.oled.selection=(210 if kind=='HOTEND' else 60)-h.menu.temperature_range(kind)[0]+1
            elif kind=='menu':
                h.menu.page='klipper'
                h.oled.selection=next(i for i,(_,a) in enumerate(h.menu.rows(h.now)[1])
                    if a==('temperatures','HOTEND','klipper'))
            else:
                h.menu.page='setting_led_brightness';h.oled.selection=8
            frames=[];wires=[]
            for i in range(4):
                h.oled._render(i*.5)
                wire=h.oled._render_wire;wires.append(wire)
                im=Image.open(io.BytesIO(encoded_png(wire))).convert('P')
                frames.append(im.resize((768,192),Image.Resampling.NEAREST))
            assert len(set(wires))>1,name
            assert (h.hotend.target,h.bed.target)==(0.,0.)
            path=out/(name+'.gif')
            if args.check:
                with Image.open(path) as im:
                    assert im.n_frames==4 and im.info['loop']==0,name
                    for i,frame in enumerate(frames):
                        im.seek(i)
                        assert im.info['duration']==500,name
                        assert im.convert('RGB').tobytes()==frame.convert('RGB').tobytes(),(name,i)
            else:
                frames[0].save(path,save_all=True,append_images=frames[1:],
                    duration=500,loop=0,optimize=False,disposal=2)
            records.append(dict(name=name,file=str(path.relative_to(ROOT)),
                frame_ms=500,frames=4,unique_frames=len(set(wires)),
                wire_sha256=[hashlib.sha256(w).hexdigest() for w in wires],
                gif_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),sprite=h.ui.last_sprite))
    report=dict(status='PASS_APPROVED_MENU_ANIMATION',release='v1.0.0-rc.6',
        source='M300OLED._render and original indexed PNG encoder',
        approved_artwork_release='v1.0.0-rc.3',approved_sha256=APPROVED,
        physical_printer_tested=False,heater_targets_changed=False,screens=records)
    path=ROOT/'docs/reports/MENU_ANIMATION_RC6.json'
    if args.check:assert json.loads(path.read_text())==report
    else:path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
