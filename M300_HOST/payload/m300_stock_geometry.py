# SPDX-License-Identifier: GPL-3.0-or-later
"""OEM 1.3.1 session XY offsets: 0x08008174 and 0x080159a0."""


def stock_xy_offsets(seed):
    if type(seed) is not int or not 0 <= seed <= 0xffffffff:
        raise ValueError('stock random seed must be uint32')
    result = []
    for _ in range(2):
        seed = (seed * 1103515245 + 12345) & 0xffffffff
        result.append((seed >> 1) % 7 - 3)
    return tuple(result)
