# SPDX-License-Identifier: GPL-3.0-or-later
"""Klipper's real default graphics screen, rendered into the private M300 OLED.

DisplayGroup/Jinja, font, glyphs, text and XOR progress rendering are upstream.
DisplayBase is memory-only here: no SPI/GPIO/encoder object is constructed.
The native 128x64 bitmap expands horizontally 2:1 onto the 256x64 SSD1322.
"""
from .display.display import lookup_display_templates, PrinterLCD
from .display.uc1701 import DisplayBase

_BIT_PLANES = tuple(bytes(255 if value & (1 << bit) else 0
                         for value in range(256)) for bit in range(8))


class KlipperStatus:
    group_name = '_default_16x4'
    draw_text = PrinterLCD.draw_text
    draw_progress_bar = PrinterLCD.draw_progress_bar

    def __init__(self, config):
        templates = lookup_display_templates(config)
        self.display_templates = templates.get_display_templates()
        self.group = templates.get_display_data_groups()[self.group_name]
        self.lcd_chip = DisplayBase(self)
        self.lcd_chip.set_glyphs(templates.get_display_glyphs())
        self._previous = self._wire = None
        self.changed = False

    @staticmethod
    def send(*args, **kwargs):
        raise RuntimeError('M300 native status is a memory-only renderer')

    def render(self, eventtime):
        self.lcd_chip.clear()
        self.group.show(self, self.display_templates, eventtime)
        pages = tuple(bytes(page) for page in self.lcd_chip.vram)
        self.changed = pages != self._previous
        if self.changed:
            # One source pixel maps to two adjacent 4-bit pixels: 0x00/0xff.
            # The original native bitmap and placements are not rearranged.
            self._wire = b''.join(page.translate(table)
                                  for page in pages for table in _BIT_PLANES)
            self._previous = pages
        return self._wire


def load_config(config):
    return KlipperStatus(config)
