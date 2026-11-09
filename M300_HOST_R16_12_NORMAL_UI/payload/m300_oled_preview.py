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
import logging
import uuid
import struct
import zlib

WIDTH, HEIGHT = 256, 64
WIRE_BYTES = WIDTH * HEIGHT // 2
MIN_INTERVAL = .125  # Existing animation/status cadence is unchanged.
PREVIEW_REVISION = 'NAV-EVENT-1'
MAX_WAITERS = 8
WAIT_SECONDS = 10.
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
        raise ValueError('M300 OLED preview requires exactly 8192 rendered bytes')
    ihdr = struct.pack('>IIBBBBB', WIDTH, HEIGHT, 4, 3, 0, 0, 0)
    palette = bytes(channel for rgb in PALETTE for channel in rgb)
    stride = WIDTH // 2
    scanlines = b''.join(b'\0' + wire[y*stride:(y+1)*stride]
                         for y in range(HEIGHT))
    return (PNG_HEADER + _chunk(b'IHDR', ihdr) + _chunk(b'PLTE', palette)
            + _chunk(b'IDAT', zlib.compress(scanlines, 1))
            + _chunk(b'IEND', b''))


class M300OLEDPreview:
    """Read-only navigation events on Moonraker's existing authorized socket.

    An outstanding wait request completes on navigation, NOT on the periodic
    objects/query timer. This needs no new service, socket, nginx rule or
    Moonraker plugin. Each browser keeps one request outstanding. Between
    requests only the latest state is retained; there is no stale-frame queue.
    """
    def __init__(self):
        self._wire = None
        self._image = ''
        self._next_at = 0.
        self._sequence = 0
        self._epoch = uuid.uuid4().hex
        self._navigation = 0
        self._view = None
        self._owner = None
        self._waiters = {}
        self._bound = False
        self._bind_failed = False
        self._delivered = 0

    def bind(self, owner):
        self._owner = owner
        if self._bound or self._bind_failed:
            return
        web = owner.printer.lookup_object('webhooks', None)
        if web is None:
            return
        try:
            web.register_endpoint('m300/oled_preview/wait', self._wait)
            web.register_endpoint('m300/oled_preview/cancel_wait', self._cancel_wait)
            self._bound = True
        except Exception:
            self._bind_failed = True
            logging.exception('M300 optional OLED navigation API unavailable')

    def reset(self):
        self._wire = None
        self._image = ''
        self._next_at = 0.
        self._sequence += 1
        self._epoch = uuid.uuid4().hex
        self._view = None
        self._navigation += 1
        self._wake_waiters()

    def observe_navigation(self, owner, now, view):
        # Called after normal rendering; never render again or touch hardware.
        try:
            self._owner = owner
            if view != self._view:
                self._view = view
                self._navigation += 1
                self._wake_waiters()
        except Exception:
            logging.exception('M300 optional OLED navigation observer failed')

    def _wake_waiters(self):
        for complete, client in list(self._waiters.values()):
            complete.complete(not client.is_closed())

    @staticmethod
    def _valid(now, online, rendered):
        return (online is True and type(rendered) is bytes
                and len(rendered) == WIRE_BYTES
                and type(now) in (int, float) and math.isfinite(now))

    def _encode(self, now, rendered):
        if rendered != self._wire:
            self._image = base64.b64encode(encoded_png(rendered)).decode('ascii')
            self._wire = rendered
            self._sequence += 1
            self._next_at = now + MIN_INTERVAL

    def _status(self, ready):
        visible = ready and bool(self._image)
        return {'online': bool(visible), 'sequence': self._sequence,
                'width': WIDTH, 'height': HEIGHT, 'format': 'indexed4-png',
                'source': 'host-rendered', 'image_base64': self._image if visible else '',
                'epoch': self._epoch, 'navigation_revision': self._navigation,
                'navigation_api': PREVIEW_REVISION if self._bound else '',
                'navigation_waiters': len(self._waiters),
                'navigation_delivered': self._delivered}

    def get_status(self, now, online, rendered):
        ready = self._valid(now, online, rendered)
        if ready and (not self._image or now >= self._next_at):
            self._encode(now, rendered)
        return self._status(ready)

    def _snapshot(self):
        owner = self._owner
        if owner is None:
            return self._status(False)
        now = owner.reactor.monotonic()
        rendered = getattr(owner, '_render_wire', None)
        ready = self._valid(now, owner.connected and owner.stream.ready
                            and owner.stream.enabled, rendered)
        if ready:
            self._encode(now, rendered)  # Navigation bypasses MIN_INTERVAL.
        return self._status(ready)

    @staticmethod
    def _client_key(request):
        key = request.get_str('client')
        if not 1 <= len(key) <= 64 or not all(c.isalnum() or c in '-_' for c in key):
            raise request.error('Invalid OLED navigation client')
        return key

    def _wait(self, request):
        key = self._client_key(request)
        epoch = request.get_str('epoch', '')
        revision = request.get_int('navigation_revision', -1)
        if len(epoch) > 64 or revision < -1:
            raise request.error('Invalid OLED navigation cursor')
        if epoch != self._epoch or revision != self._navigation:
            self._delivered += 1
            request.send({'changed': True, 'frame': self._snapshot()})
            return
        if key in self._waiters:
            raise request.error('OLED navigation request already pending')
        if len(self._waiters) >= MAX_WAITERS:
            raise request.error('Too many OLED navigation clients')
        reactor = self._owner.reactor
        complete = reactor.completion()
        record = (complete, request.get_client_connection())
        self._waiters[key] = record
        try:
            changed = complete.wait(reactor.monotonic() + WAIT_SECONDS, False)
        finally:
            if self._waiters.get(key) is record:
                del self._waiters[key]
        if changed:
            self._delivered += 1
            request.send({'changed': True, 'frame': self._snapshot()})
        else:
            request.send({'changed': False})

    def _cancel_wait(self, request):
        key = self._client_key(request)
        record = self._waiters.get(key)
        matched = record is not None and record[1] is request.get_client_connection()
        if matched:
            record[0].complete(False)
        request.send({'cancelled': matched})
