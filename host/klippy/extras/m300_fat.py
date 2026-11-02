# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded, read-only FAT16/FAT32 reader for the private M300 SD transport.

All sector reads pass through a caller-owned function. No file-system writes,
host paths, G-code, symlinks or MCU commands are accepted here. The FAT copy is
chosen from BPB flags; multi-partition and ambiguous name matches fail closed.
"""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import struct


class FATError(ValueError):
    pass


def u16(data, offset):
    return struct.unpack_from('<H', data, offset)[0]


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


@dataclass(frozen=True)
class Entry:
    name: str
    cluster: int
    size: int
    directory: bool
    fingerprint: str
    modified: int


def path_parts(path):
    if not isinstance(path, str) or len(path.encode('utf-8')) > 255:
        raise FATError('SD path must contain at most 255 UTF-8 bytes')
    if path in ('', '/'):
        return []
    if path.startswith('/'):
        path = path[1:]
    parts = path.split('/')
    if len(parts) > 16 or any(p in ('', '.', '..') for p in parts):
        raise FATError('invalid SD path or excessive depth')
    if any(ord(c) < 32 or ord(c) == 127 or c in '\\:' for c in path):
        raise FATError('invalid SD path character')
    return parts


def _lfn_checksum(short):
    value = 0
    for b in short:
        value = (((value & 1) << 7) | (value >> 1)) + b
        value &= 255
    return value


def _valid_name(name):
    return (bool(name) and name not in ('.', '..') and len(name) <= 255
            and not any(ord(c) < 32 or ord(c) == 127 or c in '/\\:' for c in name))


class FATVolume:
    def __init__(self, read_sector, block_count, max_directory_entries=4096,
                 max_chain_clusters=262144):
        if isinstance(block_count, bool) or not 1 <= int(block_count) <= 0xffffffff:
            raise FATError('invalid SD block count')
        self.read_sector = read_sector
        self.blocks = int(block_count)
        self.max_entries = max_directory_entries
        self.max_chain = max_chain_clusters
        self._cache = OrderedDict()
        first = self._raw(0)
        if first[510:] != b'\x55\xaa':
            raise FATError('missing MBR/BPB signature')
        # A plausible BPB is a superfloppy. Otherwise require exactly one FAT
        # primary partition. GPT, extended and other partition types rejected.
        plausible = (first[0] in (0xeb, 0xe9) and u16(first, 11) == 512
                     and first[13] in (1, 2, 4, 8, 16, 32, 64, 128))
        self.base = 0
        self.partition_blocks = self.blocks
        if not plausible:
            partitions = []
            for index in range(4):
                offset = 446 + 16 * index
                kind = first[offset + 4]
                start, count = u32(first, offset + 8), u32(first, offset + 12)
                if not kind and not start and not count:
                    continue
                if kind not in (0x04, 0x06, 0x0e, 0x0b, 0x0c):
                    raise FATError('only a FAT16/FAT32 primary partition is supported')
                if not start or not count or start + count > self.blocks:
                    raise FATError('partition outside card')
                partitions.append((start, count, kind))
            if len(partitions) != 1:
                raise FATError('exactly one FAT partition is required')
            self.base, self.partition_blocks, partition_kind = partitions[0]
            first = self._raw(self.base)
        else:
            partition_kind = None
        if first[510:] != b'\x55\xaa' or u16(first, 11) != 512:
            raise FATError('only 512-byte sectors with a valid BPB are supported')
        self.spc = first[13]
        self.reserved, self.nfats = u16(first, 14), first[16]
        self.root_count = u16(first, 17)
        total16, total32 = u16(first, 19), u32(first, 32)
        if total16 and total32 and total16 != total32:
            raise FATError('conflicting FAT total-sector fields')
        self.total = total16 or total32
        fat16, fat32 = u16(first, 22), u32(first, 36)
        self.fat_sectors = fat16 or fat32
        if (self.spc not in (1, 2, 4, 8, 16, 32, 64, 128)
                or self.reserved < 1 or self.nfats not in (1, 2)
                or not self.fat_sectors or not self.total
                or self.total > self.partition_blocks):
            raise FATError('invalid BPB geometry')
        self.root_sectors = (self.root_count * 32 + 511) // 512
        self.fat_start = self.base + self.reserved
        self.root_start = self.fat_start + self.nfats * self.fat_sectors
        self.data_start = self.root_start + self.root_sectors
        data_sectors = self.total - (self.data_start - self.base)
        if data_sectors <= 0:
            raise FATError('empty or negative FAT data area')
        self.clusters = data_sectors // self.spc
        if self.clusters < 4085:
            raise FATError('FAT12 is unsupported')
        self.bits = 16 if self.clusters < 65525 else 32
        if self.clusters >= 0x0ffffff5:
            raise FATError('FAT cluster count out of range')
        self.entry_bytes = self.bits // 8
        if (self.clusters + 2) * self.entry_bytes > self.fat_sectors * 512:
            raise FATError('FAT too short for data geometry')
        if self.bits == 16:
            if not fat16 or not self.root_count:
                raise FATError('invalid FAT16 root/size')
            self.root_cluster = None
            if partition_kind not in (None, 0x04, 0x06, 0x0e):
                raise FATError('partition type disagrees with FAT16 geometry')
        else:
            if fat16 or self.root_count or u16(first, 42) != 0:
                raise FATError('invalid/unsupported FAT32 BPB')
            self.root_cluster = u32(first, 44) & 0x0fffffff
            self._cluster(self.root_cluster)
            flags = u16(first, 40)
            if flags & 0x80:
                selected = flags & 15
                if selected >= self.nfats:
                    raise FATError('invalid active FAT copy')
                self.fat_start += selected * self.fat_sectors
            if partition_kind not in (None, 0x0b, 0x0c):
                raise FATError('partition type disagrees with FAT32 geometry')
        self.volume_id = hashlib.sha256(first).hexdigest()

    def _raw(self, lba):
        if isinstance(lba, bool) or not 0 <= lba < self.blocks:
            raise FATError('sector outside card')
        block = bytes(self.read_sector(lba))
        if len(block) != 512:
            raise FATError('short sector')
        return block

    def _sector(self, lba):
        if not self.base <= lba < self.base + self.total:
            raise FATError('sector outside FAT partition')
        return self._raw(lba)

    def _cluster(self, cluster):
        if not 2 <= cluster < self.clusters + 2:
            raise FATError('cluster outside data area')
        return cluster

    def _next(self, cluster):
        offset = self._cluster(cluster) * self.entry_bytes
        lba = self.fat_start + offset // 512
        block = self._cache.get(lba)
        if block is None:
            block = self._sector(lba)
            self._cache[lba] = block
            if len(self._cache) > 8:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(lba)
        value = (u16(block, offset % 512) if self.bits == 16
                 else u32(block, offset % 512) & 0x0fffffff)
        if value >= (0xfff8 if self.bits == 16 else 0x0ffffff8):
            return None
        if value >= (0xfff0 if self.bits == 16 else 0x0ffffff0):
            raise FATError('bad/reserved FAT cluster')
        return self._cluster(value)

    def _chain(self, start):
        current, seen = start, set()
        while current is not None:
            self._cluster(current)
            if current in seen or len(seen) >= self.max_chain:
                raise FATError('cyclic or excessive FAT chain')
            seen.add(current)
            yield current
            current = self._next(current)

    def _directory_blocks(self, cluster):
        if cluster is None:
            if self.bits != 16:
                raise FATError('missing directory cluster')
            for offset in range(self.root_sectors):
                yield self._sector(self.root_start + offset)
            return
        for current in self._chain(cluster):
            lba = self.data_start + (current - 2) * self.spc
            for offset in range(self.spc):
                yield self._sector(lba + offset)

    def _entries(self, cluster):
        long_parts, checksum, expected = {}, None, 0
        count = 0
        for block in self._directory_blocks(cluster):
            for offset in range(0, 512, 32):
                count += 1
                if count > self.max_entries:
                    raise FATError('directory scan limit exceeded')
                row = block[offset:offset + 32]
                if row[0] == 0:
                    return
                if row[0] == 0xe5:
                    long_parts, checksum, expected = {}, None, 0
                    continue
                if row[11] == 0x0f:
                    ordinal = row[0] & 0x1f
                    valid = (1 <= ordinal <= 20 and not row[0] & 0xa0
                             and row[12] == 0 and u16(row, 26) == 0)
                    if row[0] & 0x40 and valid:
                        long_parts, checksum, expected = {}, row[13], ordinal
                    if not valid or ordinal != expected or row[13] != checksum:
                        long_parts, checksum, expected = {}, None, 0
                        continue
                    long_parts[ordinal] = row[1:11] + row[14:26] + row[28:32]
                    expected -= 1
                    continue
                name = None
                if (long_parts and expected == 0
                        and checksum == _lfn_checksum(row[:11])):
                    raw = b''.join(long_parts[i] for i in sorted(long_parts))
                    units = [raw[i:i + 2] for i in range(0, len(raw), 2)]
                    if b'\x00\x00' in units:
                        end = units.index(b'\x00\x00')
                        if any(v != b'\xff\xff' for v in units[end + 1:]):
                            units = []
                        else:
                            units = units[:end]
                    try:
                        candidate = b''.join(units).decode('utf-16-le', 'strict')
                        if _valid_name(candidate):
                            name = candidate
                    except UnicodeError:
                        pass
                long_parts, checksum, expected = {}, None, 0
                if row[11] & 0x08:  # volume label
                    continue
                if row[11] & 0xc0:
                    raise FATError('reserved FAT directory attributes')
                if name is None:
                    short = bytes([0xe5 if row[0] == 5 else row[0]]) + row[1:11]
                    stem = short[:8].rstrip(b' ').decode('cp437')
                    ext = short[8:].rstrip(b' ').decode('cp437')
                    if row[12] & 0x08:
                        stem = stem.lower()
                    if row[12] & 0x10:
                        ext = ext.lower()
                    name = stem + ('.' + ext if ext else '')
                if name in ('.', '..'):
                    continue
                if not _valid_name(name):
                    raise FATError('invalid FAT directory name')
                start = u16(row, 26)
                if self.bits == 32:
                    start |= (u16(row, 20) & 0x0fff) << 16
                size = u32(row, 28)
                isdir = bool(row[11] & 0x10)
                if isdir or size:
                    self._cluster(start)
                elif start != 0:
                    self._cluster(start)
                yield Entry(name, start, size, isdir,
                            hashlib.sha256(row).hexdigest(), u32(row, 22))

    def resolve(self, path, directory=False):
        parts = path_parts(path)
        cluster, entry = self.root_cluster, None
        for index, part in enumerate(parts):
            matches = [e for e in self._entries(cluster)
                       if e.name.casefold() == part.casefold()]
            if len(matches) != 1:
                raise FATError('SD path absent or ambiguous: ' + part)
            entry = matches[0]
            if index < len(parts) - 1 or directory:
                if not entry.directory:
                    raise FATError('SD path component is not a directory')
                cluster = entry.cluster
        if directory:
            return cluster
        if entry is None or entry.directory:
            raise FATError('SD path is not a file')
        return entry

    def list_directory(self, path='/', limit=50):
        if not 1 <= limit <= 4096:
            raise FATError('invalid directory list limit')
        entries, names = [], set()
        for entry in self._entries(self.resolve(path, directory=True)):
            key = entry.name.casefold()
            if key in names:
                raise FATError('ambiguous duplicate FAT filename')
            names.add(key)
            entries.append(entry)
            if len(entries) > limit:
                raise FATError('directory exceeds %d-entry limit' % limit)
        return entries

    def iter_file(self, entry, max_bytes=16 * 1024 * 1024):
        if entry.directory or not 0 < entry.size <= max_bytes:
            raise FATError('SD file size outside allowed bounds')
        remaining = entry.size
        chain = self._chain(entry.cluster)
        for cluster in chain:
            lba = self.data_start + (cluster - 2) * self.spc
            for offset in range(self.spc):
                if not remaining:
                    break
                data = self._sector(lba + offset)[:remaining]
                remaining -= len(data)
                yield data
            if not remaining:
                # Refuse hidden extra clusters and force validation of this
                # last FAT entry; malformed tails are not silently accepted.
                if self._next(cluster) is not None:
                    raise FATError('FAT chain is longer than the declared file')
                return
        raise FATError('FAT chain shorter than declared file')
