"""Read-only OLED mirroring: ACK source, 4-bit PNG fidelity and 2 Hz bound."""
import base64
import struct
import unittest
import zlib

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

    def test_only_acknowledged_frame_is_exposed(self):
        preview = M300OLEDPreview()
        missing = preview.get_status(10., True, None)
        self.assertFalse(missing['online'])
        self.assertEqual(missing['image_base64'], '')
        raw = bytes(WIRE_BYTES)
        latest = preview.get_status(10., True, raw)
        self.assertTrue(latest['online'])
        self.assertEqual(latest['format'], 'indexed4-png')
        self.assertEqual(latest['sequence'], 1)
        png = base64.b64decode(latest['image_base64'], validate=True)
        self.assertEqual(decode_png(png)[b'IHDR'][:8],
                         struct.pack('>II', WIDTH, HEIGHT))

    def test_changed_frames_are_throttled_to_two_hz_without_timer_or_mcu_io(self):
        preview = M300OLEDPreview()
        frame1 = bytes(WIRE_BYTES)
        frame2 = bytes([0xf0]) * WIRE_BYTES
        first = preview.get_status(20., True, frame1)
        duplicate = preview.get_status(20.25, True, frame2)
        self.assertEqual(duplicate['sequence'], first['sequence'])
        self.assertEqual(duplicate['image_base64'], first['image_base64'])
        changed = preview.get_status(20.50, True, frame2)
        self.assertEqual(changed['sequence'], first['sequence']+1)
        self.assertNotEqual(changed['image_base64'], first['image_base64'])
        self.assertEqual(preview.get_status(21., True, frame2)['sequence'],
                         changed['sequence'])

    def test_disconnect_suppresses_old_acked_image_and_reset_invalidates(self):
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
