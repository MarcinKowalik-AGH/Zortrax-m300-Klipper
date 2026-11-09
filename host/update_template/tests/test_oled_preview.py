"""Read-only low-latency host-rendered OLED preview, 4bpp PNG fidelity and bounds."""
import base64
import struct
import unittest
import zlib

from test_settings_information import session

from payload.m300_oled_preview import (M300OLEDPreview, WIDTH, HEIGHT,
                                       WIRE_BYTES, PNG_HEADER, PALETTE,
                                       encoded_png)


def decode_png(data):
    assert data.startswith(PNG_HEADER)
    i, parts = len(PNG_HEADER), {}
    while i < len(data):
        count = struct.unpack_from('>I', data, i)[0]
        name = data[i+4:i+8]
        value = data[i+8:i+8+count]
        checksum = struct.unpack_from('>I', data, i+8+count)[0]
        assert checksum == (zlib.crc32(name + value) & 0xffffffff)
        parts[name] = value
        i += 12 + count
    return parts


class OLEDPreviewTests(unittest.TestCase):
    def test_indexed_png_uses_exact_nibbles_palette_and_dimensions(self):
        raw = bytes(range(256)) * 32
        self.assertEqual(len(raw), WIRE_BYTES)
        png = encoded_png(raw)
        parts = decode_png(png)
        self.assertEqual(struct.unpack('>IIBBBBB', parts[b'IHDR']),
                         (WIDTH, HEIGHT, 4, 3, 0, 0, 0))
        self.assertEqual(len(parts[b'PLTE']), 16*3)
        self.assertEqual(tuple(tuple(parts[b'PLTE'][i:i+3])
                               for i in range(0, 48, 3)), PALETTE)
        scan = zlib.decompress(parts[b'IDAT'])
        self.assertEqual(len(scan), HEIGHT * (WIDTH//2+1))
        self.assertEqual(b''.join(scan[y*129+1:(y+1)*129]
                                  for y in range(HEIGHT)), raw)
        self.assertEqual(parts[b'IEND'], b'')

    def test_specific_three_tone_klipper_gray_pixels_survive_without_quantization(self):
        raw = bytearray(WIRE_BYTES)
        raw[7*128+3] = 0x7b
        raw[7*128+4] = 0xf0
        parts = decode_png(encoded_png(bytes(raw)))
        row = zlib.decompress(parts[b'IDAT'])[7*129:8*129]
        self.assertEqual(row[4:6], b'\x7b\xf0')

    def test_latest_host_rendered_frame_is_exposed_without_ack_wait(self):
        preview = M300OLEDPreview()
        missing = preview.get_status(10., True, None)
        self.assertFalse(missing['online'])
        self.assertEqual(missing['image_base64'], '')
        raw = bytes(WIRE_BYTES)
        latest = preview.get_status(10., True, raw)
        self.assertTrue(latest['online'])
        self.assertEqual(latest['format'], 'indexed4-png')
        self.assertEqual(latest['source'], 'host-rendered')
        self.assertEqual(latest['sequence'], 1)
        png = base64.b64decode(latest['image_base64'], validate=True)
        self.assertEqual(decode_png(png)[b'IHDR'][:8],
                         struct.pack('>II', WIDTH, HEIGHT))

    def test_changed_frames_coalesce_and_publish_without_old_500ms_lag(self):
        preview = M300OLEDPreview()
        frame1 = bytes(WIRE_BYTES)
        frame2 = bytes([0xf0]) * WIRE_BYTES
        first = preview.get_status(20., True, frame1)
        # A 125ms upstream status cadence sees changes without a 500ms wait.
        # It still coalesces bursts faster than that rate.
        duplicate = preview.get_status(20.05, True, frame2)
        self.assertEqual(duplicate['sequence'], first['sequence'])
        self.assertEqual(duplicate['image_base64'], first['image_base64'])
        changed = preview.get_status(20.125, True, frame2)
        self.assertEqual(changed['sequence'], first['sequence']+1)
        self.assertNotEqual(changed['image_base64'], first['image_base64'])
        self.assertEqual(preview.get_status(20.2, True, frame2)['sequence'],
                         changed['sequence'])

    def test_rapid_knob_frames_are_coalesced_into_latest_snapshot(self):
        from unittest.mock import patch
        preview = M300OLEDPreview()
        def frame(n):
            return bytes([n]) * WIRE_BYTES
        with patch('payload.m300_oled_preview.encoded_png',
                   wraps=encoded_png) as encoder:
            first = preview.get_status(4., True, frame(1))
            for i in range(2, 22):
                new = preview.get_status(4.+i*.003, True, frame(i))
                self.assertEqual(new['sequence'], first['sequence'])
            result = preview.get_status(4.13, True, frame(31))
            self.assertEqual(result['sequence'], first['sequence']+1)
            self.assertEqual(encoder.call_count, 2)
            png = base64.b64decode(result['image_base64'], validate=True)
            rows = zlib.decompress(decode_png(png)[b'IDAT'])
            self.assertEqual(rows[1:129], bytes([31]) * 128)

    def test_disconnect_suppresses_old_rendered_image_and_reset_invalidates(self):
        preview = M300OLEDPreview()
        raw = bytes(WIRE_BYTES)
        before = preview.get_status(1., True, raw)
        disconnected = preview.get_status(1.1, False, raw)
        self.assertFalse(disconnected['online'])
        self.assertEqual(disconnected['image_base64'], '')
        preview.reset()
        self.assertFalse(preview.get_status(1.2, True, None)['online'])
        fresh = preview.get_status(1.3, True, raw)
        self.assertGreater(fresh['sequence'], before['sequence'])
        self.assertTrue(fresh['online'])

    def test_host_menu_logo_animation_renders_complete_sprite_each_phase(self):
        # The full host-rendered frame is the same source used by physical OLED
        # and the browser. No animated bitmap may disappear in one phase.
        with session() as h:
            h.menu.page = 'main'
            h.oled.page = 'm04'
            rows = h.oled._rows(h.now)[1]
            labels = [label for label, _ in rows]
            self.assertEqual(labels[0], 'Back')
            self.assertIn('Klipper', labels)
            h.oled.selection = labels.index('Klipper')
            icons = []
            for phase in range(4):
                h.oled._render(h.now + phase * .5)
                wire = h.oled._render_wire
                self.assertEqual(len(wire), WIRE_BYTES)
                right = b''.join(
                    wire[(7 + y) * 128 + 100:(7 + y) * 128 + 125]
                    for y in range(50))
                ink = sum(int(pixel >> 4 != 0) + int(pixel & 15 != 0)
                          for pixel in right)
                self.assertGreater(ink, 60)
                icons.append(right)
            self.assertGreaterEqual(len(set(icons)), 3)

    def test_host_cartesian_homing_animation_is_never_an_empty_region(self):
        with session() as h:
            h.menu.page = 'maintenance'
            h.oled.page = 'm04'
            labels = [label for label, _ in h.oled._rows(h.now)[1]]
            h.oled.selection = labels.index('Home X')
            frames = []
            for phase in range(4):
                h.oled._render(h.now + phase * .5)
                wire = h.oled._render_wire
                self.assertEqual(len(wire), WIRE_BYTES)
                right = b''.join(
                    wire[(7 + y) * 128 + 100:(7 + y) * 128 + 125]
                    for y in range(50))
                ink = sum(int(pixel >> 4 != 0) + int(pixel & 15 != 0)
                          for pixel in right)
                self.assertGreater(ink, 60)
                frames.append(right)
            self.assertGreaterEqual(len(set(frames)), 2)

    def test_invalid_frame_or_time_never_exposes_untrusted_image(self):
        preview = M300OLEDPreview()
        for data in (None, b'', b'\x00'*(WIRE_BYTES-1), b'\0'*(WIRE_BYTES+1),
                     bytearray(WIRE_BYTES)):
            self.assertFalse(preview.get_status(1., True, data)['online'])
        self.assertFalse(preview.get_status(float('nan'), True,
                                            bytes(WIRE_BYTES))['online'])
        with self.assertRaisesRegex(ValueError, '8192'):
            encoded_png(bytes(WIRE_BYTES-1))


if __name__ == '__main__':
    unittest.main()
