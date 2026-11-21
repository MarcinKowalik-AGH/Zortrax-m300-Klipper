#!/usr/bin/env python3
# Marcin Kowalik <mkowalik@agh.edu.pl>
# check_manual.py - Sprawdza odnośniki, makra, ilustracje i zgodność dokumentacji z bieżącą wersją.
"""Verify current instructions and historical illustrations. Never contacts a printer."""
import argparse
import configparser
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from collections import Counter
from urllib.parse import unquote, urlsplit
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / 'ci'))
from historical_source import source_sha

CURRENT_RELEASE = 'v1.0.0-rc.34'
CURRENT_MCU = '1.0.8'
VISUAL_BASELINE = 'v1.0.0-beta.20'
CHAPTERS = ('OVERVIEW_PL.md', 'FIRST_INSTALL.md', 'INSTALL.md', 'USER_GUIDE.md',
            'OLED_MENU_REFERENCE.md', 'BED_MESH_AND_LEVELING.md',
            'TECHNICAL_REFERENCE.md', 'PRINT_LIMITS_AND_PLANNER.md',
            'MACRO_REFERENCE.md', 'DOCUMENTATION_CHECK.md',
            'OLED_FUNCTIONS.md', 'UPDATE_2026-11-10.md', 'PRINT_CONTROL.md',
            'INSTALLATION_AND_CI.md', 'ACCEPTANCE_REGISTER.md', 'RC1_UI.md', 'CODE_REVIEW_RC1.md', 'MCU_FIRMWARE_1.0.1.md', 'MCU_FIRMWARE_1.0.2.md', f'MCU_FIRMWARE_{CURRENT_MCU}.md')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def heading_ids(text):
    ids = set(re.findall(r'<a\s+(?:id|name)="([^"]+)"', text))
    counts = Counter()
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*$', text, re.M):
        heading = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', heading)
        slug = ''.join(c for c in heading.strip().lower().replace(' ', '-')
                       if c in '-_' or unicodedata.category(c)[0] in 'LNM')
        ids.add(slug if not counts[slug] else f'{slug}-{counts[slug]}')
        counts[slug] += 1
    return ids


def check_manual_links(check):
    paths = sorted((ROOT/'docs').rglob('*.md')) + list(ROOT.glob('*.md'))
    # Fenced examples contain G-code and shell syntax as well as prose.
    pages = {p: re.sub(r'^```[^\n]*\n.*?^```[^\n]*', '', p.read_text(),
                       flags=re.M | re.S) for p in paths}
    headings = {p: heading_ids(body) for p, body in pages.items()}
    links = 0
    for page, body in pages.items():
        for target in re.findall(r'\]\(([^\s)]+)', body):
            url = urlsplit(target)
            if url.scheme or url.netloc:
                continue
            dest = (page.parent / unquote(url.path)).resolve() if url.path else page
            label = str(page.relative_to(ROOT)) + ':' + target
            check(dest.is_relative_to(ROOT) and dest.exists(), 'link:' + label)
            if url.fragment and dest in headings:
                check(unquote(url.fragment) in headings[dest], 'anchor:' + label)
            links += 1
    return len(pages), links


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'.ci/reports/DOCUMENTATION_RC1_VALIDATION.json')
    args = parser.parse_args()
    errors = []
    checks = []
    def check(condition, label):
        checks.append({'name': label, 'status': 'PASS' if condition else 'FAIL'})
        if not condition:
            errors.append(label)
    paths = [ROOT/'README_PL.md', ROOT/'README.md'] + [ROOT/'docs/pl'/n for n in CHAPTERS]
    paths += [ROOT/'docs/en'/n for n in ('USER_GUIDE.md','FIRST_INSTALL.md','INSTALL.md','FRONTEND_BETA20.md','FLUIDD_M300.md','FEATURES.md','LEVELING.md','SETTINGS_INFORMATION.md','UI_SYMBOLS.md','MCU_FIRMWARE_1.0.1.md', 'MCU_FIRMWARE_1.0.2.md', f'MCU_FIRMWARE_{CURRENT_MCU}.md')]
    paths += [ROOT/'docs'/lang/('RELEASE_'+CURRENT_RELEASE+'.md') for lang in ('pl','en')]
    for p in paths:
        check(p.is_file(), 'document:'+str(p.relative_to(ROOT)))
    for p in paths:
        if p.is_file():
            check(len(p.read_text().split()) >= 100, 'substantive:'+str(p.relative_to(ROOT)))
    page_count, links = check_manual_links(check)
    render = json.loads((ROOT/'docs/reports/OLED_RENDER_MANIFEST.json').read_text())
    check(render['source_commit'] == '4828a9da9d5fd8b0b93eb2ac267732ee7e49d506', 'render-source-commit')
    check(render['physical_printer'] is False, 'render-is-demonstration-not-hardware')
    check(len(render['screens']) == 65, '65-rendered-screen-states')
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
    cover = 'docs/img/m300-orcaslicer-fluidd-printing.png'
    check(sum(item['file'] == cover for item in screenshots) == 1, 'cover-provenance')
    for s in screenshots:
        p = ROOT/s['file']
        check(p.exists(), 'screenshot:'+s['file'])
        if p.exists():
            check(sha(p) == s['published_sha256'] == s['original_sha256'], 'screenshot-sha:'+s['file'])
            check(list(Image.open(p).size) == s['dimensions'], 'screenshot-size:'+s['file'])
    names = set()
    for p in (ROOT/'host/config').glob('*.cfg'):
        names.update(re.findall(r'^\[gcode_macro ([^\]]+)\]',p.read_text(),re.M))
    documented = set(re.findall(r'\[`([A-Z0-9_]+)`\]\(../../host/config/',(ROOT/'docs/pl/MACRO_REFERENCE.md').read_text()))
    check(names == documented and len(names) == 44, 'all-44-config-macros-covered')
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
    check('select a saved bed mesh with BED_MESH_PROFILE LOAD=' in start, 'auto-requires-saved-profile')
    guide = (ROOT/'docs/pl/BED_MESH_AND_LEVELING.md').read_text()
    check('X rośnie w prawo, Y do góry' in guide and 'nieaktywny' in guide, 'mesh-orientation-and-inactive-preview-explicit')
    planner = (ROOT/'docs/pl/PRINT_LIMITS_AND_PLANNER.md').read_text()
    check('nie deklarowanym limitem M300' in planner and '111 mm/s' in planner, 'flow-example-not-hardware-claim')
    # Historical beta.20 illustrations remain exact, explicitly versioned evidence.
    catalog = json.loads((ROOT/'docs/reports/OLED_FUNCTION_CATALOG.json').read_text())
    entries = catalog['entries']
    screen_ids = {item['id'] for item in render['screens']}
    check(len(entries) == len(screen_ids) == 65, '65-illustrated-functions')
    check({e['id'] for e in entries} == screen_ids, 'function-to-render-coverage')
    illustrated = (ROOT/'docs/pl/OLED_FUNCTIONS.md').read_text()
    for e in entries:
        check(all(isinstance(e.get(k), str) and len(e[k]) > 3 for k in
                  ('title','path','effect','operator','fluidd','icon','source')), 'function-fields:'+e['id'])
        check(('id="'+e['id']+'"') in illustrated and (e['id']+'@3x.png') in illustrated,
              'function-illustration:'+e['id'])
        check((ROOT/'host/klippy/extras'/e['source']).is_file(), 'function-source:'+e['id'])
    demo = json.loads((ROOT/'docs/reports/FLUIDD_OLED_DEMO.json').read_text())
    check(demo['physical_printer'] is False, 'Fluidd-images-are-demonstrations')
    check(len(demo['screens']) == 3, 'three-Fluidd-zoom-demonstrations')
    for image in demo['screens']:
        p = ROOT/image['file']
        check(p.is_file() and sha(p) == image['sha256'], 'Fluidd-demo:'+image['file'])
    source_baseline = json.loads((ROOT/'docs/reports/DOC_SOURCE_BASELINE.json').read_text())
    # Historical image digests stay exact. The reviewed RC7 and RC14 host
    # changes have separate contracts from the RC6 illustration baseline.
    updated_runtime_sources = {
        'host/klippy/extras/m300_print_control.py',
        'host/klippy/extras/m300_settings.py',
        'host/klippy/extras/m300_native_motion.py',
    }
    current_plate_sources = {
        'frontend/fluidd/m300-tune.patch': '914c94dded9c006519259efaed333b7a22d77176392372bfe2bf38bf60800304',
        'host/klippy/extras/m300_oem_graphics.py': 'a362428135beaa70d7366902fba0da52c9d631531b26336b1229868c4b446028',
        # RC33 names the OLED reheat action before material flow verification.
        'host/klippy/extras/m300_print_ui.py': '5082c05b90ba40183784097bcc87dd381bcd9831cba6df505f3d30ded32b8e87',
        'host/config/m300_classic_services.cfg': '541a4b8434cfa784ab07172d630f93ad18b57d147b6adf75c9ca4dabbe867505',
        'host/klippy/extras/m300_menu.py': 'f8b550fc3064404efba210b2fdb86a3a3bdae9eaa40fae3d2a41ac980540e743',
        'host/config/m300_classic_base.cfg': 'bcc673a7be643a9f637fd22ffc02f912063b3af26509d7cc861dce650cdc9e64',
        'host/config/m300_operations.cfg': 'acf1f2de2d43479f895af856f8f32b8cdab5b02bfa082a27c5b487c19c198274',
        'host/config/m300_display.cfg': 'e29c157538dec062c7b9e3f4f37c93613a5b54d91bc231c9bee15d1b84ffd284',
        'host/klippy/extras/m300_pad_mesh.py': 'c8a21696a4e17fe9797074d6e0e0cc732167ecfe225aeb23c4487ab838de1f7b',
        'host/klippy/extras/m300_activity_graphics.py': '51b7f4992070ccd5363ce7a74237c4a6a320c365ce7dadd059ba20bef3429037',
        'host/klippy/extras/m300_settings_ui.py': 'cad2ac3c9fea594a5e8701f35936681857ec0f6e341697768940cba6a8d3dafd',
        'host/klippy/extras/m300_klipper_status.py': '6bde411f82ee2f1a86e53b40b967000d715bc4f10ee656521493a7a2e8ae45c1',
    }
    for path, expected in source_baseline['files'].items():
        expected = current_plate_sources.get(path, expected)
        if path in updated_runtime_sources:
            continue
        p = ROOT/path
        check(p.is_file() and source_sha(p) == expected, 'source-baseline:'+path)
    port = json.loads((ROOT/'PORT.json').read_text())
    check(port['distribution_version'] == CURRENT_RELEASE, 'current-release')
    check(port['mcu_release'] == CURRENT_MCU, 'current-MCU-release')
    check(port['oled_zoom_revision'] == 'OLED-ZOOM-2', 'current-zoom-revision')
    check(port['tune_frontend_revision'] == 'TUNE-PREPARE-1', 'current-Tune-revision')
    for lang in ('pl','en'):
        install = (ROOT/'docs'/lang/'FIRST_INSTALL.md').read_text()
        check('releases/download/'+CURRENT_RELEASE+'/' in install, 'first-install-release:'+lang)
        supplement = (ROOT/'docs'/lang/('RELEASE_'+CURRENT_RELEASE+'.md')).read_text()
        check(port['mcu_release'] in supplement and 'M300_SD.zip' in supplement,
              'current-MCU-update-instructions:'+lang)
        check('beta.20' in supplement, 'historical-illustration-baseline-disclosed:'+lang)
    for name in ('README.md','README_PL.md'):
        text = (ROOT/name).read_text()
        top = text.split('\n\n', 2)[1]
        check(bool(re.fullmatch(r'\[!\[[^\]]+\]\(' + re.escape(cover) +
                                r'\)\]\(' + re.escape(cover) + r'\?raw=true\)', top)),
              'clickable-cover-under-title:'+name)
        check('releases/tag/'+CURRENT_RELEASE in text, 'README-current-release:'+name)
        check('OLED_FUNCTIONS.md' in text, 'README-illustrated-guide:'+name)
    update = (ROOT/'docs/pl/UPDATE_2026-11-10.md').read_text()
    check(all(t in update for t in ('#16A1FE','#0A436C','#0C588E','#020610','×1','×2','×3','HIDE','TUNE-PREPARE-1')), 'documented-current-UI')
    check('nad heatmapą' in guide and 'M300_HOME_ALL' in guide, 'current-Tune-order-and-home')
    check('nie deklaruje' in (ROOT/'docs/pl/USER_GUIDE.md').read_text(), 'no-unimplemented-CI-auto-repair-claim')
    report = {'status':'PASS_DOCUMENTATION' if not errors else 'FAIL_DOCUMENTATION',
              'reference_release':CURRENT_RELEASE, 'visual_baseline_release':VISUAL_BASELINE,
              'documents':page_count, 'local_link_references':links,
              'oled_screen_states':65,'oled_png_files':130,
              'native_pixels_compared':native_pixels,'user_screenshots':len(screenshots),
              'config_macros':len(names),'illustrated_functions':len(entries),
              'browser_demo_images':len(demo['screens']),'checks_count':len(checks),'checks':checks,
              'physical_printer_tested':False,'errors':errors}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},ensure_ascii=False))
    if errors:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
