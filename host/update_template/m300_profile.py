"""R16 normal-operation configuration migration; keeps calibration text intact."""
from pathlib import Path
import glob
import math
import re

HEADER = re.compile(r'^\[([^]\r\n]+)\]\s*(?:[#;].*)?$', re.M)
MACRO_RENAMES = {'TEST_M300_LEVEL': 'TEST_ZORTRAX_LEVEL',
                 'TEST_M300_STATUS': 'TEST_ZORTRAX_STATUS',
                 'TEST_M300_XY': 'TEST_ZORTRAX_XY'}
PINS = {'extruder': ('heater_pin', 'PC8'), 'heater_bed': ('heater_pin', 'PC9'),
        'fan': ('pin', 'PE13'), 'heater_fan hotend': ('pin', 'PE14')}
DROP = {'m300_test01'} | {'gcode_macro ' + n for n in (
    'PID_ARM', 'PID_HEAT_CHECK', 'PID_STOP', 'ZORTRAX_TEST_PRINT_FAN',
    'ZORTRAX_TEST_HOTEND_FAN', 'ZORTRAX_FAN_SPEED', 'ZORTRAX_FAN_STOP')}


def split_saved(text):
    match = re.search(r'^#\*#', text, re.M)
    return (text[:match.start()], text[match.start():]) if match else (text, '')


def blocks(text):
    body, saved = split_saved(text)
    matches = list(HEADER.finditer(body))
    prefix = body[:matches[0].start()] if matches else body
    chunks = [(m.group(1), body[m.start():matches[i+1].start()
               if i+1 < len(matches) else len(body)]) for i, m in enumerate(matches)]
    return prefix, chunks, saved


def option(block, name, default=None):
    m = re.search(r'^[ \t]*' + re.escape(name) + r'[ \t]*[=:][ \t]*([^\r\n#;]*)', block, re.M|re.I)
    return m.group(1).strip() if m else default


def set_option(block, name, value):
    pattern = re.compile(r'^([ \t]*' + re.escape(name) + r'[ \t]*[=:][ \t]*)([^\r\n#;]*)([^\r\n]*)$', re.M|re.I)
    if pattern.search(block):
        return pattern.sub(lambda m: m[1]+str(value)+(' ' if m[3] else '')+m[3], block, count=1)
    lines = block.splitlines(keepends=True)
    lines.insert(1, name + ': ' + str(value) + '\n')
    return ''.join(lines)


def minimum(block, name, value):
    current = float(option(block, name, value))
    if not math.isfinite(current) or current <= 0:
        raise ValueError('Invalid native motion setting: ' + name)
    return set_option(block, name, max(value, current))


def convert_text(text):
    prefix, chunks, saved = blocks(text)
    output = [prefix]
    for section, block in chunks:
        if section in DROP:
            continue
        if section.startswith('gcode_macro '):
            old = section[12:]
            if old in MACRO_RENAMES:
                renamed = 'gcode_macro ' + MACRO_RENAMES[old]
                block = block.replace('[' + section + ']', '[' + renamed + ']', 1)
                section = renamed
        if section == 'm300_motion':
            # The complete old text stays in the installer's rollback receipt.
            block = ('[m300_motion]\nmode: native\nhome_xy: ' +
                     option(block, 'home_xy', '150, 158') +
                     '\nhome_travel_speed: 50\nz_home_hotend_target: 180\n'
                     'z_contact_clearance: 5\nz_lift_speed: 5\n\n')
        elif section == 'mcu':
            # The M300 direct UART has no Arduino DTR reset wire. Select the
            # native software reset used by both explicit and startup recovery.
            block = set_option(block, 'restart_method', 'command')
        elif section == 'm300_mcu':
            block = set_option(block, 'native_control', 'True')
        elif section == 'm300_calibration':
            block = set_option(block, 'qualified', 'True')
            block = set_option(block, 'workflow', 'M07_STOCK')
            block = set_option(block, 'procedure_temperature', '260')
            defaults = {'safe_z': '5', 'probe_search_margin': '1',
                        'release_distance': '1',
                        'rear_left_positive_direction': 'CCW',
                        'rear_right_positive_direction': 'CCW',
                        'front_positive_direction': 'CCW'}
            for key, value in defaults.items():
                if option(block, key) is None:
                    block = set_option(block, key, value)
            block = minimum(block, 'approach_distance',
                            float(option(block, 'safe_z')) + float(option(block, 'probe_search_margin')))
        elif section == 'm300_filament':
            block = set_option(block, 'procedure_temperature', '240')
            block = set_option(block, 'filament_qualified', 'True')
        elif section == 'm300_maintenance':
            block = set_option(block, 'qualified', 'True')
        elif section == 'printer':
            block = minimum(block, 'max_velocity', 300)
            block = minimum(block, 'max_z_velocity', 25)
            block = minimum(block, 'max_z_accel', 50)
            # Existing print acceleration/corner settings are operator choices.
        elif section in ('stepper_x', 'stepper_y', 'stepper_z', 'extruder'):
            block = set_option(block, 'step_pulse_duration', '0.000002')
            if section == 'stepper_z':
                # Remove only the recognizable temporary 30 mm commissioning
                # envelope. Other deliberate geometry values are preserved.
                if float(option(block, 'position_max', '300')) == 30:
                    block = set_option(block, 'position_max', '300')
                if float(option(block, 'homing_speed', '4')) <= .5:
                    block = set_option(block, 'homing_speed', '4')
        elif section == 'gcode_macro PID_SAVE':
            block = ('[gcode_macro PID_SAVE]\ndescription: Save native Klipper calibration\n'
                     'gcode:\n    SAVE_CONFIG\n\n')
        elif section == 'gcode_macro ZORTRAX_LEVEL':
            block = ('[gcode_macro ZORTRAX_LEVEL]\n'
                     'description: OEM Autocalibration at 260C; shared OLED and Fluidd steps\n'
                     'gcode:\n    ZORTRAX_PROCEDURE_START OP=LEVEL TEMP={params.TEMP|default(260)|float}\n\n')
        elif section == 'gcode_macro ZORTRAX_CHANGE':
            block = ('[gcode_macro ZORTRAX_CHANGE]\n'
                     'description: Change material in a paused native print; explicit Resume\n'
                     'gcode:\n    ZORTRAX_PROCEDURE_START OP=CHANGE '
                     '{% if params.TEMP is defined %}TEMP={params.TEMP|float}{% endif %}\n\n')
        elif section in ('gcode_macro TEST_ZORTRAX_LEVEL', 'gcode_macro ZORTRAX_LOAD',
                         'gcode_macro ZORTRAX_UNLOAD'):
            # Existing wrappers live in included files on installed R16.x.
            # Update the TEMP default while preserving their other commands.
            target = '260' if section.endswith('_LEVEL') else '240'
            block = re.sub(r'params\.TEMP\s*\|\s*default\([^)]*\)',
                           'params.TEMP|default(' + target + ')', block)
        elif section == 'gcode_macro CANCEL_PRINT':
            block = ('[gcode_macro CANCEL_PRINT]\ndescription: Cancel native print and heaters\n'
                     'rename_existing: CANCEL_PRINT_BASE\ngcode:\n'
                     '    TURN_OFF_HEATERS\n    CANCEL_PRINT_BASE\n\n')
        if section in PINS:
            block = set_option(block, *PINS[section])
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
        text = path.read_text()
        result[path] = text
        for section, _ in blocks(text)[1]:
            if section.lower().startswith('include '):
                pattern = Path(section[8:].strip()).expanduser()
                if not pattern.is_absolute():
                    pattern = path.parent / pattern
                matches = sorted(glob.glob(str(pattern)))
                if not matches and not any(c in str(pattern) for c in '*?['):
                    raise ValueError('Missing configuration include: ' + str(pattern))
                for match in matches:
                    visit(Path(match))
    visit(Path(path))
    return result


def missing_macros(template, existing):
    prefix, chunks, saved = blocks(template)
    return prefix + ''.join(block for name, block in chunks if name.lower() not in existing) + saved
