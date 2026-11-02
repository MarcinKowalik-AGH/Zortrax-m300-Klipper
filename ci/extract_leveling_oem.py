"""Reproduce the M07 text/font manifest from the operator-supplied OEM dump.

The application and initialized RAM are inputs, never release payloads. This
extractor needs no disassembler and refuses a different application revision.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct

STOCK_SHA256 = '11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75'
BASE = 0x08008000
LANGUAGES = ('EN', 'PL', 'FR', 'DE', 'ES')


def extract(application, ram):
    assert hashlib.sha256(application).hexdigest() == STOCK_SHA256
    def word(address):
        return struct.unpack_from('<I', application, address-BASE)[0]
    def string(address):
        start = address-BASE
        end = application.index(b'\0', start)
        return application[start:end].decode('utf-8')
    texts = {}
    for index in (16, 19, 20, 21, 22, 105, 108, *range(123, 143)):
        table = 0x0801afd0 + index*20
        texts[str(index)] = {'table': hex(table), 'languages': {
            lang: string(word(table+4*i)) for i, lang in enumerate(LANGUAGES)}}
    descriptors = {}
    for address in (0x08021c60, 0x08021d38,
                    *range(0x08021db0, 0x08021e58, 12),
                    0x08021ea0, 0x08021eac, 0x08021eb8, 0x08021ec4):
        table, flags, sprite = (word(address+i) for i in (0, 4, 8))
        text_id = (table-0x0801afd0)//20
        assert str(text_id) in texts
        descriptors[hex(address)] = dict(text_id=text_id, flags=flags, sprite=hex(sprite))
    glyphs = []
    for index in range(388):
        address = struct.unpack_from('<I', ram, 0xfa0+4*index)[0]
        start = address-BASE
        encoded = int.from_bytes(application[start:start+2], 'big')
        width = application[start+2]
        assert 0 <= width <= 12
        bands = (width+7)//8 if width else 1
        data = application[start+4:start+4+bands*13]
        glyphs.append(dict(address=hex(address), encoded=encoded, width=width,
                           bitmap_b64=base64.b64encode(data).decode()))
    return dict(source_sha256=STOCK_SHA256,
                initialized_ram_sha256=hashlib.sha256(ram).hexdigest(),
                glyph_table='0x20000fa0', glyph_height=13, line_advance=12,
                dialog_box=[0, 0, 192, 60], sprite_origin=[200, 7],
                texts=texts, descriptors=descriptors, glyphs=glyphs)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('application', type=Path)
    p.add_argument('ram', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    a.output.write_text(json.dumps(extract(a.application.read_bytes(), a.ram.read_bytes()),
                                   ensure_ascii=False, indent=2)+'\n')
