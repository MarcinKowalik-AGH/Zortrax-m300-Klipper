#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""M300 diagnostic OLED renderer, adapted from the Inventure project atlas.

Pure renderer used by m300_oled.py; it does not access hardware itself.
It reproduces the 5x7 glyph bitmap and packed SSD1322 framebuffer rules from
Inventure boot v1.3, with the left-line + triangle menu composition derived
from the v1.3 OLED UI patch preview (last patch C sources not in release).

Does not access printers, SD or microcontroller peripherals.
"""
import argparse
import json
from functools import lru_cache
from pathlib import Path

WIDTH, HEIGHT = 256, 64
RAW_LEN = WIDTH * HEIGHT // 2  # 8192 bytes
# Glyph masks supplied with the user project; no system font dependency.
FONT = {'A': [14, 17, 17, 31, 17, 17, 17], 'B': [30, 17, 17, 30, 17, 17, 30], 'C': [15, 16, 16, 16, 16, 16, 15], 'D': [30, 17, 17, 17, 17, 17, 30], 'E': [31, 16, 16, 30, 16, 16, 31], 'F': [31, 16, 16, 30, 16, 16, 16], 'G': [15, 16, 16, 23, 17, 17, 15], 'H': [17, 17, 17, 31, 17, 17, 17], 'I': [31, 4, 4, 4, 4, 4, 31], 'J': [7, 2, 2, 2, 18, 18, 12], 'K': [17, 18, 20, 24, 20, 18, 17], 'L': [16, 16, 16, 16, 16, 16, 31], 'M': [17, 27, 21, 21, 17, 17, 17], 'N': [17, 25, 21, 19, 17, 17, 17], 'O': [14, 17, 17, 17, 17, 17, 14], 'P': [30, 17, 17, 30, 16, 16, 16], 'Q': [14, 17, 17, 17, 21, 18, 13], 'R': [30, 17, 17, 30, 20, 18, 17], 'S': [15, 16, 16, 14, 1, 1, 30], 'T': [31, 4, 4, 4, 4, 4, 4], 'U': [17, 17, 17, 17, 17, 17, 14], 'V': [17, 17, 17, 17, 17, 10, 4], 'W': [17, 17, 17, 21, 21, 21, 10], 'X': [17, 17, 10, 4, 10, 17, 17], 'Y': [17, 17, 10, 4, 4, 4, 4], 'Z': [31, 1, 2, 4, 8, 16, 31], '0': [14, 17, 19, 21, 25, 17, 14], '1': [4, 12, 4, 4, 4, 4, 14], '2': [14, 17, 1, 2, 4, 8, 31], '3': [30, 1, 1, 14, 1, 1, 30], '4': [2, 6, 10, 18, 31, 2, 2], '5': [31, 16, 16, 30, 1, 1, 30], '6': [14, 16, 16, 30, 17, 17, 14], '7': [31, 1, 2, 4, 8, 8, 8], '8': [14, 17, 17, 14, 17, 17, 14], '9': [14, 17, 17, 15, 1, 1, 14], 'a': [0, 0, 14, 1, 15, 17, 15], 'b': [16, 16, 22, 25, 17, 17, 30], 'c': [0, 0, 15, 16, 16, 16, 15], 'd': [1, 1, 13, 19, 17, 17, 15], 'e': [0, 0, 14, 17, 31, 16, 14], 'f': [6, 9, 8, 28, 8, 8, 8], 'g': [0, 0, 15, 17, 15, 1, 14], 'h': [16, 16, 22, 25, 17, 17, 17], 'i': [4, 0, 12, 4, 4, 4, 14], 'j': [2, 0, 6, 2, 2, 18, 12], 'k': [16, 16, 18, 20, 24, 20, 18], 'l': [12, 4, 4, 4, 4, 4, 14], 'm': [0, 0, 26, 21, 21, 21, 21], 'n': [0, 0, 22, 25, 17, 17, 17], 'o': [0, 0, 14, 17, 17, 17, 14], 'p': [0, 0, 30, 17, 30, 16, 16], 'q': [0, 0, 15, 17, 15, 1, 1], 'r': [0, 0, 22, 25, 16, 16, 16], 's': [0, 0, 15, 16, 14, 1, 30], 't': [8, 8, 28, 8, 8, 9, 6], 'u': [0, 0, 17, 17, 17, 19, 13], 'v': [0, 0, 17, 17, 17, 10, 4], 'w': [0, 0, 17, 17, 21, 21, 10], 'x': [0, 0, 17, 10, 4, 10, 17], 'y': [0, 0, 17, 17, 15, 1, 14], 'z': [0, 0, 31, 2, 4, 8, 31], ' ': [0, 0, 0, 0, 0, 0, 0], '.': [0, 0, 0, 0, 0, 6, 6], ',': [0, 0, 0, 0, 0, 4, 8], ':': [0, 0, 4, 0, 0, 4, 0], ';': [0, 0, 4, 0, 0, 4, 8], '-': [0, 0, 0, 31, 0, 0, 0], '_': [0, 0, 0, 0, 0, 0, 31], '+': [0, 4, 4, 31, 4, 4, 0], '=': [0, 0, 31, 0, 31, 0, 0], '(': [2, 4, 8, 8, 8, 4, 2], ')': [8, 4, 2, 2, 2, 4, 8], '[': [14, 8, 8, 8, 8, 8, 14], ']': [14, 2, 2, 2, 2, 2, 14], '{': [3, 4, 4, 8, 4, 4, 3], '}': [24, 4, 4, 2, 4, 4, 24], '<': [1, 2, 4, 8, 4, 2, 1], '>': [16, 8, 4, 2, 4, 8, 16], '?': [14, 17, 1, 2, 4, 0, 4], '!': [4, 4, 4, 4, 4, 0, 4], "'": [4, 4, 8, 0, 0, 0, 0], '"': [10, 10, 0, 0, 0, 0, 0], '#': [10, 10, 31, 10, 31, 10, 10], '$': [4, 15, 20, 14, 5, 30, 4], '&': [12, 18, 20, 8, 21, 18, 13], '*': [0, 21, 14, 31, 14, 21, 0], '@': [14, 17, 23, 21, 23, 16, 14], '^': [4, 10, 17, 0, 0, 0, 0], '|': [4, 4, 4, 4, 4, 4, 4], '~': [0, 0, 9, 22, 0, 0, 0], '`': [8, 4, 0, 0, 0, 0, 0], '%': [25, 26, 2, 4, 8, 11, 19], '©': [28, 34, 93, 81, 93, 34, 28], '®': [14, 17, 29, 27, 21, 17, 14], '°': [6, 9, 9, 6, 0, 0, 0], '•': [0, 0, 14, 14, 14, 0, 0], '←': [0, 4, 8, 31, 8, 4, 0], '→': [0, 4, 2, 31, 2, 4, 0], '✓': [0, 0, 1, 2, 20, 8, 0], '×': [0, 17, 10, 4, 10, 17, 0], '/': [1, 1, 2, 4, 4, 8, 16], '\\': [16, 16, 8, 4, 4, 2, 1], 'ą': [0, 0, 14, 1, 15, 17, 15], 'Ą': [14, 17, 17, 31, 17, 17, 17], 'ć': [2, 0, 15, 16, 16, 16, 15], 'Ć': [15, 16, 16, 16, 16, 16, 15], 'ę': [0, 0, 14, 17, 31, 16, 15], 'Ę': [31, 16, 16, 30, 16, 16, 31], 'ł': [12, 4, 4, 7, 4, 4, 14], 'Ł': [16, 16, 16, 23, 16, 16, 31], 'ń': [2, 0, 22, 25, 17, 17, 17], 'Ń': [19, 25, 21, 19, 17, 17, 17], 'ó': [2, 0, 14, 17, 17, 17, 14], 'Ó': [14, 17, 17, 17, 17, 17, 14], 'ś': [2, 0, 15, 16, 14, 1, 30], 'Ś': [15, 16, 16, 14, 1, 1, 30], 'ź': [2, 0, 31, 2, 4, 8, 31], 'Ź': [31, 1, 2, 4, 8, 16, 31], 'ż': [4, 0, 31, 2, 4, 8, 31], 'Ż': [31, 1, 2, 4, 8, 16, 31]}
# Support both Klippy's package import and the pinned offline preview script.
try:
    from .m300_ui_m11_font import supplemental as _m11_supplemental
except ImportError:
    import importlib.util as _m11_importlib
    _m11_spec = _m11_importlib.spec_from_file_location(
        'm300_ui_m11_font_standalone', Path(__file__).with_name('m300_ui_m11_font.py'))
    _m11_source = _m11_importlib.module_from_spec(_m11_spec)
    _m11_spec.loader.exec_module(_m11_source)
    _m11_supplemental = _m11_source.supplemental
M11_FONT = _m11_supplemental(FONT)
TITLE = "M300 Klipper / diagnostyka"


@lru_cache(maxsize=128)
def _text_pattern(chars, level, parity):
    """Bounded cache of transparent packed glyph writes, independent of XY."""
    writes = {}
    x = parity
    for c in chars:
        glyph = FONT.get(c, M11_FONT.get(c, FONT['?']))
        width = 7 if c == '©' else 5
        for dy, bits in enumerate(glyph):
            for dx in range(width):
                if bits & (1 << (width-1-dx)):
                    px = x+dx
                    offset = (px//2)*HEIGHT+dy
                    shift = 0 if px & 1 else 4
                    mask, value = writes.get(offset, (0, 0))
                    writes[offset] = (mask | (15 << shift),
                                      value | ((level & 15) << shift))
        x += width+1
    return tuple((offset, mask, value) for offset, (mask, value) in writes.items())


@lru_cache(maxsize=8)
def _header_pattern(title):
    f = Frame()
    f.text(4, 2, title)
    for x in range(4, 252):
        f.pixel(x, 11, 5)
    return bytes(f.raw)


@lru_cache(maxsize=64)
def _sprite_pattern(sprite):
    """Transpose each original frame once; cached blits copy packed columns.

    There are only 61 audited frame references. The cache is bounded even for
    test/custom inputs; OEM greyscale nibbles are never quantized or rescaled.
    """
    width, height, pixels = sprite
    if (type(width) is not int or type(height) is not int
            or not 1 <= width <= 96 or not 1 <= height <= HEIGHT
            or not isinstance(pixels, bytes) or len(pixels) != (width*height+1)//2):
        raise ValueError('Invalid packed menu sprite')
    x0, y0 = WIDTH-width-4, (HEIGHT-height)//2
    columns = []
    for pair in range(x0//2, (x0+width-1)//2+1):
        data, mask = bytearray(height), 0
        for side in (0, 1):
            x = pair*2+side-x0
            if not 0 <= x < width:
                continue
            shift = 4 if side == 0 else 0
            mask |= 15 << shift
            for y in range(height):
                index = y*width+x
                level = (pixels[index//2] >> (0 if index & 1 else 4)) & 15
                data[y] |= level << shift
        columns.append((pair*HEIGHT+y0, mask, bytes(data)))
    return tuple(columns)


def _sprite_label(label, pixels):
    size, end = 0, 0
    for end, char in enumerate(label, 1):
        size += 8 if char == '©' else 6
        if size > pixels:
            return label[:end-1]
    return label


class Frame:
    def __init__(self):
        # identical column-major memory representation as v1.3
        self.raw = bytearray(RAW_LEN)

    def pixel(self, x: int, y: int, level: int = 15):
        if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
            return
        i = (x // 2) * HEIGHT + y
        shift = 4 if (x & 1) == 0 else 0
        self.raw[i] = (self.raw[i] & ~(0xF << shift)) | ((level & 0xF) << shift)

    def get_pixel(self, x, y):
        assert 0 <= x < WIDTH and 0 <= y < HEIGHT
        i = (x // 2) * HEIGHT + y
        return (self.raw[i] >> (4 if not x % 2 else 0)) & 0xF

    def text(self, x, y, chars, level=15):
        if 0 <= x < WIDTH and 0 <= y <= HEIGHT-7:
            # At most 43 glyphs fit. Never retain an unbounded external string
            # as a cache key; clipping, © width and every grey level stay exact.
            end=x; count=0
            for c in chars:
                width=7 if c == '©' else 5
                if end+width > WIDTH:
                    break
                count += 1; end += width+1
            prefix=chars[:count]
            base=(x//2)*HEIGHT+y
            for offset, mask, value in _text_pattern(prefix, level & 15, x & 1):
                i=base+offset
                self.raw[i]=(self.raw[i] & ~mask) | value
            return
        # Preserve old glyphs; use adapted supplements for accents.
        for c in chars:
            glyph = FONT.get(c, M11_FONT.get(c, FONT["?"]))
            width = 7 if c == "©" else 5
            if x + width > WIDTH:
                break
            for dy, bits in enumerate(glyph):
                for dx in range(width):
                    if bits & (1 << (width-1-dx)):
                        self.pixel(x + dx, y + dy, level)
            x += width + 1

    def header(self, title=TITLE):
        self.raw[:] = _header_pattern(title[:44])

    def status(self, upper, lower, header=TITLE):
        self.header(header)
        self.text(4, 23, upper)
        self.text(4, 41, lower)
        return self

    def menu(self, title, items, selected=0, keep_back_visible=True, header=TITLE):
        self.header(header)
        self.text(4, 14, title)
        if not items:
            return self
        selected = max(0, min(int(selected), len(items)-1))
        # In the UI patch Back has index 0 and stays in the first row during scroll.
        if len(items) <= 4:
            visible = list(range(len(items)))
        elif keep_back_visible:
            if selected <= 3:
                visible = [0,1,2,3]
            else:
                visible = [0] + list(range(max(1, selected-2), selected+1))
        else:
            first = max(0, selected-3)
            visible = list(range(first, min(first+4,len(items))))
        # Stock-style left line and moving triangle, no highlight rectangle.
        for y in range(24, 63):
            self.pixel(9,y,7)
        for row, idx in enumerate(visible[:4]):
            y = 23 + row * 10
            self.text(20, y+1, items[idx],15)
            if idx == selected:
                # Exact 9-pixel stock-style arrow outline from exported UI patch.
                for dy in range(9):
                    ay = y + 1 + dy
                    x = 9 + min(dy, 8-dy)
                    if 0 < dy < 8: self.pixel(9, ay, 0)
                    self.pixel(x, ay, 15)
        return self

    def progress(self, phase, description, pct, header=TITLE):
        pct = min(100,max(0,int(pct)))
        self.header(header)
        self.text(4, 17, phase)
        self.text(4, 30, description)
        for y in range(45,58):
            for x in range(4,252):
                border = y in (45,57) or x in (4,251)
                if border or x < 5 + 246*pct//100:
                    self.pixel(x,y,8 if border else 15)
        return self

    def original_sprite(self, sprite):
        if sprite is not None:
            for offset, mask, data in _sprite_pattern(sprite):
                if mask == 255:
                    self.raw[offset:offset+len(data)] = data
                else:
                    for y, value in enumerate(data):
                        index = offset+y
                        self.raw[index] = (self.raw[index] & (255^mask)) | value
        return self

    def menu_full(self, items, selected=0, keep_back_visible=True, sprite=None):
        """Six rows across the complete panel; no branding or title band."""
        self.raw[:] = bytes(RAW_LEN)
        if not items:
            return self
        selected = max(0, min(int(selected), len(items)-1))
        if len(items) <= 6 or selected < 6:
            visible = list(range(min(6, len(items))))
        elif keep_back_visible:
            visible = [0] + list(range(selected-4, selected+1))
        else:
            visible = list(range(selected-5, selected+1))
        for y in range(1, 63):
            self.pixel(9, y, 7)
        for row, idx in enumerate(visible):
            y = 1 + row*10
            label = items[idx]
            if sprite is not None:
                label = _sprite_label(label, WIDTH-sprite[0]-4-20-6)
            self.text(20, y+1, label, 15)
            if idx == selected:
                for dy in range(9):
                    if 0 < dy < 8:
                        self.pixel(9, y+dy, 0)
                    self.pixel(9+min(dy, 8-dy), y+dy, 15)
        return self.original_sprite(sprite)

    def dialog(self, title, message):
        # Acknowledgement only: clicking Back cannot repeat the rejected action.
        import textwrap
        body = textwrap.wrap(' '.join(str(message).split())[:240], 38,
                             max_lines=4, placeholder='...')
        return self.menu_full(['Back', str(title)[:38]] + body, 0)

    def notice(self, upper, lower):
        self.raw[:] = bytes(RAW_LEN)
        self.text(4, 16, upper[:41])
        self.text(4, 39, lower[:41])
        return self

    def wire_bytes(self):
        # SSD1322 0x5C stream: 64 rows x 128 bytes per row.
        # WARNING: writing self.raw directly produces distorted image!
        # Transpose with 64 bounded C-level slices, preserving every nibble.
        # Avoid 8192 Python generator iterations on the Orange Pi CPU.
        output = bytearray(RAW_LEN)
        for y in range(HEIGHT):
            output[y*128:(y+1)*128] = self.raw[y::HEIGHT]
        return bytes(output)

    def to_image(self, scale=4):
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError('Pillow required for PNG preview; wire_bytes needs no third-party packages') from exc
        palette=[(2,6,16),(3,11,21),(3,15,26),(4,20,35),
                 (5,27,45),(8,57,95),(10,67,108),(12,88,142),
                 (13,97,154),(14,107,168),(15,117,183),(16,129,203),
                 (18,140,220),(20,151,235),(21,157,245),(22,161,254)]
        img=Image.new('RGB',(WIDTH,HEIGHT),(2,6,16))
        px=img.load()
        for y in range(HEIGHT):
            for x in range(WIDTH):
                px[x,y]=palette[self.get_pixel(x,y)]
        return img.resize((WIDTH*scale,HEIGHT*scale), Image.Resampling.NEAREST)

