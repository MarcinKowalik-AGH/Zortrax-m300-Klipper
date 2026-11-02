# SPDX-License-Identifier: GPL-3.0-or-later
"""M13 pure, fail-closed compatibility classification for M300 Classic binary Z-code.

This does not add opcodes to the already audited M04 compiler. It provides a
stable, bounded, reproducible proof before M02 creates its own checked snapshot.
"""
from dataclasses import dataclass
import hashlib
from .m300_binary import compile_m300, BinaryRejected, PROFILE, DEFAULT_MAX_BYTES
from .m300_zcode import parse_header, ZCodeError

class PolicyError(ValueError):
    pass

COMPATIBILITY = 'M300_CLASSIC_1.3.1_STRICT_SUBSET'
ALLOWED_MODEL_IDS = tuple(range(20,30))
ALLOWED_Z_SCALES = (400, 800)
SUPPORTED_OPCODES = (0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,
                     0x09,0x0B,0x0C,0x0D,0x0E,0x0F,0x10)

@dataclass(frozen=True)
class CompatibilityProof:
    source_sha256: str
    source_size: int
    model: int
    steps_z: int
    records: int
    opcodes: tuple
    converted_gcode_sha256: str
    requires_homing: bool
    targets: tuple

    def public(self):
        return {'profile':COMPATIBILITY,'m04_compiler_profile':PROFILE,
                'source_sha256':self.source_sha256,'source_bytes':self.source_size,
                'model_code':self.model,'steps_z':self.steps_z,
                'records':self.records,'opcode_counts':dict(self.opcodes),
                'gcode_sha256':self.converted_gcode_sha256,
                'requires_homing':self.requires_homing,
                'targets':dict(self.targets), 'all_records_checked':True,
                'executed':False,'zsuite_real_corpus_verified':False}


def prove(data, heater_limits=None, axis_limits=None,
          max_bytes=DEFAULT_MAX_BYTES, max_records=1000000,
          max_output_bytes=64*1024*1024):
    if type(max_bytes) is not int or not 128 <= max_bytes <= 128*1024*1024:
        raise PolicyError('invalid bounded source size')
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise PolicyError('M13 accepts binary bytes only')
    if len(data) > max_bytes:
        raise PolicyError('M13 source exceeds maximum size')
    try:
        header = parse_header(bytes(data[:128]), 'm300')
    except ZCodeError as exc:
        raise PolicyError('M300 framing/header: '+str(exc))
    if header['printer_id'] not in ALLOWED_MODEL_IDS:
        raise PolicyError('unsupported M300 model id')
    if header['declared_steps_per_mm']['Z'] not in ALLOWED_Z_SCALES:
        raise PolicyError('unsupported Z-scale variant')
    try:
        compiled = compile_m300(data,heater_limits=heater_limits, axis_limits=axis_limits,
                                max_bytes=max_bytes,max_records=max_records,
                                max_output_bytes=max_output_bytes)
    except (BinaryRejected,ZCodeError) as exc:
        raise PolicyError('unsupported/corrupt M300 Z-code: '+str(exc))
    ops=tuple(sorted(compiled.metadata['opcode_counts'].items()))
    if any(int(op,16) not in SUPPORTED_OPCODES for op,count in ops):
        raise PolicyError('unclassified opcode')
    if compiled.metadata['source_sha256'] != hashlib.sha256(data).hexdigest():
        raise PolicyError('source proof mismatch')
    return CompatibilityProof(compiled.metadata['source_sha256'],len(data),
                              header['printer_id'],header['declared_steps_per_mm']['Z'],
                              compiled.metadata['records'],ops,
                              compiled.metadata['gcode_sha256'],
                              bool(compiled.requires_homing),
                              tuple(sorted(compiled.targets.items())))
