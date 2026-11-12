# SPDX-License-Identifier: GPL-3.0-or-later
"""RC UI migration: remove exact stock lab macros; preserve operator extensions."""
import hashlib
import json
from pathlib import Path
import re
import m300_profile as profile

HERE = Path(__file__).resolve().parent
RETIRED = frozenset(('TEST_ZORTRAX_STATUS', 'TEST_ZORTRAX_XY', 'ZORTRAX_PRINT', 'ZORTRAX_OLED_PERF'))
UPDATED = frozenset(('ZORTRAX_LIGHT', 'ZORTRAX_BUZZER', 'ZORTRAX_SLEEP_MODE',
                    'ZORTRAX_MODELS_SORT', 'ZORTRAX_FULL_PLATFORM_PREHEAT',
                    'ZORTRAX_INFORMATION', 'ZORTRAX_PLATFORM_UP', 'ZORTRAX_PLATFORM_DOWN'))


def command_hash(block):
    _, commands = profile.gcode_body(block)
    # Only ordinary wrapper options may be replaced. Variables or extra
    # commands mean this is an operator-owned macro, not a stock definition.
    options = set(re.findall(r'^([^\s#;][^:=\r\n]*?)[=:]', block, re.M))
    if options - {'description', 'gcode'}:
        return None
    return hashlib.sha256('\n'.join(commands).encode()).hexdigest()


def apply_to_plan(desired, config):
    baselines = json.loads((HERE/'RC_UI_BASELINES.json').read_text())
    canonical = dict(profile.blocks((HERE/'payload/m300_operations.cfg').read_text())[1])
    for path, data in list(desired.items()):
        if path.suffix != '.cfg' or not path.is_relative_to(config.parent):
            continue
        prefix, chunks, saved = profile.blocks(data.decode())
        result = [prefix]
        for section, block in chunks:
            name = section[12:] if section.startswith('gcode_macro ') else None
            signature = command_hash(block) if name else None
            stock = signature is not None and signature in baselines.get(name, ())
            if name in RETIRED and stock:
                continue
            if name in UPDATED and stock:
                block = canonical[section].rstrip() + '\n\n'
            result.append(block)
        desired[path] = (''.join(result) + saved).encode()
    # Keep empty compatibility files on disk for rollback and external includes,
    # but stop including the shipped test-only file when no user content remains.
    old = config.parent/'m300_tests.cfg'
    if old in desired and not profile.blocks(desired[old].decode())[1]:
        for path, data in list(desired.items()):
            if path.suffix != '.cfg' or not path.is_relative_to(config.parent):
                continue
            prefix, chunks, saved = profile.blocks(data.decode())
            chunks = [(n,b) for n,b in chunks if not (n.lower().startswith('include ')
                and (path.parent/n[8:].strip()).resolve() == old.resolve())]
            desired[path] = (prefix+''.join(b for _,b in chunks)+saved).encode()
