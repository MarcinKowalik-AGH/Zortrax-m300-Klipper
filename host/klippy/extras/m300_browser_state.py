# SPDX-License-Identifier: GPL-3.0-or-later
"""M12 pure, bounded, non-executing directory lease for the classic M300.

The lease is not a file capability: its identity is checked *again* by M02 when
opening an immutable snapshot. It expires on new listings and host lifecycle.
"""
from dataclasses import dataclass
import os

class BrowserError(ValueError):
    pass

ALLOWED_EXTENSIONS = frozenset(('.gcode', '.gco', '.g', '.zcode'))
SORTS = ('NAME', 'DATE', 'SIZE')


def directory_parts(path):
    if not isinstance(path, str) or path.startswith('/') or '\\' in path or ':' in path:
        raise BrowserError('invalid browser directory')
    if len(path.encode('utf-8')) >= 255 or path.count('/') >= 16:
        raise BrowserError('directory exceeds bounded size/depth')
    if any(segment in ('', '.', '..') for segment in path.split('/') if path):
        raise BrowserError('traversal or empty directory component')
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise BrowserError('control characters forbidden')
    return path


@dataclass(frozen=True)
class EntryProof:
    name: str
    path: str
    is_dir: bool
    size: int
    mtime: float

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise BrowserError('entry is not a dictionary')
        name, path = value.get('name'), value.get('path')
        if not isinstance(name, str) or not name or '/' in name or name in ('.', '..'):
            raise BrowserError('invalid file entry name')
        if not isinstance(path, str):
            raise BrowserError('invalid entry path')
        directory_parts(path)
        size, mtime = value.get('size'), value.get('mtime')
        if type(size) is not int or size < 0 or not isinstance(mtime, (int, float)):
            raise BrowserError('invalid entry stat')
        import math
        if not math.isfinite(mtime):
            raise BrowserError('non-finite entry time')
        is_dir = value.get('is_dir')
        if type(is_dir) is not bool:
            raise BrowserError('invalid entry type')
        if not is_dir and os.path.splitext(name)[1].lower() not in ALLOWED_EXTENSIONS:
            raise BrowserError('unsupported file extension')
        return cls(name, path, is_dir, size, float(mtime))


class Catalog:
    def __init__(self, limit=50):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise BrowserError('file count limit outside 1..50')
        self.limit = limit
        self.generation = 0
        self.source = self.directory = None
        self.entries = ()

    def invalidate(self):
        self.generation += 1
        self.source = self.directory = None
        self.entries = ()

    def publish(self, source, directory, entries):
        if source not in ('host', 'sd'):
            raise BrowserError('only host or read-only physical SD is supported')
        directory_parts(directory)
        if not isinstance(entries, (list, tuple)) or len(entries) > self.limit:
            raise BrowserError('directory entry count exceeded')
        material = tuple(EntryProof.from_dict(entry) for entry in entries)
        if len(set(e.path.casefold() for e in material)) != len(material):
            raise BrowserError('ambiguous duplicate paths')
        self.invalidate()
        self.source, self.directory, self.entries = source, directory, material
        return self.generation

    def selected(self, generation, index, fresh):
        if type(generation) is not int or generation != self.generation or self.source is None:
            raise BrowserError('expired directory listing token')
        if type(index) is not int or not 0 <= index < len(self.entries):
            raise BrowserError('invalid directory selection index')
        old = self.entries[index]
        if old.is_dir:
            raise BrowserError('directory is not a printable file')
        if len(fresh) > self.limit:
            raise BrowserError('directory changed beyond entry limit')
        current = [EntryProof.from_dict(row) for row in fresh]
        if len(current) != len(self.entries) or old not in current:
            self.invalidate()
            raise BrowserError('file/directory changed after listing')
        return ('sd:/' if self.source == 'sd' else '') + old.path
