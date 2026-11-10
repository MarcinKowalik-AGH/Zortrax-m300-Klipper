#!/usr/bin/env python3
"""Sharp host icon acceptance checks. Never connects to a printer."""
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / 'host/klippy/extras'
sys.path.insert(0, str(ROOT / 'host'))
from klippy.extras.m300_oem_graphics import OEMGraphics, sharp_sprite
from klippy.extras.m300_oled_transport import fast_blocks
from klippy.extras.m300_menu_ui import M300MenuUI


def threshold(raw):
    values = [15 if value >= 8 else 0 for byte in raw
              for value in (byte // 16, byte % 16)]
    return bytes(values[i] * 16 + values[i + 1] for i in range(0, len(values), 2))


def packet_check(raw):
    result = bytearray()
    payload = 0
    for _, (dc, encoding, count, data), _ in fast_blocks(raw):
        assert dc == 1 and len(data) <= 32 and count <= 256
        payload += len(data)
        before = len(result)
        if not encoding:
            result.extend(data)
        else:
            at = 0
            while at < len(data):
                code = data[at]
                at += 1
                n = (code & 127) + 1
                if code & 128:
                    result.extend(bytes([data[at]]) * n)
                    at += 1
                else:
                    result.extend(data[at:at + n])
                    at += n
            assert at == len(data)
        assert len(result) - before == count
    assert bytes(result) == raw
    return payload


def main():
    expected_sources = {
        'm300_oem_sprites_131.json': '006058afcac0b9b888762a336935675bcac625b6f888e1fb10fca2872187c387',
        'm300_activity_sprites.json': 'e30b73046443492032c197ad8def628b36bb64a42d797d2c3262eddab05f18c0',
    }
    for name, sha in expected_sources.items():
        assert hashlib.sha256((HOST / name).read_bytes()).hexdigest() == sha, name
    source = OEMGraphics()
    sharp = OEMGraphics(sharp=True)
    assert source.sharp is False and sharp.sharp is True
    assert sharp.get('missing') is None
    for bad in (1, 'true', None):
        try:
            OEMGraphics(sharp=bad)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid style accepted')
    for sprite in ((49, 50, bytes(1250)), (50, 50, b''), (50, 50, bytearray(1250))):
        try:
            sharp_sprite(sprite)
        except (ValueError, TypeError):
            # lru_cache rejects unhashable mutable data before the body runs.
            pass
        else:
            raise AssertionError('Invalid frame accepted')

    rows = []
    for addr, desc in source.frames.items():
        for index, frame in enumerate(desc['frames']):
            clock = index * desc['period_ticks'] / 1000. + .00001
            raw = zlib.decompress(base64.b64decode(frame['zlib_b64'], validate=True))
            original = source.get(addr, clock)
            binary = sharp.get(addr, clock)
            assert original == (50, 50, raw)
            assert hashlib.sha256(raw).hexdigest() == frame['sha256']
            assert binary == (50, 50, threshold(raw))
            assert set(binary[2]) <= {0, 15, 240, 255}
            assert sharp.get(addr, clock) is binary
            rows.append(dict(group='OEM', symbol=addr, frame=index,
                             payload_before=packet_check(raw),
                             payload_after=packet_check(binary[2])))
    assert len(rows) == 61

    activity = json.loads((HOST / 'm300_activity_sprites.json').read_text())
    before = json.loads((ROOT / 'docs/assets/ui-symbols/native_frames_beta20.json').read_text())
    assert len(activity['symbols']) == 24
    for name, desc in activity['symbols'].items():
        assert (desc['width'], desc['height'], desc['frame_ms']) == (50, 50, 500)
        assert len(desc['frames']) == 4
        for index, frame in enumerate(desc['frames']):
            clock = index * .5
            raw = zlib.decompress(base64.b64decode(frame['zlib_b64'], validate=True))
            binary = sharp.get('activity:' + name, clock)
            assert source.get('activity:' + name, clock) == (50, 50, raw)
            assert binary[2] == bytes.fromhex(before['symbols'][name]['frames'][index])
            assert binary[2] == threshold(raw)
            assert sharp.get('activity:' + name, clock + 2.) == binary
            rows.append(dict(group='activity', symbol=name, frame=index,
                             payload_before=packet_check(raw),
                             payload_after=packet_check(binary[2])))
    assert len(rows) == 157

    for name in ('home_x', 'home_y', 'home_z', 'home_xy', 'home_xyz',
                 'move_x', 'move_y', 'move_z', 'move_xyz'):
        for frame in range(4):
            assert sharp.get('cartesian:' + name, frame * .5) == source.get('cartesian:' + name, frame * .5)
    for name in ('project-klipper', 'project-zortrax'):
        for frame in range(4):
            assert sharp.get(name, frame * .5) == source.get(name, frame * .5)
    assert sharp_sprite.cache_info().maxsize == 64
    assert sharp_sprite.cache_info().currsize <= 64

    package = ROOT / '.ci/host-update'
    sys.path.insert(0, str(package))
    sys.path.insert(0, str(package / 'tests'))
    from test_settings_information import session
    from test_activity_graphics import right_icon
    with session() as h:
        # The historical session deliberately constructs OEMGraphics() in
        # source mode. Construct the real production UI to test the new default.
        h.ui = M300MenuUI(h.config)
        h.objects['m300_menu_ui'] = h.ui
        h.oled.menu_reverse = True
        assert h.ui.oem_sprites.sharp is True
        assert h.ui.get_status(h.now)['icon_style'] == 'SHARP-HOST-1'
        h.menu.page = 'klipper'
        # Fixed read-only menu snapshot, no command is executed by this test.
        h.menu.rows = lambda now: ('Klipper', [
            ('Back', ('page', 'main')), ('Bed mesh', ('native_gcode', 'BED_MESH'))])
        h.oled.page, h.oled.selection = 'm04', 1
        h.oled._render_key = None
        h.oled._render(h.now)
        # Idle menu icons use phase zero; active procedures keep their cadence.
        assert right_icon(h.oled._render_wire) == h.ui.oem_sprites.get('activity:bed_mesh', 0.)[2]
        assert not any(e[0] in ('heat', 'move', 'fan') for e in h.events)
    with session() as h:
        original_getboolean = h.config.getboolean
        h.config.getboolean = lambda key, default: (False if key == 'sharp_icons'
                                                   else original_getboolean(key, default))
        ui = M300MenuUI(h.config)
        assert ui.sharp_icons is False and ui.oem_sprites.sharp is False

    sample = source.get('0x0801c958')
    start = time.perf_counter()
    for _ in range(10000):
        sharp_sprite(sample)
    elapsed = time.perf_counter() - start
    report = dict(status='PASS_SHARP_HOST_ICONS', revision='SHARP-HOST-1',
                  oem_descriptors=37, oem_frames=61, activity_symbols=24, activity_frames=96,
                  threshold=8, canonical_asset_files_unchanged=True,
                  exact_activity_beta20_restoration=True,
                  original_oem_mode_preserved=True, axis_logo_pixels_preserved=True,
                  real_menu_constructor_default_verified=True,
                  real_menu_constructor_source_fallback_verified=True,
                  cache_max_frames=64, warm_cache_calls=10000,
                  warm_cache_seconds=elapsed, transport_lossless=True,
                  physical_printer_tested=False, mcu_flashed=False, results=rows)
    output = ROOT / '.ci/reports/OLED_SHARP.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}))


if __name__ == '__main__':
    main()
