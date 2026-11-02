# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded, all-or-nothing M300 1.3.1 Z-code to native G-code compiler.

The supported profile is deliberately explicit.  Framing comes from the
existing m300_zcode module; opcode semantics are grounded in M300 1.3.1
0x08019D58, 0x0801A0F8, 0x080198A8 and 0x08017E44 (see M04_BINARY.md).
This module performs no IO, changes no heater, and never runs a command.

There is no fallback temperature or guessed machine position.  A caller must
pass the returned bytes through the independent M02 dialect/snapshot checks
and enforce requires_homing before it can start a job.  A synthetic fixture
and a register-C oracle are software evidence, not a physical M300 print.
"""
from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import struct

try:
    from .m300_zcode import parse_header, crc8_d5, ZCodeError
except ImportError:
    from m300_zcode import parse_header, crc8_d5, ZCodeError

PROFILE = 'M300_STOCK_1.3.1_SUBSET_V2_RECOVERED'
STOCK_SHA256 = '11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75'
DEFAULT_MAX_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_RECORDS = 1000000
MAX_PARAMETER = 1000000.


class BinaryRejected(ZCodeError):
    """The entire source is unsuitable for the declared execution profile."""


@dataclass(frozen=True)
class Compilation:
    gcode: bytes
    metadata: dict
    targets: dict
    requires_homing: bool


def _finite(value, description):
    if isinstance(value, bool):
        raise BinaryRejected(description + ' must be numeric')
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError):
        raise BinaryRejected(description + ' must be finite')
    if not math.isfinite(value):
        raise BinaryRejected(description + ' must be finite')
    return value


def _bounds(heater_limits, axis_limits):
    if heater_limits is None:
        heater_limits = {'hotend': (1., 300.), 'bed': (1., 130.)}
    heaters = {}
    for name in ('hotend', 'bed'):
        try:
            low, high = heater_limits[name]
        except (KeyError, ValueError, TypeError):
            raise BinaryRejected('invalid heater limits for ' + name)
        low, high = _finite(low, name + ' minimum'), _finite(high, name + ' maximum')
        if low < 0. or high <= low or high > (300. if name == 'hotend' else 130.):
            raise BinaryRejected('heater limits exceed M300 profile hard caps')
        heaters[name] = (low, high)
    if axis_limits is None:
        axes = {axis: (0., MAX_PARAMETER) for axis in 'XYZ'}
    elif isinstance(axis_limits, dict):
        try:
            axes = {axis: tuple(axis_limits[axis]) for axis in 'XYZ'}
        except (KeyError, TypeError):
            raise BinaryRejected('axis_limits must include X, Y, Z')
    else:
        try:
            minimum, maximum = axis_limits
            axes = {axis: (minimum[i], maximum[i]) for i, axis in enumerate('XYZ')}
        except (TypeError, ValueError, IndexError):
            raise BinaryRejected('axis_limits must be (minimum_xyz, maximum_xyz)')
    for axis, pair in axes.items():
        if len(pair) != 2:
            raise BinaryRejected('invalid bounds for ' + axis)
        low, high = (_finite(v, axis + ' boundary') for v in pair)
        # Negative Z goes through a stock unsigned conversion; it is outside
        # this profile even when a Klipper machine permits negative positions.
        low = max(0., low)
        if not low < high <= MAX_PARAMETER:
            raise BinaryRejected('invalid bounds for ' + axis)
        axes[axis] = (low, high)
    return heaters, axes


def _fmt(value):
    # Nine decimal places retain sub-step precision at all admitted scales;
    # no exponent notation (M02 intentionally does not accept exponents).
    return ('%.9f' % value).rstrip('0').rstrip('.') or '0'


def compile_m300(data, *, heater_limits=None, axis_limits=None,
                 max_bytes=DEFAULT_MAX_BYTES,
                 max_records=DEFAULT_MAX_RECORDS,
                 max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES):
    """Return Compilation after validating every byte, including the tail.

    Heater and axis limits should come from the actual Klipper configuration.
    ``requires_homing`` means a complete stock XYZ homing prefix was removed
    from G-code and must be performed by qualified M02 native_contact startup.
    The function does not authorize execution, even when it returns normally.
    """
    for name, value in (('max_bytes', max_bytes), ('max_records', max_records),
                        ('max_output_bytes', max_output_bytes)):
        if type(value) is not int or value <= 0:
            raise BinaryRejected(name + ' must be a positive integer')
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise BinaryRejected('source must be binary bytes')
    source_bytes = data.nbytes if isinstance(data, memoryview) else len(data)
    if source_bytes > max_bytes:
        raise BinaryRejected('source exceeds byte limit')
    data = bytes(data)  # Own one immutable source; never execute a mutable view.
    header = parse_header(data[:128], 'm300')
    count = header['declared_records']
    if not 0 < count <= max_records:
        raise BinaryRejected('declared record count is outside limits')
    if tuple(header['firmware_triplet']) > (1, 3, 1):
        raise BinaryRejected('required firmware is newer than audited M300 1.3.1')
    scales = header['declared_steps_per_mm']
    if (scales['X'], scales['Y'], scales['E']) != (640, 640, 960) or scales['Z'] not in (400, 800):
        raise BinaryRejected('unsupported XY/Z/E scales for the M300 profile')
    if scales['A'] not in (0, 1) or scales['B'] not in (0, 1) or scales['Z2']:
        raise BinaryRejected('unsupported auxiliary header scales')
    if header['support_filament_mm']:
        raise BinaryRejected('support/dual-extruder material is outside the M300 profile')
    heaters, axes = _bounds(heater_limits, axis_limits)
    lines = []
    output_size = 0

    def emit(line):
        nonlocal output_size
        encoded = (line + '\n').encode('ascii')
        output_size += len(encoded)
        if output_size > max_output_bytes:
            raise BinaryRejected('compiled G-code exceeds output byte limit')
        lines.append(encoded)

    # Body is built privately.  Startup is inserted only after complete input
    # validation; no prefix can escape if the final record is malformed.
    targets = {}
    counts = Counter()
    position = {axis: None for axis in 'XYZE'}
    feed = None
    moved = False
    e_reset = False
    requires_homing = False
    progress = []
    markers = []
    offset = 128
    for index in range(count):
        record_number = index + 1

        def reject(reason):
            raise BinaryRejected('record %d at byte %d: %s' % (record_number, offset, reason))

        if offset >= len(data):
            reject('record count exceeds available data')
        length = data[offset]
        if length < 2:
            reject('invalid record length')
        end = offset + length + 1
        if end > len(data):
            reject('truncated record')
        record = data[offset:end]
        if crc8_d5(record[:-1]) != record[-1]:
            reject('record CRC mismatch')
        opcode = record[1]
        counts[opcode] += 1
        payload = record[2:-1]

        def exact(size):
            if len(payload) != size:
                reject('incorrect payload length for opcode 0x%02X' % opcode)

        def u32(start=0):
            return struct.unpack_from('<I', payload, start)[0]

        if opcode in (0x00, 0x06, 0x07, 0x0C, 0x0D):
            # Explicit no-op branches in the stock TBB dispatcher.  An exact
            # empty shape avoids pretending that future payloads are known.
            exact(0)
        elif opcode == 0x02:
            exact(4)
            raw = u32()
            if raw:
                if not 60 <= raw <= 32767:
                    reject('feed outside positive signed16 range (60..32767)')
                # Stock feeds the planner an integer raw*100/6000 mm/s.
                feed = 60 * (raw // 60)
            elif feed is None:
                reject('zero feed cannot supply an initial feedrate')
        elif opcode in (0x03, 0x04):
            exact(1 if opcode == 0x03 else 5)
            if payload[0] != 8:
                reject('only E coordinate reset is admitted; XYZ resets are unsupported')
            raw = 0 if opcode == 0x03 else u32(1)
            value = raw / scales['E']
            if value > MAX_PARAMETER:
                reject('E reset exceeds bounded coordinate limit')
            emit('G92 E' + _fmt(value))
            e_reset = True
            position['E'] = value
        elif opcode == 0x05:
            exact(1)
            if payload[0] != 7 or moved or requires_homing:
                reject('only one complete XYZ homing prefix is supported')
            requires_homing = True
        elif opcode in (0x08, 0x0E):
            exact(5 if opcode == 0x08 else 4)
            name = 'hotend' if opcode == 0x08 else 'bed'
            if opcode == 0x08 and payload[0] != 0:
                reject('only extruder T0 is supported')
            raw = u32(1 if opcode == 0x08 else 0)
            value = raw if name == 'hotend' else raw + 10
            if name not in targets:
                if record_number > 10 or moved:
                    reject('initial explicit heater targets must precede movement in first ten records')
                low, high = heaters[name]
                if not value > 0 or not low <= value <= high:
                    reject(name + ' target outside configured heater limits')
                targets[name] = value
            elif value != targets[name]:
                # Stock's initial-heat latch ignores later values.  Rewriting
                # them as M104/M140 would invent different execution behavior.
                reject('changing a latched heater target is outside this subset')
        elif opcode == 0x09:
            exact(0)
            # Sets the stock mode flag to zero. Raw move targets in the audited
            # path are absolute; the compiler starts native G90/M82 explicitly.
        elif opcode == 0x0A:
            reject('opcode 0x0A mode=1 has no proven native coordinate mapping')
        elif opcode == 0x0B:
            exact(1)
            if payload[0] > 100:
                reject('progress percentage exceeds 100')
            progress.append({'record': record_number, 'percent': payload[0]})
            emit('; ZCODE_PROGRESS %d' % payload[0])
        elif opcode == 0x0F:
            exact(0)
            if not moved:
                reject('pre-motion pause is outside this subset')
            emit('PAUSE')
        elif opcode == 0x10:
            exact(4)
            raw = struct.unpack('<i', payload)[0]
            markers.append({'record': record_number, 'raw': raw})
            emit('; ZCODE_MARKER %d' % raw)
        elif opcode == 0x01:
            if len(payload) < 2:
                reject('move must contain subtype and mask')
            subtype, mask = payload[:2]
            if mask & 0x80 or mask == 0:
                reject('unsupported move mask')
            exact(2 + 4 * mask.bit_count())
            values = {}
            p = 2
            for bit, axis in enumerate(('X', 'Y', 'Z', 'E', 'A', 'FAN', 'B')):
                if mask & (1 << bit):
                    values[axis] = struct.unpack_from('<i' if axis == 'E' else '<I', payload, p)[0]
                    p += 4
            if values.get('A', 0) or values.get('B', 0):
                reject('nonzero auxiliary move field is unsupported')
            if 'FAN' in values:
                if values['FAN'] > 255:
                    reject('fan field has nonzero upper bytes')
                emit('M106 S%d' % values['FAN'])
            motion_fields = set(values) & set('XYZE')
            if motion_fields:
                if set(targets) != {'hotend', 'bed'}:
                    reject('motion requires both explicit initial heater targets')
                if feed is None:
                    reject('motion requires explicit nonzero initial feedrate')
                if not moved and not set('XYZ') <= motion_fields:
                    reject('first move must define complete XYZ position')
                if 'E' in values and not e_reset:
                    reject('E must be explicitly reset before extrusion')
                words = []
                for axis in 'XYZE':
                    if axis not in values:
                        continue
                    value = values[axis] / scales[axis]
                    if abs(value) > MAX_PARAMETER:
                        reject(axis + ' coordinate exceeds bounded dialect')
                    if axis in axes and not axes[axis][0] <= value <= axes[axis][1]:
                        reject(axis + ' coordinate outside configured axis limits')
                    position[axis] = value
                    words.append(axis + _fmt(value))
                words.append('F%d' % feed)
                emit('G1 ' + ' '.join(words))
                moved = True
        else:
            reject('unsupported opcode 0x%02X' % opcode)
        offset = end
    if offset != len(data):
        raise BinaryRejected('trailing data / declared record count mismatch')
    if set(targets) != {'hotend', 'bed'}:
        raise BinaryRejected('both explicit initial heater targets are required')
    if not moved:
        raise BinaryRejected('file contains no supported motion')
    prefix = ('; ' + PROFILE + '\nG90\nM82\nM220 S100\nM221 S100\n'
              'START_PRINT EXTRUDER_TEMP=%d BED_TEMP=%d\n' %
              (targets['hotend'], targets['bed'])).encode('ascii')
    suffix = b'M400\nEND_PRINT\n'
    if len(prefix) + output_size + len(suffix) > max_output_bytes:
        raise BinaryRejected('compiled G-code exceeds output byte limit')
    gcode = prefix + b''.join(lines) + suffix
    metadata = dict(header)
    metadata.update({
        'profile': PROFILE, 'source_sha256': hashlib.sha256(data).hexdigest(),
        'source_bytes': len(data), 'gcode_sha256': hashlib.sha256(gcode).hexdigest(),
        'gcode_bytes': len(gcode), 'records': count,
        'opcode_counts': {'0x%02X' % op: n for op, n in sorted(counts.items())},
        'targets': dict(targets), 'requires_homing': requires_homing,
        'progress_events': progress, 'marker_events': markers,
        'framing_and_crc_valid': True, 'supported_semantics_validated': True,
        'whole_file_validated': True, 'executed': False,
        'physical_m300_zsuite_corpus_validated': False,
        'stock_application_sha256': STOCK_SHA256,
        'intentional_adaptations': [
            'Native Klipper planner and bounded kinematics',
            'Whole-file preflight before any heating or movement',
            'No stock fallback temperatures; M02 owns stable preheat',
            'M02 owns qualified homing, pause, drain, cleanup and EOF',
            'Z raw/headerZ converted to mm; stock intermediate step truncation omitted',
        ],
    })
    return Compilation(gcode, metadata, dict(targets), requires_homing)
