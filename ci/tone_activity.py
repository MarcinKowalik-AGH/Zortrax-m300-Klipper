#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Authoring-only tonal edges for the existing binary 50x50 activity designs.

No imports from the printer runtime. The host only reads precomputed 4bpp
frames; this filter is never executed on menu navigation or on the MCU.
"""

def toned_image(image):
    from PIL import Image, ImageFilter
    if image.size != (50, 50) or image.mode != 'L':
        raise ValueError('Expected a native 50x50 grayscale input')
    if set(image.tobytes()) - {0, 255}:
        raise ValueError('Refuse to re-filter an already toned source')
    big = image.resize((400, 400), Image.Resampling.NEAREST)
    big = big.filter(ImageFilter.MaxFilter(3))
    big = big.filter(ImageFilter.GaussianBlur(radius=0.9))
    sampled = big.resize((50, 50), Image.Resampling.BOX)
    tones = []
    for old, value in zip(image.tobytes(), sampled.tobytes()):
        v = value / 255.0
        if old:
            tone = 15 if v >= 0.82 else 12 if v >= 0.58 else 9
        else:
            tone = (0 if v < 0.10 else 2 if v < 0.22 else
                    4 if v < 0.38 else 6 if v < 0.52 else 8)
        tones.append(tone * 17)
    return Image.frombytes('L', (50, 50), bytes(tones))


def indexed_rows(raws, prefix):
    """Deduplicate 25-byte native 4bpp scanlines in const flash, not SRAM."""
    rows, seen, frames = [], {}, []
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
                    seen[row] = len(rows)
                    rows.append(row)
                frame_ids.append(seen[row])
            indices.append(frame_ids)
        frames.append(indices)
    if len(rows) >= 65536:
        raise ValueError('Flash row indices do not fit uint16_t')
    lines = ['/* Generated native 4bpp flash rows. No framebuffer or decoder. */',
             'static const uint8_t %s_rows[%d][25] = {' % (prefix, len(rows))]
    lines += ['    {' + ','.join('0x%02x' % v for v in row) + '},' for row in rows]
    lines += ['};', 'static const uint16_t %s_frames[%d][4][50] = {' % (prefix,len(frames))]
    for bank in frames:
        lines.append('  {')
        lines += ['    {' + ','.join(map(str, row_ids)) + '},' for row_ids in bank]
        lines.append('  },')
    return '\n'.join(lines + ['};', ''])
