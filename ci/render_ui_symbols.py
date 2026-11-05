#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate project SVGs and optional native OLED frames and review animations.

SVG generation uses the standard library. --raster requires CairoSVG and Pillow
only on the asset-authoring machine; the printer never imports either package.
"""
import argparse
import hashlib
import html
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/assets/ui-symbols'
SYMBOLS = (
    ('bed_mesh', 'Bed mesh', 'Five contact pads and a moving measurement dot'),
    ('heat_nozzle', 'Heat the nozzle', 'Nozzle with rising heat waves'),
    ('heat_bed', 'Heat the bed', 'Platform with rising heat waves'),
    ('cooling', 'Cooling', 'Thermometer and downward temperature arrow'),
    ('fan_upper', 'Upper fan', 'Rotating fan with an upper position marker'),
    ('fan_lower', 'Lower fan', 'Rotating fan with a lower position marker'),
    ('sd_read', 'Read SD card', 'Card, contacts and moving data dots'),
    ('file_convert', 'Prepare model file', 'Two files and a transfer arrow'),
    ('clean_nozzle', 'Clean the nozzle', 'Nozzle and a moving brush'),
    ('link_status', 'Printer connection', 'Two ports with a moving link dot'),
    ('oled_brightness', 'OLED brightness', 'Display with a sixteen-segment bar'),
    ('led_brightness', 'LED brightness', 'Lamp with a sixteen-segment bar'),
    ('filament_jam', 'Filament jam', 'Feed rollers and a blocked filament path'),
    ('filament_runout', 'Filament runout', 'An empty spool and a broken feed path'),
    ('waiting_klipper', 'Waiting for Klipper', 'MCU and host with a travelling connection marker'),
    ('connection_lost', 'Connection lost', 'A broken link with a persistent cross'),
    ('hotend_overheat', 'Hotend overheat', 'Nozzle, high temperature and warning rays'),
    ('bed_overheat', 'Bed overheat', 'Platform, high temperature and warning rays'),
    ('sensor_fault', 'Temperature sensor fault', 'Thermometer with a broken sensor lead'),
    ('heating_failed', 'Heating failed', 'Heater, low temperature and a warning triangle'),
    ('probe_contact_fault', 'Probe contact fault', 'Nozzle contact pad and a persistent warning'),
    ('platform_connector', 'Platform connector fault', 'Separated platform connector and a warning'),
    ('emergency_stop', 'Emergency stop', 'Stop octagon with a fixed exclamation mark'),
    ('firmware_update', 'Firmware update', 'Memory chip and an incoming data arrow'),
)
FRAME_MS = 500
FRAME_COUNT = 4
MCU_FRAMES = ROOT / 'mcu/SOURCE_MCU/overlay/src/stm32/m300_oled_activity.inc'


def drawing(name, frame=0):
    parts = []

    def path(d, fill='none'):
        parts.append('<path d="%s" fill="%s"/>' % (d, fill))

    def rect(x, y, w, h, fill='none'):
        parts.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>'
                     % (x, y, w, h, fill))

    def dot(x, y, radius=2):
        parts.append('<circle cx="%s" cy="%s" r="%s" fill="currentColor"/>' % (x, y, radius))

    def nozzle():
        rect(15, 7, 20, 10)
        path('M18 17v8l7 8 7-8v-8M22 33h6')

    def bar():
        parts.append('<g stroke-width=".55">')
        for index in range(16):
            rect(2 + index*3, 44, 2, 4, 'currentColor' if index < (frame+1)*4 else 'none')
        parts.append('</g>')

    if name == 'bed_mesh':
        rect(6, 10, 38, 32)
        for x, y in ((10, 14), (34, 14), (22, 24), (10, 32), (34, 32)):
            rect(x, y, 6, 6)
        x, y = ((13, 17), (37, 17), (37, 35), (25, 27))[frame]
        dot(x, y, 3)
        path('M25 2v6m-3-3 3 3 3-3')
    elif name == 'heat_nozzle':
        nozzle()
        for x in (14, 25, 36):
            y = 42 - frame*2
            path('M%d %dc-5-3 5-6 0-10' % (x, y))
    elif name == 'heat_bed':
        path('M5 34h40l-5 8H10zM10 45h30')
        for x in (13, 25, 37):
            y = 27 - frame
            path('M%d %dc-7-5 7-9 0-16m-3 3 3-3 3 3' % (x, y))
    elif name == 'cooling':
        path('M12 29V9a4 4 0 0 1 8 0v20a8 8 0 1 1-8 0zM16 17v19')
        dot(16, 36, 3)
        path('M35 8v28m-7-7 7 7 7-7M30 13h10M30 19h10')
        dot(35, 14 + frame*5, 1)
    elif name.startswith('fan_'):
        parts.append('<circle cx="25" cy="25" r="17" fill="none"/>')
        parts.append('<g transform="rotate(%d 25 25)">' % (frame*30))
        for angle in (0, 120, 240):
            parts.append('<path transform="rotate(%d 25 25)" d="M24 22Q12 9 12 23Q13 31 24 27z" fill="currentColor"/>' % angle)
        parts.append('</g>')
        dot(25, 25, 3)
        if name == 'fan_upper':
            path('M19 5 25 1l6 4')
        else:
            path('M19 45 25 49l6-4')
    elif name == 'sd_read':
        path('M10 4h23l7 8v33H10zM15 4v12h18V4')
        for x in (19, 24, 29):
            path('M%d 7v5' % x)
        path('M16 24h18M16 31h18M16 38h10')
        dot(16 + frame*6, 31, 2)
    elif name == 'file_convert':
        path('M3 7h12l5 5v20H3zM15 7v6h5M30 7h12l5 5v20H30zM42 7v6h5')
        path('M8 38h30m-5-5 5 5-5 5')
        dot(10 + frame*7, 38, 2)
        path('M7 18h8M7 23h6M34 18h8M34 23h6')
    elif name == 'clean_nozzle':
        nozzle()
        shift = (0, 2, 4, 1)[frame]
        path('M%d 41l12-11 5 5-12 11z' % (22+shift))
        for index in range(4):
            path('M%d 38l-5-5' % (22 + shift + index*3))
    elif name == 'link_status':
        rect(3, 14, 10, 20)
        rect(37, 14, 10, 20)
        path('M13 20h24m-5-5 5 5-5 5M37 29H13m5-5-5 5 5 5')
        dot(17 + frame*5, 20, 2)
    elif name == 'oled_brightness':
        rect(4, 5, 42, 30)
        path('M19 35v5m12-5v5M16 40h18')
        for index in range(frame+1):
            rect(12 + index*7, 13, 4, 14, 'currentColor')
        bar()
    elif name == 'led_brightness':
        path('M18 26C5 14 10 4 25 4S45 14 32 26l-2 7H20zM20 36h10M22 39h6')
        for x in (3, 47):
            path('M%d 17h%d' % (x, 4 if x == 3 else -4))
        if frame % 2:
            path('M8 5l4 4M38 9l4-4')
        bar()
    elif name == 'filament_jam':
        for x in (13, 37):
            parts.append('<circle cx="%d" cy="15" r="7"/>' % x)
            parts.append('<path transform="rotate(%d %d 15)" d="M%d 11v8"/>'
                         % ((0, 12, 24, 12)[frame], x, x))
        path('M25 3v19l-4 5 8 5-4 4v10M3 39h12m-4-4 4 4-4 4')
        dot(25, 5+frame*4, 1.5)
        path('M36 33l10 13m0-13L36 46')
    elif name == 'filament_runout':
        parts.append('<circle cx="18" cy="18" r="13"/><circle cx="18" cy="18" r="4"/>')
        path('M18 5v5M18 26v5M5 18h5M26 18h5M31 18h10v12m0 9v7M37 33l8 4m-8 0 8-4')
        dot(41, 20+frame*2, 1.5)
    elif name in ('waiting_klipper', 'connection_lost'):
        rect(3, 12, 12, 23)
        rect(35, 12, 12, 23)
        path('M7 17h4M7 21h4M39 17h4M39 21h4M7 30h4M39 30h4')
        if name == 'waiting_klipper':
            path('M15 24h20')
            dot(18+frame*5, 24, 2)
            for i in range(frame+1):
                dot(19+i*4, 42, .8)
        else:
            path('M15 24h5m10 0h5M21 19l8 10m0-10-8 10')
            path('M%d 39h%d' % (18-frame, 14+frame*2))
    elif name in ('hotend_overheat', 'bed_overheat'):
        if name == 'hotend_overheat':
            path('M4 8h20v10H4zM7 18v9l7 8 7-8v-9M11 35h6')
        else:
            path('M3 29h23l-4 9H7zM7 42h15M9 23c-5-4 5-7 0-11M21 23c-5-4 5-7 0-11')
        path('M34 31V13a4 4 0 0 1 8 0v18a7 7 0 1 1-8 0zM38 15v22')
        dot(38, 37, 2.4)
        path('M33 %dh10' % (20-frame*2))
        path('M27 %dl3-2M46 %dl3-2' % (5+frame*2, 8+frame*2))
    elif name == 'sensor_fault':
        path('M10 29V9a4 4 0 0 1 8 0v20a8 8 0 1 1-8 0zM14 17v19')
        dot(14, 36, 2.5)
        path('M22 36h7v-7m0-9v-7h13M25 22l8 5m0-5-8 5M37 9l8 8m0-8-8 8')
        dot(24+frame*2, 36, 1.3)
    elif name == 'heating_failed':
        path('M5 8h19v10H5zM8 18v8l6 7 7-7v-8M11 34h6M4 43h17M7 39h11')
        path('M35 18 48 43H22zM35 27v7')
        dot(35, 38, .8)
        dot(5+frame*4, 43, 1.2)
    elif name == 'probe_contact_fault':
        path('M6 5h22v10H6zM9 15v9l8 8 8-8v-9M6 40h24v5H6zM17 32v4')
        path('M36 8l10 10m0-10L36 18M32 39h15m-4-4 4 4-4 4')
        dot(17, 33+frame, 1)
    elif name == 'platform_connector':
        path('M3 11h15v9h5v13h-5v9H3zM47 11H32v9h-5v13h5v9h15zM9 17v19M40 17v19')
        path('M21 3l8 10m0-10-8 10')
        path('M%d 24h4m-4 5h4' % (18+frame))
    elif name == 'emergency_stop':
        path('M15 4h20l11 11v20L35 46H15L4 35V15zM25 14v15')
        dot(25, 36, 1.6)
        # The stop outline and exclamation remain visible in every frame.
        for i in range(frame+1):
            path('M%d 9h3' % (18+i*4))
    elif name == 'firmware_update':
        rect(11, 17, 28, 25)
        rect(17, 23, 16, 13)
        for x in (16, 22, 28, 34):
            path('M%d 14v3m0 25v4' % x)
        path('M25 2v16m-5-5 5 5 5-5M6 23h5M6 30h5M6 37h5M39 23h5M39 30h5M39 37h5')
        dot(25, 3+frame*3, 1.5)
    else:
        raise ValueError('Unknown symbol: ' + name)
    return '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">%s</g>' % ''.join(parts)


def frame_svg(name, frame):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" '
            'viewBox="0 0 50 50" color="white"><rect width="50" height="50" '
            'fill="black"/>%s</svg>\n' % drawing(name, frame))


def sheet_svg(symbols, frame=0, subtitle='New project symbols'):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="950" viewBox="0 0 1120 950">',
             '<rect width="1120" height="950" fill="#0b1118"/>',
             '<g font-family="DejaVu Sans,sans-serif" fill="#eaf5ff">',
             '<text x="32" y="46" font-size="28" font-weight="bold">Printer activity symbols</text>',
             '<text x="32" y="75" font-size="15" fill="#a8c0d2">%s · monochrome · 50 × 50 px · 4 frames / 500 ms</text>' % subtitle,
             '<text x="32" y="100" font-size="14" fill="#a8c0d2">M300 / Inventure visual vocabulary. Original OLED homing animation is retained.</text>']
    for index, (name, title, _) in enumerate(symbols):
        x, y = 32 + (index % 4)*272, 126 + (index // 4)*257
        parts.append('<rect x="%d" y="%d" width="248" height="237" rx="10" fill="#13202d" stroke="#2e4556"/>' % (x, y))
        parts.append('<g transform="translate(%d %d) scale(3)" color="#eaf5ff">%s</g>' % (x+49, y+16, drawing(name, frame)))
        parts.append('<text x="%d" y="%d" font-size="%d" font-weight="bold">%s</text>' % (x+16, y+191, 15 if len(title)>22 else 17, html.escape(title)))
        parts.append('<text x="%d" y="%d" font-size="12" fill="#a8c0d2">%s · 4 FRAMES</text>' % (x+16, y+215, name))
    parts.extend(['<text x="32" y="932" font-size="13" fill="#a8c0d2">Waiting for Klipper: MCU screen. Fault symbols: artwork ready; detection and limits are separate.</text>', '</g></svg>\n'])
    return ''.join(parts)


def packed_4bpp(image):
    values = image.tobytes()
    return bytes(((values[i] >> 4) << 4) | (values[i+1] >> 4)
                 for i in range(0, 2500, 2))


def mcu_header(images):
    lines = ['/* SPDX-License-Identifier: GPL-3.0-or-later',
             ' * Generated by ci/render_ui_symbols.py --raster. New project artwork.',
             ' * 50 x 50, one bit per pixel, seven bytes per row, MSB first.',
             ' * Four frames at 500 ms. Static flash data; no framebuffer allocation.',
             ' * Banks: waiting_klipper, connection_lost.',
             ' */', 'static const uint8_t local_activity_frames[2][4][350] = {']
    for name in ('waiting_klipper', 'connection_lost'):
        lines.append('    {')
        for image in images[name]:
            pixels = image.load()
            data = bytes(sum((pixels[x, y] != 0) << (7-bit)
                             for bit in range(8) if (x := byte*8+bit) < 50)
                         for y in range(50) for byte in range(7))
            lines.append('        {')
            lines.extend('            '+','.join('0x%02x' % b for b in data[i:i+14])+','
                         for i in range(0, len(data), 14))
            lines.append('        },')
        lines.append('    },')
    return '\n'.join(lines+['};', ''])


def raster_exports():
    import cairosvg
    from PIL import Image
    bank = dict(format='M300_PROJECT_SYMBOLS_4BPP_V1', width=50, height=50,
                packing='row-major, left pixel in high nibble', frame_ms=FRAME_MS,
                foreground=15, background=0, symbols={})
    images = {}
    for name, _, _ in SYMBOLS:
        frames = []
        for frame in range(FRAME_COUNT):
            png = cairosvg.svg2png(bytestring=frame_svg(name, frame).encode())
            # A single on/off colour, matching the MCU glyph and menu style.
            image = Image.open(io.BytesIO(png)).convert('L').point(lambda p: 255 if p >= 128 else 0)
            frames.append(image)
        images[name] = frames
        data = [packed_4bpp(frame) for frame in frames]
        bank['symbols'][name] = dict(frames=[b.hex() for b in data],
                                    sha256=[hashlib.sha256(b).hexdigest() for b in data])
    (OUT/'native_frames.json').write_text(json.dumps(bank, indent=2)+'\n')
    MCU_FRAMES.write_text(mcu_header(images))
    for prefix, symbols in (('preview', SYMBOLS[:12]), ('preview_additional', SYMBOLS[12:])):
        sheets = []
        for frame in range(FRAME_COUNT):
            # Use the exact native pixel frames at integer 3x scaling.
            svg = sheet_svg(symbols, frame, 'First 12 symbols' if prefix=='preview' else '12 additional symbols')
            sheet = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode()))).convert('RGB')
            for index, (name, _, _) in enumerate(symbols):
                x, y = 32+(index%4)*272+49, 126+(index//4)*257+16
                icon = images[name][frame].convert('RGB').resize((150, 150), Image.Resampling.NEAREST)
                sheet.paste(icon, (x, y))
            sheets.append(sheet)
        sheets[0].save(OUT/(prefix+'.png'))
        sheets[0].save(OUT/(prefix+'.gif'), save_all=True, append_images=sheets[1:],
                       duration=FRAME_MS, loop=0, disposal=2, optimize=False)
    # One download contains the individual animations, exact PNG frames and SVGs.
    with zipfile.ZipFile(OUT/'M300_ACTIVITY_SYMBOLS_24.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        def put(name, data):
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, data)
        for name, _, _ in SYMBOLS:
            put('svg/'+name+'.svg', (OUT/(name+'.svg')).read_bytes())
            frames = images[name]
            gif = io.BytesIO()
            frames[0].save(gif, format='GIF', save_all=True, append_images=frames[1:],
                           duration=FRAME_MS, loop=0, disposal=2, optimize=False)
            put('gif/'+name+'.gif', gif.getvalue())
            for index, image in enumerate(frames):
                png = io.BytesIO()
                image.save(png, format='PNG')
                put('frames/%s_%d.png' % (name, index), png.getvalue())
        for filename in ('catalog.json', 'native_frames.json'):
            put(filename, (OUT/filename).read_bytes())
    print('Rendered 96 native frames, 24 GIFs, two animated sheets and MCU wait data')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raster', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, title, concept in SYMBOLS:
        frames = []
        for index in range(4):
            values = ';'.join('1' if x == index else '0' for x in (0, 1, 2, 3, 0))
            frames.append('<g opacity="%d">%s<animate attributeName="opacity" values="%s" keyTimes="0;.25;.5;.75;1" dur="2s" repeatCount="indefinite" calcMode="discrete"/></g>'
                          % (int(index == 0), drawing(name, index), values))
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50" width="50" height="50" color="white"><title>%s — project symbol</title><rect width="50" height="50" fill="black"/>%s</svg>\n' % (html.escape(title), ''.join(frames))
        (OUT / (name + '.svg')).write_text(svg)
        manifest.append(dict(id=name, title=title, concept=concept, width=50, height=50,
                             frames=FRAME_COUNT, frame_ms=FRAME_MS,
                             runtime_enabled=name in ('waiting_klipper', 'connection_lost'),
                             runtime_target='MCU local waiting screen' if name in ('waiting_klipper', 'connection_lost') else None,
                             origin='New project design; not an extracted OEM asset'))
    (OUT / 'catalog.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (OUT/'preview.svg').write_text(sheet_svg(SYMBOLS[:12], subtitle='First 12 symbols'))
    (OUT/'preview_additional.svg').write_text(sheet_svg(SYMBOLS[12:], subtitle='12 additional symbols'))
    if args.raster:
        raster_exports()
    print('Generated 24 animated project symbols')


if __name__ == '__main__':
    main()
