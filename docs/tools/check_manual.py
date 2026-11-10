#!/usr/bin/env python3
"""Verify documentation against actual source files. Never contacts a printer."""
import argparse
import configparser
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
CHAPTERS = ('OVERVIEW_PL.md', 'FIRST_INSTALL.md', 'USER_GUIDE.md',
            'OLED_MENU_REFERENCE.md', 'BED_MESH_AND_LEVELING.md',
            'TECHNICAL_REFERENCE.md', 'PRINT_LIMITS_AND_PLANNER.md',
            'MACRO_REFERENCE.md', 'DOCUMENTATION_CHECK.md')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/reports/DOCUMENTATION_VALIDATION.json')
    args = parser.parse_args()
    errors = []
    checks = []
    def check(condition, label):
        checks.append({'name': label, 'status': 'PASS' if condition else 'FAIL'})
        if not condition:
            errors.append(label)
    paths = [ROOT/'README_PL.md'] + [ROOT/'docs/pl'/n for n in CHAPTERS]
    for p in paths:
        check(p.is_file(), 'document:'+str(p.relative_to(ROOT)))
    links = 0
    for p in paths:
        if not p.is_file():
            continue
        text = p.read_text()
        check(len(text.split()) >= 100, 'substantive:'+str(p.relative_to(ROOT)))
        for target in re.findall(r'!?\[[^\]]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)', text):
            if target.startswith(('http://','https://','mailto:','#')):
                continue
            rel = unquote(urlsplit(target).path)
            dest = (p.parent / rel).resolve()
            links += 1
            check(dest.is_relative_to(ROOT) and dest.exists(), 'link:'+str(p.relative_to(ROOT))+':'+target)
    render = json.loads((ROOT/'docs/reports/OLED_RENDER_MANIFEST.json').read_text())
    check(render['source_commit'] == 'd6ddf9c3bee58dc2209946a0073f8a708d964073', 'render-source-commit')
    check(render['physical_printer'] is False, 'render-is-demonstration-not-hardware')
    check(len(render['screens']) == 43, '43-rendered-screen-states')
    native_pixels = 0
    for s in render['screens']:
        small = ROOT/'docs/img/oled'/(s['id']+'.png')
        large = ROOT/'docs/img/oled'/(s['id']+'@3x.png')
        check(small.exists() and large.exists(), 'render-pair:'+s['id'])
        if not (small.exists() and large.exists()):
            continue
        a,b = Image.open(small).convert('RGB'), Image.open(large).convert('RGB')
        check(a.size == (256,64) and b.size == (768,192), 'dimensions:'+s['id'])
        check(sha(small) == s['png_sha256'], 'render-sha:'+s['id'])
        expected = a.resize((768,192), Image.Resampling.NEAREST)
        check(ImageChops.difference(b,expected).getbbox() is None, 'square-3x:'+s['id'])
        native_pixels += a.width*a.height
    screenshots = json.loads((ROOT/'docs/reports/IMAGE_PROVENANCE.json').read_text())
    check(len(screenshots) == 3, 'three-user-screenshots')
    for s in screenshots:
        p = ROOT/s['file']
        check(p.exists(), 'screenshot:'+s['file'])
        if p.exists():
            check(sha(p) == s['published_sha256'], 'screenshot-sha:'+s['file'])
            check(list(Image.open(p).size) == s['dimensions'], 'screenshot-size:'+s['file'])
    names = set()
    for p in (ROOT/'host/config').glob('*.cfg'):
        names.update(re.findall(r'^\[gcode_macro ([^\]]+)\]',p.read_text(),re.M))
    documented = set(re.findall(r'\[`([A-Z0-9_]+)`\]\(../../host/config/',(ROOT/'docs/pl/MACRO_REFERENCE.md').read_text()))
    check(names == documented and len(names) == 39, 'all-39-config-macros-covered')
    catalog = json.loads((ROOT/'docs/reports/MACRO_MANIFEST.json').read_text())
    check({m['name'] for m in catalog['macros']} == names, 'macro-manifest-matches-source')
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(ROOT/'host/config/m300_classic_sensors.cfg')
    bed = cfg['adc_temperature M300_BED_STOCK_TABLE_LAB']
    check(sum(k.startswith('temperature') for k in bed) == 205, '205-original-bed-temperature-pairs')
    check(sum(k.startswith('voltage') for k in bed) == 205, '205-bed-voltage-pairs')
    hot = cfg['adc_temperature M300_HOTEND_STOCK_LINEAR_LAB']
    check(float(hot['temperature2']) == 250 and float(hot['voltage2']) == 1.25, 'original-linear-hotend-map')
    src = (ROOT/'host/klippy/extras/m300_pad_mesh.py').read_text()
    check('GRID_COUNT = 61' in src, '61x61-interpolated-grid-not-3721-measurements')
    start = (ROOT/'host/klippy/extras/m300_print_control.py').read_text()
    check("mesh=gcmd.get('MESH','AUTO')" in start and 'pmgr.load_profile(mesh)' in start, 'start-mesh-load-source')
    check("else 'NONE')" in start, 'auto-without-profile-is-none')
    guide = (ROOT/'docs/pl/BED_MESH_AND_LEVELING.md').read_text()
    check('X rośnie w prawo, Y do góry' in guide and 'nieaktywny' in guide, 'mesh-orientation-and-inactive-preview-explicit')
    planner = (ROOT/'docs/pl/PRINT_LIMITS_AND_PLANNER.md').read_text()
    check('nie deklarowanym limitem M300' in planner and '111 mm/s' in planner, 'flow-example-not-hardware-claim')
    report = {'status':'PASS_DOCUMENTATION' if not errors else 'FAIL_DOCUMENTATION',
              'reference_release':'v1.0.0-beta.17', 'documents':len(paths),
              'local_link_references':links, 'oled_screen_states':43,'oled_png_files':86,
              'native_pixels_compared':native_pixels,'user_screenshots':3,
              'config_macros':len(names),'checks_count':len(checks),'checks':checks,
              'physical_printer_tested':False,'errors':errors}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},ensure_ascii=False))
    if errors:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
