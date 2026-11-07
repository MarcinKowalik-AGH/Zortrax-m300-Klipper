# SPDX-License-Identifier: GPL-3.0-or-later
"""Small status text scoped to the bottom strip of the native Klipper screen."""
from functools import lru_cache
import re
import textwrap

from .m300_oled_render import Frame


@lru_cache(maxsize=128)
def klipper_footer(text):
    """Two bounded 42-character 5x7 lines in the existing bottom 16 pixels."""
    text = re.sub(r'~([^~]+)~', lambda m: {'degrees':'°', 'right_arrow':'→'}.get(m[1], '?'),
                  str(text)[:240])
    lines = textwrap.wrap(' '.join(text.split()), width=42, max_lines=2, placeholder='...')
    frame = Frame()
    for index, line in enumerate(lines):
        frame.text(2, 52 if len(lines) == 1 else 48+index*8, line)
    return frame.wire_bytes()[48*128:]
