# SPDX-License-Identifier: GPL-3.0-or-later
"""Three-tone complete Klipper V/nozzle symbol and lowercase 'klipper' wordmark.

Display-only native 4bpp overlay inside the original 50x50 M300 printer
frame. A tiny pixel font redraws the lowercase wordmark from the official
Klipper3d/klipper/docs/img/klipper.svg (GPL-3.0) at OLED resolution.
No external fonts, SVG parsing, motion, heating, timers or network access.
"""
from functools import lru_cache

WIDTH = HEIGHT = 50
SLATE = 7      # dark grey original wing: lower OLED luminance
ACCENT = 11    # red original inner V: medium OLED luminance
BRIGHT = 15    # lowercase 'klipper' text: original firmware white

_GLYPHS = {
    'k': ('1001', '1010', '1100', '1010', '1001'),
    'l': ('10', '10', '10', '10', '11'),
    'i': ('1', '0', '1', '1', '1'),
    'p': ('110', '101', '110', '100', '100'),
    'e': ('011', '100', '111', '100', '011'),
    'r': ('110', '101', '100', '100', '100'),
}


def _inside(x, y, polygon):
    inside = False
    previous_x, previous_y = polygon[-1]
    for next_x, next_y in polygon:
        if ((next_y > y) != (previous_y > y)
                and x < (previous_x-next_x)*(y-next_y)/(previous_y-next_y)+next_x):
            inside = not inside
        previous_x, previous_y = next_x, next_y
    return inside


def _logo():
    pixels = {}
    # Two angular V wings and smaller inner accent strips, source-matched
    # to the official Klipper mark but simplified for the 50-pixel display.
    shapes = (
        (SLATE, ((11,17),(15,17),(27,29),(27,32),(23,32),(11,21))),
        (SLATE, ((35,17),(39,17),(27,30),(27,32),(23,32),(23,29))),
        (ACCENT, ((11,17),(13,17),(26,30),(26,32),(24,32),(11,19))),
        (ACCENT, ((37,17),(39,17),(26,32),(24,32),(24,30))),
    )
    for level, polygon in shapes:
        for y in range(16, 33):
            for x in range(10, 41):
                if _inside(x+.5, y+.5, polygon):
                    pixels[x, y] = level

    word = 'klipper'
    glyph_widths = [len(_GLYPHS[letter][0]) for letter in word]
    current_x = (WIDTH-sum(glyph_widths)-len(word)+1)//2
    for letter, width in zip(word, glyph_widths):
        for dy, row in enumerate(_GLYPHS[letter]):
            for dx, mark in enumerate(row):
                if mark == '1':
                    pixels[current_x+dx, 34+dy] = BRIGHT
        current_x += width+1
    return tuple(sorted((x, y, value) for (x, y), value in pixels.items()))


LOGO_PIXELS = _logo()


@lru_cache(maxsize=4)
def _replace_k(packed):
    if len(packed) != WIDTH*HEIGHT//2:
        raise ValueError('M300 Klipper icon requires 50x50 4bpp pixels')
    data = bytearray(packed)

    def set_pixel(x, y, tone):
        offset = y * (WIDTH//2) + x//2
        if x & 1:
            data[offset] = (data[offset] & 0xf0) | tone
        else:
            data[offset] = (data[offset] & 0x0f) | (tone << 4)

    # Keep the OEM-scale 2px printer surround, the four-frame toolhead and
    # the 50x50 display footprint. Erase the old K and the obsolete moving
    # 3px marker under the bed (the former animated x=12/19/26/33, y=44).
    # Redraw the platform stroke at fixed coordinates: no bottom animation.
    for y in range(15, 42):
        for x in range(10, 41):
            set_pixel(x, y, 0)
    for y in (43, 44, 45):
        for x in range(10, 41):
            set_pixel(x, y, 0)
    # Platform: two fixed high-luminance scanlines, matching the original
    # 1.6px stroked perimeter rasterized to approximately two OLED pixels.
    for x in range(8, 43):
        for y in (42, 43):
            set_pixel(x, y, 15)
    for x, y, tone in LOGO_PIXELS:
        set_pixel(x, y, tone)
    return bytes(data)


def klipper_frame(sprite):
    if sprite is None:
        return None
    width, height, packed = sprite
    if (width, height) != (WIDTH, HEIGHT):
        raise ValueError('M300 Klipper icon expects a 50x50 sprite')
    return width, height, _replace_k(packed)
