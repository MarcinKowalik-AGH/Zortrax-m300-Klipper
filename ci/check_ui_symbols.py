#!/usr/bin/env python3
"""Validate committed OLED artwork without raster libraries or printer access."""
import hashlib
import base64
import json
from pathlib import Path
import re
import struct
import unittest
import xml.etree.ElementTree as ET
import zipfile
import zlib

from render_ui_symbols import OUT, SYMBOLS, MCU_FRAMES, HOST_FRAMES, drawing, frame_svg


def gif_frames(data):
    """Read GIF blocks; do not mistake compressed bytes for frame markers."""
    if data[:6] not in (b'GIF87a', b'GIF89a'):
        raise ValueError('Invalid GIF header')
    flags = data[10]
    offset = 13 + (3 * (2 << (flags & 7)) if flags & 128 else 0)
    durations = []
    delay = None

    def subblocks(at):
        while data[at]:
            at += data[at]+1
        return at+1

    while data[offset] != 0x3b:
        kind = data[offset]
        offset += 1
        if kind == 0x21:
            label = data[offset]
            offset += 1
            if label == 0xf9:
                delay = struct.unpack_from('<H', data, offset+2)[0]*10
            offset = subblocks(offset)
        elif kind == 0x2c:
            flags = data[offset+8]
            offset += 9 + (3 * (2 << (flags & 7)) if flags & 128 else 0)
            offset = subblocks(offset+1)  # LZW minimum size, then image subblocks
            durations.append(delay)
        else:
            raise ValueError('Invalid GIF block')
    return durations


class ArtworkContracts(unittest.TestCase):
    def test_project_menu_marks_have_native_frames_and_matching_animation_exports(self):
        folder=OUT.parent/'menu-symbols'
        spec=json.loads((HOST_FRAMES.parent/'m300_menu_sprites.json').read_text())
        self.assertEqual(set(spec['symbols']),{'project-klipper','project-zortrax','homing-xy','homing-z','homing-all'})
        for name,record in spec['symbols'].items():
            self.assertEqual((record['width'],record['height'],record['frame_ms']),(50,50,500))
            frames=[zlib.decompress(base64.b64decode(f['zlib_b64'])) for f in record['frames']]
            self.assertEqual(len(set(frames)),4)
            for index,(raw,frame) in enumerate(zip(frames,record['frames'])):
                self.assertEqual(len(raw),1250)
                self.assertEqual(hashlib.sha256(raw).hexdigest(),frame['sha256'])
                self.assertLessEqual(set(raw),{0,15,240,255})
                svg=ET.fromstring((folder/('%s_%d.svg'%(name,index))).read_text())
                self.assertEqual((svg.get('width'),svg.get('height')),('50','50'))
                png=(folder/('%s_%d.png'%(name,index))).read_bytes()
                self.assertEqual(struct.unpack_from('>II',png,16),(50,50))
            self.assertEqual(gif_frames((folder/(name+'.gif')).read_bytes()),[500]*4)

    def test_all_symbols_have_four_distinct_native_frames(self):
        catalog = json.loads((OUT/'catalog.json').read_text())
        bank = json.loads((OUT/'native_frames.json').read_text())
        self.assertEqual(len(catalog), 24)
        self.assertEqual(set(bank['symbols']), {entry[0] for entry in SYMBOLS})
        self.assertEqual({item['id'] for item in catalog if item['runtime_enabled']},
                         {entry[0] for entry in SYMBOLS})
        runtime = json.loads(HOST_FRAMES.read_text())
        for name, _, _ in SYMBOLS:
            with self.subTest(name=name):
                record = bank['symbols'][name]
                host_frames = runtime['symbols'][name]['frames']
                self.assertEqual([zlib.decompress(base64.b64decode(frame['zlib_b64'])).hex()
                                  for frame in host_frames], record['frames'])
                self.assertEqual(len(set(record['frames'])), 4)
                for raw, checksum in zip(record['frames'], record['sha256']):
                    packed = bytes.fromhex(raw)
                    self.assertEqual(len(packed), 1250)
                    levels = {v for b in packed for v in (b >> 4, b & 15)}
                    self.assertTrue({0, 15}.issubset(levels))
                    self.assertTrue(any(0 < level < 15 for level in levels))
                    self.assertEqual(hashlib.sha256(packed).hexdigest(), checksum)
                svg = ET.fromstring((OUT/(name+'.svg')).read_text())
                animations = svg.findall('.//{http://www.w3.org/2000/svg}animate')
                self.assertEqual(len(animations), 4)
                self.assertTrue(all(a.get('calcMode') == 'discrete' and
                                    a.get('dur') == '2s' for a in animations))
                for frame in range(4):
                    ET.fromstring(frame_svg(name, frame))
                self.assertNotEqual(drawing(name, 0), drawing(name, 1))

    def test_mcu_flash_frames_match_downloadable_native_artwork(self):
        # Independent parsing: actual const flash lookup must reproduce EVERY
        # native pixel value, not just binary foreground membership.
        def parsed(source, prefix):
            body = re.search(prefix+r'_rle\[\d+\] = \{(.*?)\n\};',source,re.S)[1]
            stream = bytes(int(v,16) for v in re.findall(r'0x([0-9a-f]{2})',body))
            body = re.search(prefix+r'_frames\[\d+\]\[4\]\[50\] = \{(.*?)\n\};',source,re.S)[1]
            offsets = [int(v) for v in re.findall(r'\d+',body)]
            def decode(offset):
                pixels=[]
                while len(pixels)<50:
                    token=stream[offset]; offset+=1
                    pixels.extend([token&15]*((token>>4)+1))
                    self.assertLessEqual(len(pixels),50)
                return bytes((pixels[i]<<4)|pixels[i+1] for i in range(0,50,2))
            return decode, offsets
        bank = json.loads((OUT/'native_frames.json').read_text())
        error_spec = json.loads((HOST_FRAMES.parent/'m300_error_codes.json').read_text())
        error_names = list(dict.fromkeys(item['icon'] for item in error_spec['codes']+error_spec['native']))
        groups = [(MCU_FRAMES,'local_activity',['waiting_klipper','connection_lost']),
                  (MCU_FRAMES.with_name('m300_error_icons.inc'),'local_error',error_names)]
        for path,prefix,names in groups:
            decode,ids = parsed(path.read_text(),prefix)
            self.assertEqual(len(ids),len(names)*4*50)
            for index,name in enumerate(names):
                for frame in range(4):
                    expected = bytes.fromhex(bank['symbols'][name]['frames'][frame])
                    actual = b''.join(decode(i) for i in ids[(index*4+frame)*50:(index*4+frame+1)*50])
                    self.assertEqual(actual,expected,(name,frame))

    def test_download_has_all_animated_gifs_and_individual_frames(self):
        with zipfile.ZipFile(OUT/'M300_ACTIVITY_SYMBOLS_24.zip') as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(archive.namelist()), 24*6+2)
            for name, _, _ in SYMBOLS:
                self.assertEqual(archive.read('svg/'+name+'.svg'), (OUT/(name+'.svg')).read_bytes())
                gif = archive.read('gif/'+name+'.gif')
                self.assertEqual(struct.unpack_from('<HH', gif, 6), (50, 50))
                self.assertEqual(gif_frames(gif), [500]*4)
                for frame in range(4):
                    png = archive.read('frames/%s_%d.png' % (name, frame))
                    self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
                    self.assertEqual(struct.unpack_from('>II', png, 16), (50, 50))
            for filename in ('catalog.json', 'native_frames.json'):
                self.assertEqual(archive.read(filename), (OUT/filename).read_bytes())
        for prefix in ('preview', 'preview_additional'):
            self.assertEqual(gif_frames((OUT/(prefix+'.gif')).read_bytes()), [500]*4)


if __name__ == '__main__':
    unittest.main()
