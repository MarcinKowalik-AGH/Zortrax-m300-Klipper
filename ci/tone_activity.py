#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lossless native 4bpp row encoder shared by both MCU asset exporters."""

def indexed_rows(raws, prefix):
    """Deduplicate and RLE native 4bpp scanlines in flash, never quantizing tones.

    Each token contains (run_length-1) in its high nibble and the unchanged
    luminance in its low nibble. Direct uint16 offsets avoid a second index
    table. Each row decodes to exactly 50 pixels, at most 50 tokens.
    """
    stream, seen, frames = bytearray(), {}, []
    for bank in raws:
        indices = []
        if len(bank) != 4:
            raise ValueError('Expected four 500ms animation frames')
        for frame in bank:
            if len(frame) != 1250:
                raise ValueError('Expected native 50x50 4bpp')
            frame_ids = []
            for y in range(50):
                row = frame[y*25:(y+1)*25]
                if row not in seen:
                    seen[row] = len(stream)
                    pixels = [level for b in row for level in (b >> 4, b & 15)]
                    x = 0
                    while x < 50:
                        count = 1
                        while x+count < 50 and count < 16 and pixels[x+count] == pixels[x]:
                            count += 1
                        stream.append(((count-1) << 4) | pixels[x])
                        x += count
                frame_ids.append(seen[row])
            indices.append(frame_ids)
        frames.append(indices)
    if len(stream) >= 65536:
        raise ValueError('Flash row offsets do not fit uint16_t')
    lines = ['/* Generated exact 4bpp row RLE: high nibble count-1, low nibble tone. */',
             'static const uint8_t %s_rle[%d] = {' % (prefix,len(stream))]
    lines += ['    '+','.join('0x%02x'%v for v in stream[i:i+20])+','
              for i in range(0,len(stream),20)]
    lines += ['};', 'static const uint16_t %s_frames[%d][4][50] = {' % (prefix,len(frames))]
    for bank in frames:
        lines.append('  {')
        lines += ['    {'+','.join(map(str,row_ids))+'},' for row_ids in bank]
        lines.append('  },')
    return '\n'.join(lines+['};',''])
