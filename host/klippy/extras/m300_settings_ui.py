# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded original-font OLED menu composition, no actions."""
from functools import lru_cache

from .m300_leveling_oem import draw_sprite, draw_text, width
from .m300_ui_m11_state import fit_label

SPRITE_LABEL_PIXELS = 174
MENU_LABEL_PIXELS = 232
BRIGHTNESS_BAR_PITCH = 10
BRIGHTNESS_BAR_WIDTH = 8


def menu_label_pixels(sprite):
    return MENU_LABEL_PIXELS if sprite is None else SPRITE_LABEL_PIXELS - max(0, sprite[0] - 50)


@lru_cache(maxsize=64)
def menu_frame(labels, active, selected, frame_type, sprite=None):
    frame = frame_type()
    if not labels:
        return frame.wire_bytes()
    selected = max(0, min(int(selected), len(labels)-1))
    has_back = labels[0] == 'Back'
    if selected < 5:
        visible = list(range(min(5, len(labels))))
    elif has_back:
        visible = [0] + list(range(selected-3, selected+1))
    else:
        visible = list(range(selected-4, selected+1))
    center = visible.index(selected)*12+7
    for y in range(64):
        if abs(y-center) > 2:
            frame.pixel(8, y)
    direction = -1 if has_back and selected == 0 else 1
    for dy in range(-2, 3):
        frame.pixel(8+direction*(3-abs(dy)), center+dy)
    for row, index in enumerate(visible):
        x = 16 if has_back and index == 0 else 20
        y = row*12
        active_row = index in active
        pixels = menu_label_pixels(sprite)
        if active_row:
            pixels -= width('<')+4
        label = labels[index]
        if width(label) > pixels:
            label = fit_label(label, pixels)
        draw_text(frame, x, y, label)
        if active_row:
            draw_text(frame, x+width(label)+4, y+1, '<')
    if sprite is not None:
        draw_sprite(frame, sprite)
    return frame.wire_bytes()


@lru_cache(maxsize=64)
def brightness_frame(title, level, back, frame_type, sprite=None):
    frame = frame_type()
    draw_text(frame, 16, 0, title)
    draw_text(frame, 16, 14, 'Turn to adjust')
    draw_text(frame, 16, 27, 'Press to go back' if back else 'Press to save')
    draw_text(frame, 16, 40, 'Hold to go back')
    for segment in range(16):
        left = 16 + BRIGHTNESS_BAR_PITCH * segment
        for x in range(left, left + BRIGHTNESS_BAR_WIDTH):
            for y in range(55, 63):
                if segment < level or x in (left, left + BRIGHTNESS_BAR_WIDTH-1) or y in (55, 62):
                    frame.pixel(x, y, 15 if segment < level else 5)
    if sprite is not None:
        # The real sixteen-segment control is on the left. Hide the draft
        # icon's demonstration meter so the screen has only one value bar.
        w,h,raw=sprite
        draw_sprite(frame,(w,h,raw[:43*(w//2)]+bytes((h-43)*(w//2))))
    return frame.wire_bytes()


@lru_cache(maxsize=64)
def temperature_frame(title, value, lower, upper, back, frame_type, sprite=None):
    """Native-pixel draft editor. Numeric value and icon have disjoint areas."""
    if not (type(value) is int and lower <= value <= upper):
        raise ValueError('Temperature draft outside its visible range')
    frame = frame_type()
    draw_text(frame, 16, 0, title)
    draw_text(frame, 16, 14, '%d-%d°C / 1°C' % (lower, upper))
    draw_text(frame, 16, 27, 'Press to go back' if back else 'Press to heat')
    draw_text(frame, 16, 40, 'Hold to go back')
    # Same 16-segment geometry as brightness. The number, not the coarse bar,
    # is the exact temperature; a single-value range is shown fully filled.
    filled = (16 if upper == lower else
              (16 * (value - lower) + (upper - lower) // 2) // (upper - lower))
    for segment in range(16):
        left = 16 + BRIGHTNESS_BAR_PITCH * segment
        for x in range(left, left + BRIGHTNESS_BAR_WIDTH):
            for y in range(55, 63):
                if segment < filled or x in (left, left + BRIGHTNESS_BAR_WIDTH-1) or y in (55, 62):
                    frame.pixel(x, y, 15 if segment < filled else 5)
    if sprite is not None:
        w, h, raw = sprite
        if (w, h, len(raw)) != (50, 50, 1250):
            raise ValueError('Temperature editor requires a native 50x50 icon')
        # Keep every original nibble; move only the icon's origin to (200,0).
        # Text below it begins at y=51 and uses the remaining 13 pixel rows.
        for column in range(25):
            offset = (100 + column) * 64
            frame.raw[offset:offset + 50] = raw[column::25]
    label = '%d°C' % value
    draw_text(frame, 200 + max(0, (50 - width(label)) // 2), 51, label)
    return frame.wire_bytes()


def notice_frame(title, message, frame_type, sprite=None):
    rows = ['Back', title]
    pixels = menu_label_pixels(sprite)
    for _ in range(2):
        if width(message) <= pixels:
            break
        line = fit_label(message, pixels)
        prefix, separator, _ = line.rpartition(' ')
        if separator and prefix:
            line = prefix
        rows.append(line)
        message = message[len(line):].lstrip()
    if width(message) > pixels:
        message = fit_label(message, pixels-width(' ...')-1).rstrip() + ' ...'
    rows.append(message)
    return menu_frame(tuple(rows), (), 0, frame_type, sprite)
