"""Text-preserving R14 -> native-core configuration update."""
from pathlib import Path
import glob
import re

DROP = {'m300_test01'} | {'gcode_macro ' + name for name in (
    'PID_ARM', 'PID_HEAT_CHECK', 'PID_STOP',
    'ZORTRAX_TEST_PRINT_FAN', 'ZORTRAX_TEST_HOTEND_FAN',
    'ZORTRAX_FAN_SPEED', 'ZORTRAX_FAN_STOP')}
PINS = {'extruder': ('heater_pin', 'PC8'), 'heater_bed': ('heater_pin', 'PC9'),
        'fan': ('pin', 'PE13'), 'heater_fan hotend': ('pin', 'PE14')}
MACROS = {
    'gcode_macro PID_SAVE': '[gcode_macro PID_SAVE]\ndescription: Native SAVE_CONFIG\ngcode:\n    SAVE_CONFIG\n\n',
    'gcode_macro CANCEL_PRINT': '[gcode_macro CANCEL_PRINT]\ndescription: Cancel native print and turn off heaters\nrename_existing: CANCEL_PRINT_BASE\ngcode:\n    TURN_OFF_HEATERS\n    CANCEL_PRINT_BASE\n\n',
}
HEADER = re.compile(r'^\[([^]\r\n]+)\]\s*(?:[#;].*)?$', re.M)

def split_saved(text):
    m = re.search(r'^#\*#', text, re.M)
    return (text[:m.start()], text[m.start():]) if m else (text, '')

def blocks(text):
    body, saved = split_saved(text)
    matches = list(HEADER.finditer(body))
    prefix = body[:matches[0].start()] if matches else body
    result = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        result.append((match.group(1), body[match.start():end]))
    return prefix, result, saved

def option(block, name):
    match = re.search(r'^[ \t]*' + re.escape(name) + r'[ \t]*[=:][ \t]*([^\r\n#;]*)', block, re.M | re.I)
    return match.group(1).strip() if match else None

def set_option(block, name, value):
    pattern = re.compile(r'^([ \t]*' + re.escape(name) + r'[ \t]*[=:][ \t]*)([^\r\n#;]*)([^\r\n]*)$', re.M | re.I)
    if pattern.search(block):
        return pattern.sub(lambda m: m.group(1) + value + (' ' if m.group(3) else '') + m.group(3), block, count=1)
    lines = block.splitlines(keepends=True)
    lines.insert(1, name + ' = ' + value + '\n')
    return ''.join(lines)

def convert_text(text):
    prefix, chunks, saved = blocks(text)
    output = [prefix]
    for section, block in chunks:
        if section in DROP:
            continue
        if section in MACROS:
            block = MACROS[section]
        elif section == 'm300_mcu':
            for name in ('allow_actuators', 'allow_motion', 'allow_heating'):
                if (option(block, name) or '').lower() not in ('true', 'yes', 'on', '1'):
                    raise ValueError('Native profile expects the already enabled ' + name)
            block = set_option(block, 'native_control', 'True')
        elif section in PINS:
            key, pin = PINS[section]
            block = set_option(block, key, pin)
        output.append(block)
    return ''.join(output) + saved

def read_tree(path):
    result = {}
    def visit(path):
        path = path.resolve()
        if path in result:
            return
        if len(result) >= 128:
            raise ValueError('Too many configuration includes')
        text = path.read_bytes().decode('utf-8')
        result[path] = text
        for section, _ in blocks(text)[1]:
            if section.lower().startswith('include '):
                expression = section[8:].strip()
                target = Path(expression).expanduser()
                if not target.is_absolute():
                    target = path.parent / target
                matches = sorted(glob.glob(str(target)))
                if not matches and not any(c in expression for c in '*?['):
                    raise ValueError('Missing configuration include: ' + str(target))
                for match in matches:
                    visit(Path(match))
    visit(Path(path))
    sections = {}
    for file, text in result.items():
        for name, block in blocks(text)[1]:
            if name in ('m300_mcu', 'm300_motion', 'm300_thermal') or name in PINS:
                if name in sections:
                    raise ValueError('Ambiguous section across includes: ' + name)
                sections[name] = block
    required = {'m300_mcu', 'm300_motion', 'm300_thermal'} | set(PINS)
    if not required <= set(sections):
        raise ValueError('Missing required installed R14 sections: ' + str(sorted(required - set(sections))))
    if (option(sections['m300_motion'], 'production_control') or '').lower() != 'true':
        raise ValueError('Expected installed production_control=True')
    return result
