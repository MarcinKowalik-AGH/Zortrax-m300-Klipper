#!/usr/bin/env python3
"""Render production OLED temperature editors in a host-only test harness."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys

from project import ROOT, stage_host_update
from PIL import Image, ImageChops


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    package=stage_host_update(ROOT/'.ci/temperature-editor-render')
    sys.path[:0]=[str(package/'tests'),str(package)]
    from test_temperature_editor import enter
    from test_settings_information import session
    from payload.m300_oled_preview import encoded_png
    output=ROOT/'docs/img/oled-temperature'
    output.mkdir(parents=True,exist_ok=True)
    records=[]
    for name,kind,value in (('hotend_210','HOTEND',210),('bed_60','BED',60),
                            ('hotend_305','HOTEND',305),('bed_105','BED',105)):
        with session() as h:
            enter(h,kind)
            low,high=h.menu.temperature_range(kind)
            h.oled.selection=value-low+1
            h.oled._render(h.now)
            wire=h.oled._render_wire
            png=encoded_png(wire)
            native=output/(name+'.png')
            if args.check:
                assert native.read_bytes()==png, 'Native render changed: '+name
            else:
                native.write_bytes(png)
            image=Image.open(io.BytesIO(png)).convert('RGB')
            enlarged=output/(name+'@3x.png')
            zoom=image.resize((768,192),Image.Resampling.NEAREST)
            if args.check:
                existing=Image.open(enlarged).convert('RGB')
                assert existing.size==zoom.size and ImageChops.difference(existing,zoom).getbbox() is None, name
            else:
                zoom.save(enlarged)
            records.append(dict(name=name,kind=kind,value_c=value,range_c=[low,high],
                native_file=str(native.relative_to(ROOT)),
                zoom_file=str(enlarged.relative_to(ROOT)),
                wire_sha256=hashlib.sha256(wire).hexdigest(),
                png_sha256=hashlib.sha256(png).hexdigest(),
                zoom_sha256=hashlib.sha256(enlarged.read_bytes()).hexdigest(),
                sprite=h.ui.last_sprite,dimensions=[256,64],zoom=3))
    report=dict(status='PASS_PRODUCTION_TEMPERATURE_EDITOR_RENDER',
        release='v1.0.0-rc.4',source='M300OLED._render + original indexed PNG encoder',
        physical_printer_tested=False,heater_targets_changed=False,screens=records)
    path=ROOT/'docs/reports/TEMPERATURE_EDITORS_RC4.json'
    if args.check:
        assert json.loads(path.read_text())==report, 'Render provenance mismatch'
    else:
        path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
