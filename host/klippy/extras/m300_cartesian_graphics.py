# SPDX-License-Identifier: GPL-3.0-or-later
"""50x50 native 4bpp Cartesian axis symbols for the Classic M300 OLED.

Presentation only: uses no printer objects, movements, timers or MCU polling.
The existing OLED 500 ms refresh selects one of four cached monochrome frames.
"""
import math
from functools import lru_cache

PREFIX = 'cartesian:'
WIDTH = HEIGHT = 50
FRAME_SECONDS = 0.5
KINDS = {
    'home_x': 'X', 'home_y': 'Y', 'home_z': 'Z',
    'home_xy': 'XY', 'home_xyz': 'XYZ',
    'move_x': 'X', 'move_y': 'Y', 'move_z': 'Z',
    'move_xyz': 'XYZ',
}

def _pixel(pixels, x, y, value):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        pos = y * WIDTH + x
        pixels[pos] = max(pixels[pos], value)

def _line(pixels, x0, y0, x1, y1, value):
    dx, dy = abs(x1-x0), -abs(y1-y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx + dy
    while True:
        _pixel(pixels, x0, y0, value)
        if x0 == x1 and y0 == y1:
            break
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x0 += sx
        if doubled <= dx:
            error += dx
            y0 += sy

def _glyph(pixels, letter, x, y, level):
    # Stroke letters remain legible at the native 50x50 OLED icon size.
    if letter == 'X':
        _line(pixels,x,y,x+4,y+6,level)
        _line(pixels,x+4,y,x,y+6,level)
    elif letter == 'Y':
        _line(pixels,x,y,x+2,y+3,level)
        _line(pixels,x+4,y,x+2,y+3,level)
        _line(pixels,x+2,y+3,x+2,y+6,level)
    elif letter == 'Z':
        _line(pixels,x,y,x+4,y,level)
        _line(pixels,x+4,y,x,y+6,level)
        _line(pixels,x,y+6,x+4,y+6,level)

def _axis(pixels, letter, level):
    ox, oy = 25, 31
    if letter == 'X':
        end = 40, 31
        wings = ((36,28),(36,34))
        label = (40,36)
    elif letter == 'Y':
        end = 12, 40
        wings = ((17,39),(15,35))
        label = (6,37)
    else:
        end = 25, 17
        wings = ((22,21),(28,21))
        label = (29,17)
    _line(pixels,ox,oy,*end,level)
    for wing in wings:
        _line(pixels,*wing,*end,level)
    _glyph(pixels,letter,*label,level)

def _make(name, frame):
    pixels = bytearray(WIDTH * HEIGHT)
    # Machine outline, top bridge and the print platform are stationary.
    for x0,y0,x1,y1 in ((4,4,45,4),(4,4,4,46),(45,4,45,46),
                        (4,46,45,46),(9,9,40,9),(9,43,40,43)):
        _line(pixels,x0,y0,x1,y1,6)
    # Retain the top toolhead motion. Nothing flashes under the platform.
    head = (19,22,25,23)[frame]
    _line(pixels,head-4,7,head+4,7,11)
    _line(pixels,head-2,7,head-2,12,11)
    _line(pixels,head+2,7,head+2,12,11)
    _line(pixels,head-2,12,head,15,13)
    _line(pixels,head+2,12,head,15,13)
    active = KINDS[name]
    # Every axis remains visible; only selected axes and letters blink.
    for letter in 'XYZ':
        tone = (15 if frame % 2 == 0 else 3) if letter in active else 7
        _axis(pixels,letter,tone)
    _pixel(pixels,25,31,15)
    raw = bytearray(WIDTH * HEIGHT // 2)
    for pos, tone in enumerate(pixels):
        if pos % 2:
            raw[pos//2] |= tone
        else:
            raw[pos//2] |= tone << 4
    return (WIDTH, HEIGHT, bytes(raw))

class CartesianGraphics:
    @staticmethod
    @lru_cache(maxsize=36)
    def frame(name, index):
        if name not in KINDS or index not in range(4):
            return None
        return _make(name, index)

    def get(self, name, now=0.):
        name = str(name).lower().removeprefix(PREFIX)
        if name not in KINDS:
            return None
        try:
            now = float(now)
        except (TypeError, ValueError):
            now = 0.
        if not math.isfinite(now):
            now = 0.
        index = int(max(now,0.) / FRAME_SECONDS) % 4
        return self.frame(name,index)
