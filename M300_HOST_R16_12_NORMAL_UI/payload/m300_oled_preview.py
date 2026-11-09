# SPDX-License-Identifier: GPL-3.0-or-later
"""Low-latency, read-only mirror of a host-rendered M300 SSD1322 OLED frame.

The previous ACK-frame source added whole-frame transfer latency before the
Fluidd preview could respond to knob rotation. Observe the already-rendered
`_render_wire` instead, with no MCU readback, no changes to the verified
DMA/RLE/UART/SPI/ACK transport and no additional display rendering.

The preview may lead the physical OLED by its transport delay; it is not a
claim that the MCU has ACKed or actually displayed that image. Only the
physical OLED's original consent/encoder rules govern printer actions.
"""
import base64
import math
import struct
import zlib

WIDTH, HEIGHT = 256, 64
WIRE_BYTES = WIDTH * HEIGHT // 2
MIN_INTERVAL = .125  # Up to 8/s on faster status clients; Moonraker usually polls at 4/s.
PNG_HEADER = b'\x89PNG\r\n\x1a\n'
# Same luminance palette as m300_oled_render.Frame.to_image; 0..15 in order.
PALETTE = ((2, 6, 16), (3, 11, 21), (3, 15, 26), (4, 20, 35),
           (5, 27, 45), (8, 57, 95), (10, 67, 108), (12, 88, 142),
           (13, 97, 154), (14, 107, 168), (15, 117, 183),
           (16, 129, 203), (18, 140, 220), (20, 151, 235),
           (21, 157, 245), (22, 161, 254))


def _chunk(name, data):
    return (struct.pack('>I', len(data)) + name + data
            + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff))


def encoded_png(wire):
    """Package unchanged row-major 4bpp nibbles as an indexed 4-bit PNG."""
    if type(wire) is not bytes or len(wire) != WIRE_BYTES:
        raise ValueError('M300 OLED preview requires exactly 8192 acknowledged bytes')
    ihdr = struct.pack('>IIBBBBB', WIDTH, HEIGHT, 4, 3, 0, 0, 0)
    palette = bytes(channel for rgb in PALETTE for channel in rgb)
    stride = WIDTH // 2
    scanlines = b''.join(b'\0' + wire[y*stride:(y+1)*stride]
                         for y in range(HEIGHT))
    return (PNG_HEADER + _chunk(b'IHDR', ihdr) + _chunk(b'PLTE', palette)
            + _chunk(b'IDAT', zlib.compress(scanlines, 1))
            + _chunk(b'IEND', b''))


class M300OLEDPreview:
    def __init__(self):
        self._wire = None
        self._image = ''
        self._next_at = 0.
        self._sequence = 0

    def reset(self):
        self._wire = None
        self._image = ''
        self._next_at = 0.
        self._sequence += 1

    def get_status(self, now, online, rendered):
        ready = (online is True and type(rendered) is bytes
                 and len(rendered) == WIRE_BYTES
                 and type(now) in (int, float) and math.isfinite(now))
        if ready and (not self._image or now >= self._next_at):
            # Never enqueue frames: discard superseded images and encode only
            # the latest renderer output when the status client asks for it.
            if rendered != self._wire:
                self._image = base64.b64encode(encoded_png(rendered)).decode('ascii')
                self._wire = rendered
                self._sequence += 1
                self._next_at = now + MIN_INTERVAL
        # Hide the cached image as soon as Klipper or the MCU link is offline.
        is_visible = ready and bool(self._image)
        return {'online': bool(is_visible), 'sequence': self._sequence,
                'width': WIDTH, 'height': HEIGHT, 'format': 'indexed4-png',
                'source': 'host-rendered', 'image_base64': self._image if is_visible else ''}
