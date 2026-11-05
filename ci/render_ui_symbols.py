#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reproducible 50px project symbol drafts; never installs runtime artwork."""
import html
import json
from pathlib import Path

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
)


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
            y = 39 + (frame % 2)*2
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
        shift = frame % 2 * 3
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
    return '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">%s</g>' % ''.join(parts)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, title, concept in SYMBOLS:
        frames = []
        for index in range(4):
            values = ';'.join('1' if x == index else '0' for x in (0, 1, 2, 3, 0))
            frames.append('<g opacity="%d">%s<animate attributeName="opacity" values="%s" keyTimes="0;.25;.5;.75;1" dur="2s" repeatCount="indefinite" calcMode="discrete"/></g>'
                          % (int(index == 0), drawing(name, index), values))
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50" width="50" height="50" color="white"><title>%s — project draft</title><rect width="50" height="50" fill="black"/>%s</svg>\n' % (html.escape(title), ''.join(frames))
        (OUT / (name + '.svg')).write_text(svg)
        manifest.append(dict(id=name, title=title, concept=concept, width=50, height=50,
                             frames=4, frame_ms=500, runtime_enabled=False,
                             origin='New project design; not an extracted OEM asset'))
    (OUT / 'catalog.json').write_text(json.dumps(manifest, indent=2) + '\n')
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="950" viewBox="0 0 1120 950">',
             '<rect width="1120" height="950" fill="#0b1118"/>',
             '<g font-family="DejaVu Sans,sans-serif" fill="#eaf5ff">',
             '<text x="32" y="46" font-size="28" font-weight="bold">Printer activity symbols</text>',
             '<text x="32" y="75" font-size="15" fill="#a8c0d2">12 project drafts · monochrome · 50 × 50 px · four frames / 500 ms</text>',
             '<text x="32" y="100" font-size="14" fill="#a8c0d2">Based on M300 / Inventure visual vocabulary. Original OLED homing animation is retained.</text>']
    for index, (name, title, _) in enumerate(SYMBOLS):
        x, y = 32 + (index % 4)*272, 126 + (index // 4)*257
        parts.append('<rect x="%d" y="%d" width="248" height="237" rx="10" fill="#13202d" stroke="#2e4556"/>' % (x, y))
        parts.append('<g transform="translate(%d %d) scale(3)" color="#eaf5ff">%s</g>' % (x+49, y+16, drawing(name)))
        parts.append('<text x="%d" y="%d" font-size="17" font-weight="bold">%s</text>' % (x+16, y+191, html.escape(title)))
        parts.append('<text x="%d" y="%d" font-size="12" fill="#a8c0d2">%s · DRAFT</text>' % (x+16, y+215, name))
    parts.extend(['<text x="32" y="932" font-size="13" fill="#a8c0d2">Preview only. The new symbols are not yet assigned to runtime OLED screens.</text>', '</g></svg>\n'])
    (OUT / 'preview.svg').write_text(''.join(parts))
    print('Generated 12 symbol drafts and the review sheet')


if __name__ == '__main__':
    main()
