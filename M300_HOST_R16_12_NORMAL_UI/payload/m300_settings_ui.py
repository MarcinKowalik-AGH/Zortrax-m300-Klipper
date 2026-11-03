# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded original-font OLED menu composition, no actions."""
from functools import lru_cache

from .m300_leveling_oem import draw_sprite, draw_text, width
from .m300_ui_m11_state import fit_label

SPRITE_LABEL_PIXELS = 174
MENU_LABEL_PIXELS = 232


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
        pixels = SPRITE_LABEL_PIXELS if sprite is not None else MENU_LABEL_PIXELS
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
def brightness_frame(title, level, back, frame_type):
    frame = frame_type()
    draw_text(frame, 16, 0, title)
    draw_text(frame, 16, 14, 'Turn to adjust')
    draw_text(frame, 16, 27, 'Press to go back' if back else 'Press to save')
    draw_text(frame, 16, 40, 'Hold to go back')
    for segment in range(16):
        left = 16 + 14 * segment
        for x in range(left, left + 12):
            for y in range(55, 63):
                if segment < level or x in (left, left + 11) or y in (55, 62):
                    frame.pixel(x, y, 15 if segment < level else 5)
    return frame.wire_bytes()


def notice_frame(title, message, frame_type):
    rows = ['Back', title]
    for _ in range(2):
        if width(message) <= MENU_LABEL_PIXELS:
            break
        line = fit_label(message, MENU_LABEL_PIXELS)
        prefix, separator, _ = line.rpartition(' ')
        if separator and prefix:
            line = prefix
        rows.append(line)
        message = message[len(line):].lstrip()
    if width(message) > MENU_LABEL_PIXELS:
        message = fit_label(message, MENU_LABEL_PIXELS-width(' ...')-1).rstrip() + ' ...'
    rows.append(message)
    return menu_frame(tuple(rows), (), 0, frame_type)
