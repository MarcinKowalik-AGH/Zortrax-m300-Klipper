# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate a raw M300 Classic flash backup without touching a printer."""
import hashlib
import struct

from .m300_nvm import NVMError, _read_regular


FLASH_BASE = 0x08000000
FLASH_SIZE = 0x40000
APP_OFFSET = 0x8000
APP_LIMIT = 0x3a000
BANK_OFFSETS = (0x3e800, 0x3f000)
PAGE_SIZE = 0x800
ERASED_PAGE = b'\xff' * PAGE_SIZE
RECORD_WIDTHS = (4, 2, 2, 2, 2, 4, 4)


def _check_vectors(image, start, end):
    stack, reset = struct.unpack_from('<II', image, start)
    if (not 0x20000000 < stack <= 0x20010000 or stack & 7
            or not reset & 1
            or not FLASH_BASE + start + 8 <= (reset & ~1) < FLASH_BASE + end):
        raise ValueError('invalid M300 bootloader or application vectors in backup')


def _check_records(page):
    if page[2:4] != b'\xff\xff':
        raise ValueError('unexpected M300 backup NVM page header')
    offset = 4
    found_counter = False
    while offset < PAGE_SIZE:
        record_id = int.from_bytes(page[offset:offset + 2], 'little')
        if record_id == 0xffff:
            if page[offset:] != ERASED_PAGE[offset:]:
                raise ValueError('incomplete M300 backup NVM tail')
            break
        if record_id >= len(RECORD_WIDTHS):
            raise ValueError('unknown M300 backup NVM record ID')
        start = offset + 2
        offset = start + RECORD_WIDTHS[record_id]
        if offset > PAGE_SIZE:
            raise ValueError('truncated M300 backup NVM record')
        if record_id == 0:
            if page[start:offset] == b'\xff' * 4:
                raise ValueError('invalid M300 backup print counter')
            found_counter = True
    if not found_counter:
        raise ValueError('M300 backup has no factory print counter')


def validate_backup(path, serial):
    """Return the digest of a complete, normalized backup for this factory serial."""
    try:
        image = _read_regular(path, FLASH_SIZE)
    except NVMError as exc:
        raise ValueError('M300 backup must be a regular file of 262144 raw bytes') from exc
    if len(image) != FLASH_SIZE:
        raise ValueError('M300 backup must be 262144 raw bytes from 0x08000000')
    _check_vectors(image, 0, APP_OFFSET)
    _check_vectors(image, APP_OFFSET, APP_LIMIT)
    header = struct.unpack_from('<I', image, 0x3f818)[0]
    raw_serial = int.from_bytes(image[0x3f81c:0x3f820], 'big')
    if (header != 0xaabb0401 or raw_serial in (0, 0xffffffff)
            or serial != 'Z%08X' % raw_serial):
        raise ValueError('M300 backup does not match the connected factory serial')
    hw_header = struct.unpack_from('<I', image, 0x3f848)[0]
    if hw_header != 0xaabb0103 or not 0xe0 <= image[0x3f84c] < 0xff:
        raise ValueError('invalid M300 backup factory hardware record')
    banks = [image[start:start + PAGE_SIZE] for start in BANK_OFFSETS]
    if banks.count(ERASED_PAGE) != 1:
        raise ValueError('M300 backup requires one fully erased NVM bank')
    active = banks[1 - banks.index(ERASED_PAGE)]
    if active[:2] != b'\0\0':
        raise ValueError('M300 backup has no normalized active NVM bank')
    _check_records(active)
    return hashlib.sha256(image).hexdigest()
