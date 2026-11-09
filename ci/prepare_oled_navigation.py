"""One-time branch preparation; removed with its workflow before review/merge."""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '8cd20c5b6c787ce126ea0f280e76367a505173f2'

def edit(path, transform):
    target = ROOT / path
    old = target.read_text()
    expected = subprocess.check_output(['git', 'show', BASE + ':' + path], text=True)
    assert old == expected, 'Refusing to edit concurrent changes: ' + path
    new = transform(old)
    assert new != old, 'Expected a change: ' + path
    target.write_text(new)

def exact(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)

subprocess.run(['git', 'apply', '--check', 'ci/prepare-oled-navigation.patch'], check=True)
assert subprocess.check_output(['git', 'hash-object', 'host/klippy/extras/m300_oled.py'], text=True).strip() == '3264881e6ed531491ef085ba870d6c5318d5c759'
subprocess.run(['git', 'apply', 'ci/prepare-oled-navigation.patch'], check=True)

def metadata(text):
    data = json.loads(text)
    assert data['distribution_version'] == 'v1.0.0-beta.15'
    data.update(distribution_version='v1.0.0-beta.16', supersedes_version='v1.0.0-beta.15',
                self_contained_host_tests=741, oled_preview_revision='NAV-EVENT-1')
    return json.dumps(data, indent=2) + '\n'
edit('PORT.json', metadata)

def build(text):
    text = exact(text, 'git apply "$root/frontend/fluidd/m300-leveling.patch"\n',
        'git apply "$root/frontend/fluidd/m300-leveling.patch"\n'
        '# Versioned navigation-only overlay; preserve the existing graphics and animation cadence.\n'
        'cp "$root/frontend/fluidd/navigation/M300OledPreview.vue" src/components/widgets/thermals/\n'
        'cp "$root/frontend/fluidd/navigation/"*.ts src/util/\n')
    text = exact(text, 'src/util/m300-oled-preview.spec.ts\n',
        'src/util/m300-oled-preview.spec.ts src/util/m300-oled-navigation.spec.ts src/util/m300-oled-navigation-component.spec.ts\n')
    text = exact(text, 'src/util/m300-oled-preview{,.spec}.ts ',
        'src/util/m300-oled-preview{,.spec}.ts src/util/m300-oled-navigation{,.spec,-component.spec}.ts ')
    text = exact(text, 'mkdir -p "$root/dist/fluidd"',
        'cp -R "$root/frontend/fluidd/navigation" navigation-source\nmkdir -p "$root/dist/fluidd"')
    return exact(text, 'fluidd-m300 LICENSE m300-leveling.patch FLUIDD_M300.md\n',
        'fluidd-m300 LICENSE m300-leveling.patch FLUIDD_M300.md navigation-source\n')
edit('ci/build_fluidd.sh', build)

def workflow(text):
    text = exact(text, '  workflow_dispatch:\n', '  pull_request:\n    branches: [main]\n  workflow_dispatch:\n')
    return exact(text, '      - name: Check OLED RLE on emulated Cortex-M instructions\n',
        '      - name: Verify event-driven OLED navigation on the pinned Klipper reactor\n'
        '        run: python ci/check_oled_navigation.py --klipper .ci/pristine --output .ci/reports/OLED_NAVIGATION.json\n\n'
        '      - name: Check OLED RLE on emulated Cortex-M instructions\n')
edit('.github/workflows/build-m300.yml', workflow)

note_en = ('**Beta.16: immediate menu navigation in the Fluidd OLED preview.** '
    'Selection changes complete a dedicated read-only event wait on the existing '
    'authorized WebSocket, without the periodic object-status timer or Fluidd cache. '
    'Animations, 344x86 layout, physical OLED transport and all beta.15 print fixes remain unchanged.\n'
    '[Beta.16 release notes](docs/en/RELEASE_v1.0.0-beta.16.md).\n\n'
    '**Correction to the beta.13 description below:** `objects/query` did not bypass '
    'the pinned Klipper 250 ms refresh. Beta.16 uses a separate event endpoint.\n\n')
note_pl = ('**Beta.16: natychmiastowa aktualizacja zaznaczenia menu w podglądzie OLED Fluidd.** '
    'Osobny kanał zdarzeniowy korzysta z istniejącego autoryzowanego WebSocket, '
    'bez czekania na cykl statusów. Animacje, rozmiar 344x86, transport fizycznego OLED '
    'oraz poprawki PAUSE/CANCEL i cztery linie startowe z beta.15 pozostają bez zmian.\n'
    '[Opis beta.16](docs/pl/RELEASE_v1.0.0-beta.16.md).\n\n'
    '**Sprostowanie opisu beta.13 poniżej:** `objects/query` nadal korzystało z cyklu '
    '250 ms Klippera. Beta.16 omija go osobnym punktem API zdarzeń.\n\n')
def readme(text, polish=False):
    lines = text.splitlines(keepends=True)
    for index in range(min(5, len(lines))):
        lines[index] = lines[index].replace('v1.0.0-beta.14', 'v1.0.0-beta.16')
    text = ''.join(lines)
    marker = '**Beta.14:' if polish else '**Beta.14 fixed-height OLED preview:**'
    assert marker in text
    return text.replace(marker, (note_pl if polish else note_en) + marker, 1)
edit('README.md', readme)
edit('README_PL.md', lambda text: readme(text, True))
for path in ('docs/en/FIRST_INSTALL.md', 'docs/pl/FIRST_INSTALL.md', 'docs/en/INSTALL.md'):
    text = (ROOT / path).read_text()
    if 'v1.0.0-beta.14' in text:
        edit(path, lambda value: value.replace('v1.0.0-beta.14', 'v1.0.0-beta.16'))

# All temporary preparation machinery is excluded from the final change.
for path in ('ci/prepare-oled-navigation.patch', 'ci/prepare_oled_navigation.py',
             '.github/workflows/prepare-oled-navigation.yml'):
    (ROOT / path).unlink()
