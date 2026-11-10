#!/usr/bin/env python3
"""One-time source preparation, removed by its isolated branch workflow."""
from pathlib import Path
import ast
import hashlib
import json

root = Path.cwd()
paths = {
    'host/klippy/extras/m300_oem_graphics.py': '4927a3b041932431347cf0548e374c12ba34e246',
    'host/klippy/extras/m300_menu_ui.py': '4a0de2f1b98b1bd39c018137df74f38c0240c7e3',
}
old_hashes = {}
for name, sha in paths.items():
    raw = (root / name).read_bytes()
    assert hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest() == sha, name
    old_hashes[Path(name).name] = hashlib.sha256(raw).hexdigest()

def replace_once(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after, 1)

oem = root / 'host/klippy/extras/m300_oem_graphics.py'
s = replace_once(oem.read_text(), 'from pathlib import Path\n', 'from pathlib import Path\nfrom functools import lru_cache\n')
s = replace_once(s, 'class OEMGraphics:\n    def __init__(self, path=None):', '''SHARP_ICON_REVISION = 'SHARP-HOST-1'
# Threshold packed nibbles independently: 0..7 -> 0, 8..15 -> 15.
# This removes the added <=6 edge tones without changing a bright core.
_SHARP_TABLE = bytes((240 if b >> 4 >= 8 else 0) |
                     (15 if b & 15 >= 8 else 0) for b in range(256))


@lru_cache(maxsize=64)
def sharp_sprite(sprite):
    """Cached presentation copy; never rewrite original OEM evidence/assets."""
    width, height, raw = sprite
    if (width, height) != (50, 50) or type(raw) is not bytes or len(raw) != 1250:
        raise ValueError('Sharp OLED icons require a native 50x50 packed frame')
    return width, height, raw.translate(_SHARP_TABLE)


class OEMGraphics:
    def __init__(self, path=None, *, sharp=False):
        if type(sharp) is not bool:
            raise ValueError('Sharp icon mode must be boolean')
        self.sharp = sharp''')
s = replace_once(s, '    def get(self, addr, now=0.):\n        addr=str(addr).lower()', '''    def get(self, addr, now=0.):
        addr = str(addr).lower()
        original = self._get_source(addr, now)
        # Functional axis dimming and the three-tone Klipper wordmark are
        # independent designs, not soft edge shading; preserve them exactly.
        if original is not None and self.sharp and (
                addr.startswith(PREFIX) or addr in self.frames):
            return sharp_sprite(original)
        return original

    def _get_source(self, addr, now=0.):
        addr=str(addr).lower()''')
ast.parse(s)
oem.write_text(s)
ui = root / 'host/klippy/extras/m300_menu_ui.py'
s = replace_once(ui.read_text(), '        self.oem_sprites = OEMGraphics() if self.oem_graphics_enabled else None', '''        self.sharp_icons = config.getboolean('sharp_icons', True)
        self.oem_sprites = (OEMGraphics(sharp=self.sharp_icons)
                            if self.oem_graphics_enabled else None)''')
s = replace_once(s, "                'oem_graphics_enabled':self.oem_graphics_enabled,", """                'oem_graphics_enabled':self.oem_graphics_enabled,
                'icon_style':('SHARP-HOST-1' if getattr(self.oem_sprites, 'sharp', False)
                              else 'SOURCE-TONES'),""")
ast.parse(s)
ui.write_text(s)
# Baselines authorize ONLY the exact previous modules; unknown edits still fail.
p = root / 'host/update_template/SUPPORTED_BASELINES.json'
d = json.loads(p.read_text())
for name, sha in old_hashes.items():
    if sha not in d.setdefault(name, []):
        d[name].append(sha)
p.write_text(json.dumps(d, indent=2) + '\n')
p = root / 'ci/run_checks.py'
s = replace_once(p.read_text(), "    run('toned_activity_transport', [sys.executable, ROOT/'ci/check_toned_activity.py'])", "    run('toned_activity_transport', [sys.executable, ROOT/'ci/check_toned_activity.py'])\n    run('sharp_host_icons', [sys.executable, ROOT/'ci/check_sharp_icons.py'])")
p.write_text(s)
p = root / 'PORT.json'
d = json.loads(p.read_text())
assert d['distribution_version'] == 'v1.0.0-beta.21'
assert d['mcu_release'] == '0.13.14.19-TONED-OLED-UART8'
d['distribution_version'] = 'v1.0.0-beta.22'
d['supersedes_version'] = 'v1.0.0-beta.21'
d['oled_icon_style'] = 'SHARP-HOST-1'
p.write_text(json.dumps(d, indent=2) + '\n')

pl = '''# M300 Classic beta.22 — ostre ikony menu na OLED i we Fluidd

Wersja zastępuje beta.21. Domyślny wygląd menu: **SHARP-HOST-1**.
To odwracalna zmiana prezentacji po stronie Orange Pi; aplikacja MCU pozostaje
**0.13.14.19-TONED-OLED-UART8**. Nie trzeba ponownie jej wgrywać.

## Co się zmienia

- Wszystkie **24 dodatkowe ikony aktywności (96 klatek)** wracają na ekranie
  dokładnie do ostrych bitmap sprzed cieniowania, bez poświaty i półtonów.
- **37 zestawów OEM (61 klatek)** wyświetla się w wariancie dwupoziomowym:
  wartości 0–7 stają się 0, a 8–15 stają się 15. To progowanie, nie filtr rozmycia.
- Pliki odzyskane z firmware oraz ich sumy kontrolne pozostają nienaruszone.
  Ostry obraz jest osobną, buforowaną reprezentacją; kanoniczne źródła dalej
  przechodzą oryginalne testy zgodności z firmware.
- Home/Move zachowują dotychczasowe jasności migających osi, a logo Klippera
  pozostaje trzytonowe. Są to oznaczenia funkcjonalne, nie dodana poświata.

Tekst, grubość fontu, rytm animacji, wybór ikon, szybki kanał nawigacji,
przyciski ×1/×2/×3, Tune, mesh, ruch, grzanie i procedury druku nie zmieniają się.
Przekształcenie dotyczy tylko bitmapy 50×50. Cache ma limit 64 klatek;
ponowny odczyt tej samej klatki nie przelicza pikseli od nowa.

## Instalacja przez Git — port Fluidd 4480

Przy bezczynnej drukarce w stanie **Ready**, na Orange Pi jako użytkownik klipper:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Odśwież Fluidd przez **Cmd+Shift+R**. W konsoli uruchom `ZORTRAX_UI_STATUS`;
wartość `icon_style` powinna wynosić `SHARP-HOST-1`. W `BUILD_PROVENANCE.json`
paczki ma być beta.22. Aktualizacja używa właściwych sum pakietu i rozpoznaje
poprzednie moduły; **nie nadpisuj ręcznie plików JSON starszym ZIP-em testowym**.
Takie nadpisanie unieważnia manifest i instalator powinien je odrzucić.

Nowy wygląd dotyczy fizycznego OLED przy działającym połączeniu z Klipperem
oraz podglądu Fluidd. **Samodzielne ekrany oczekiwania i błędów MCU nie są
zmienione w tym wydaniu** — zachowują wygląd R14.19. Host nie flashuje MCU.
Nie ma potrzeby wymiany bootloadera, kasowania konfiguracji ani nowego mesh.

## Porównanie z poprzednią wersją bez ponownego wgrywania

W istniejącej sekcji `[m300_menu_ui]` konfiguracji można dodać:

```ini
sharp_icons: False
```

Po zapisaniu i `RESTART` (tylko przy bezczynnej drukarce) wracają źródłowe
odcienie beta.21. `sharp_icons: True` lub brak tego wpisu włącza ostry wariant.
Nie twórz drugiej sekcji o tej samej nazwie. Zmiana jest wyłącznie wizualna.

## Walidacja i granice

Kontrola obejmuje wszystkie 157 klatek, oryginalne hashe OEM, dokładne
odtworzenie 96 klatek beta.20, rozmiar i czas animacji, bezstratny transport,
limit cache, integrację z rzeczywistym rendererem hosta w harnessie testowym,
741 regresji hosta, migrację instalatora i pełną kompilację CI.
Testy programowe nie są oceną wyglądu fizycznego wyświetlacza. Jasne kontury
mogą być bardziej schodkowe na ukośnych liniach — to zamierzony skutek
rezygnacji z półtonów. Oceniaj przede wszystkim przy ×1 na drukarce.

Instrukcja 65 ekranów pozostaje oznaczonym punktem odniesienia beta.20;
działania funkcji nie zmieniają się. Ten dodatek opisuje nowy wariant grafiki.
'''
en = '''# M300 Classic beta.22 — sharp host-rendered menu icons

Supersedes beta.21. Default live-menu style: **SHARP-HOST-1**.
This is a reversible Orange Pi presentation update, not an MCU firmware change.

All 24 activity symbols / 96 frames display exactly the original binary
pre-toning artwork. All 37 OEM groups / 61 frames display at 0/15 using the
threshold 8. Source firmware assets and their hashes are preserved byte-for-byte.
A bounded 64-frame cache stores only the derived visual representation. Original
source-mode APIs remain available for the firmware-fidelity tests and handbook.
Functional Home/Move axis dimming and the three-tone Klipper logo stay unchanged.
No text, navigation cadence, transport, frontend, mesh or printer procedure changes.

## Install (Fluidd port 4480)

With the printer idle and Ready, as the Klipper user on Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Hard-refresh Fluidd. `ZORTRAX_UI_STATUS` reports `icon_style: SHARP-HOST-1`.
Do not manually overwrite packaged JSON files: that invalidates integrity checks.
The updater recognizes only the exact previous module hashes and rejects unknown
local edits. No reset or repeated probing is needed.

**No MCU flash is necessary.** Normal host-rendered menus on the physical OLED
and Fluidd use the sharp frames. Autonomous waiting/fault screens on MCU R14.19
retain beta.21 tones; this release does not pretend to update those screens.

For an A/B comparison, set `sharp_icons: False` in the existing `[m300_menu_ui]`
section and restart Klipper while idle. True (the default) restores sharp output.
Do not create a duplicate section or issue RESTART during a print.

The matching full CI must validate all 157 frames, exact old activity pixels,
canonical OEM evidence, lossless transport, real host-renderer integration,
previous-install compatibility, 741 host regressions, native Klippy, ARM, Fluidd
and package checksums before publication. These are software tests, not physical
OLED visual acceptance. Binary diagonal contours may look more stepped; view at
native scale. The 65-screen beta.20 handbook remains a versioned reference.
'''
(root / 'docs/pl/RELEASE_v1.0.0-beta.22.md').write_text(pl)
(root / 'docs/en/RELEASE_v1.0.0-beta.22.md').write_text(en)
for name, note in [
    ('README.md', '> **Beta.22 — sharp host menu icons:** 24 activity designs restored to crisp binary pixels and 37 OEM groups thresholded for a physical-OLED visual test. Source evidence remains intact; no MCU flash. [Instructions, port 4480 and optional comparison](docs/en/RELEASE_v1.0.0-beta.22.md).'),
    ('README_PL.md', '> **Beta.22 — ostre ikony OLED:** przywrócone 24 dodatkowe ikony oraz wyostrzone 37 zestawów OEM, bez nadpisywania oryginalnych zasobów. [Aktualizacja na porcie 4480 i porównanie wariantów](docs/pl/RELEASE_v1.0.0-beta.22.md). Nie trzeba wgrywać MCU.'),
]:
    p = root / name
    text = p.read_text()
    title, rest = text.split('\n', 1)
    title = title.replace('v1.0.0-beta.21', 'v1.0.0-beta.22')
    p.write_text(title + '\n\n' + note + '\n' + rest)
for p in (oem, ui, root / 'ci/check_sharp_icons.py', root / 'ci/run_checks.py'):
    ast.parse(p.read_text())
print(json.dumps({'status': 'PREPARED_BETA22_SHARP_HOST', 'previous_hashes': old_hashes}))
