# SPDX-License-Identifier: GPL-3.0-or-later
"""Display-only monochrome adaptation of the official Klipper logo.

Source: Klipper3d/klipper docs/img/klipper.svg (paths 2 and 35), GPL-3.0.
This overlays the old project-klipper K in the menu, preserving the existing
top toolhead animation, source sprite bank and 500ms refresh. No hardware I/O.
"""
from functools import lru_cache

WIDTH = HEIGHT = 50
# Silhouettes of the two official paths, after reducing the tiny curved tip
# to vertices at the 50x50 display resolution. Both colors become OLED white.
_OUTER = ((30,34), (30,174), (290,429), (405,424), (485,424),
          (730,174), (730,34), (720,34), (385,374), (40,34))
_NOZZLE = ((259,424), (360,424), (360,359), (30,34), (90,34),
           (385,324), (670,34), (730,34), (410,359), (410,444),
           (400,454), (259,454), (245,439))


def _inside(x, y, polygon):
    inside = False
    last_x, last_y = polygon[-1]
    for next_x, next_y in polygon:
        if (next_y > y) != (last_y > y):
            crossing = (last_x - next_x) * (y - next_y) / (last_y - next_y) + next_x
            if x < crossing:
                inside = not inside
        last_x, last_y = next_x, next_y
    return inside


def _logo_pixels():
    # Position: x10..40 / y14..40. Keep the printer frame and header intact.
    positions = []
    for y in range(14, 41):
        for x in range(10, 41):
            source_x = 30 + (x + .5 - 10) / .042
            source_y = 34 + (y + .5 - 14) / .060
            if _inside(source_x, source_y, _OUTER) or _inside(source_x, source_y, _NOZZLE):
                positions.append((x, y))
    return tuple(positions)


LOGO_PIXELS = _logo_pixels()


@lru_cache(maxsize=4)
def _replace_k(packed):
    if len(packed) != 1250:
        raise ValueError('M300 Klipper icon requires 50x50 4bpp pixels')
    data = bytearray(packed)

    def set_pixel(x, y, value):
        offset = y * 25 + x // 2
        if x & 1:
            data[offset] = (data[offset] & 0xf0) | value
        else:
            data[offset] = (data[offset] & 0x0f) | (value << 4)

    # Remove the obsolete letter, not the surrounding printer outline.
    for y in range(14, 42):
        for x in range(10, 42):
            set_pixel(x, y, 0)
    for x, y in LOGO_PIXELS:
        set_pixel(x, y, 15)
    return bytes(data)


def klipper_frame(sprite):
    if sprite is None:
        return None
    width, height, packed = sprite
    if (width, height) != (WIDTH, HEIGHT):
        raise ValueError('M300 Klipper icon expects a 50x50 sprite')
    return width, height, _replace_k(packed)
