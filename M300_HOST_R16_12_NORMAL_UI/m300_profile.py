"""R16 normal-operation configuration migration; keeps calibration text intact."""
from pathlib import Path
import glob
import math
import re

HEADER = re.compile(r'^\[([^]\r\n]+)\]\s*(?:[#;].*)?$', re.M)
MACRO_RENAMES = {'TEST_M300_STATUS': 'TEST_ZORTRAX_STATUS',
                 'TEST_M300_XY': 'TEST_ZORTRAX_XY'}
RETIRED_LEVEL_MACROS = {'TEST_M300_LEVEL', 'TEST_ZORTRAX_LEVEL'}
LEVEL_WRAPPER = re.compile(
    r'ZORTRAX_PROCEDURE_START OP=LEVEL TEMP=\{params\.TEMP\|default\((180|260)\)\|float\}')
IDLE_GCODE = 'gcode:\n    TURN_OFF_HEATERS\n    ZORTRAX_IDLE_RELEASE_XYE\n'
CHOICE_MACROS = {
    'gcode_macro ZORTRAX_LIGHT': ('light_mode', 'MODE'),
    'gcode_macro ZORTRAX_BUZZER': ('buzzer', 'STATE'),
    'gcode_macro ZORTRAX_SLEEP_MODE': ('sleep', 'STATE'),
    'gcode_macro ZORTRAX_MODELS_SORT': ('sort', 'MODE'),
}
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


def gcode_body(block):
    match = re.search(r'^gcode[ \t]*[=:][ \t]*([^\r\n]*)(?:\r?\n|$)', block, re.M | re.I)
    if match is None:
        return None, []
    lines = [line.split('#', 1)[0].split(';', 1)[0].strip()
             for line in (match[1] + '\n' + block[match.end():]).splitlines()]
    return match, [line for line in lines if line]


def migrate_idle(block):
    match, commands = gcode_body(block)
    if match is None:
        return block.rstrip() + '\n' + IDLE_GCODE + '\n'
    if commands in (['TURN_OFF_HEATERS', 'M84'], ['TURN_OFF_HEATERS', 'M18']):
        return re.sub(r'(?m)^([ \t]+)M(?:84|18)([ \t]*(?:[#;].*)?)$',
                      r'\1ZORTRAX_IDLE_RELEASE_XYE\2', block, count=1)
    return block


def convert_text(text):
    prefix, chunks, saved = blocks(text)
    output = [prefix]
    for section, block in chunks:
        if section in DROP:
            continue
        if section.startswith('gcode_macro '):
            old = section[12:]
            if old in RETIRED_LEVEL_MACROS:
                header_options = re.findall(r'^([^\s#;][^:=\r\n]*?)[=:]', block, re.M)
                _, commands = gcode_body(block)
                if (set(header_options) <= {'description', 'gcode'} and len(commands) == 1
                        and LEVEL_WRAPPER.fullmatch(commands[0])):
                    continue
            if old in MACRO_RENAMES:
                renamed = 'gcode_macro ' + MACRO_RENAMES[old]
                block = block.replace('[' + section + ']', '[' + renamed + ']', 1)
                section = renamed
        if section == 'm300_motion' and option(block, 'mode') != 'native':
            # The complete old text stays in the installer's rollback receipt.
            block = ('[m300_motion]\nmode: native\nhome_xy: ' +
                     option(block, 'home_xy', '150, 158') +
                     '\nhome_travel_speed: 50\nz_home_hotend_target: 180\n'
                     'z_contact_clearance: 5\nz_lift_speed: 5\n\n')
        elif section == 'idle_timeout':
            block = migrate_idle(block)
        elif section == 'mcu':
            # The M300 direct UART has no Arduino DTR reset wire. Select the
            # native software reset used by both explicit and startup recovery.
            block = set_option(block, 'restart_method', 'command')
        elif section == 'm300_mcu':
            block = set_option(block, 'native_control', 'True')
        elif section in ('output_pin m300_led_r', 'output_pin m300_led_g',
                         'output_pin m300_led_b'):
            block = set_option(block, 'pwm', 'True')
            block = set_option(block, 'cycle_time', '0.010')
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
            travel_speed = option(block, 'travel_speed')
            if travel_speed is None or float(travel_speed) == 10.:
                # Upgrade the old M07 commissioning value to OEM F6000.
                block = set_option(block, 'travel_speed', 100)
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
        elif section in CHOICE_MACROS:
            key, param = CHOICE_MACROS[section]
            old_command = (r'^([ \t]*)ZORTRAX_(?:UI_)?SETTING[ \t]+NAME=' + key
                           + r'[ \t]+VALUE=\{params\.' + param
                           + r"\s*\|\s*default\([^\r\n{}]*\)\}[ \t]*$")
            command = ("ZORTRAX_UI_SETTING NAME=%s {%% if '%s' in params %%}"
                       "VALUE={params['%s']}{%% endif %%}") % (key, param, param)
            block = re.sub(old_command, lambda match: match[1] + command,
                           block, flags=re.MULTILINE)
        elif section == 'gcode_macro ZORTRAX_LANGUAGE':
            block = re.sub(r'^(\s*ZORTRAX_UI_SETTING NAME=language) VALUE=EN[ \t]*$',
                           r'\1', block, flags=re.MULTILINE)
        elif section == 'gcode_macro ZORTRAX_INFORMATION':
            block = block.replace('REFRESH={params.REFRESH|', "REFRESH={params['REFRESH']|")
        elif section == 'gcode_macro ZORTRAX_LEVEL':
            block = ('[gcode_macro ZORTRAX_LEVEL]\n'
                     'description: OEM Autocalibration at 260C; shared OLED and Fluidd steps\n'
                     'gcode:\n    ZORTRAX_PROCEDURE_START OP=LEVEL TEMP={params.TEMP|default(260)|float}\n\n')
        elif section == 'gcode_macro ZORTRAX_CHANGE':
            block = ('[gcode_macro ZORTRAX_CHANGE]\n'
                     'description: Change material in a paused native print; explicit Resume\n'
                     'gcode:\n    ZORTRAX_PROCEDURE_START OP=CHANGE '
                     '{% if params.TEMP is defined %}TEMP={params.TEMP|float}{% endif %}\n\n')
        elif section in ('gcode_macro ZORTRAX_LOAD', 'gcode_macro ZORTRAX_UNLOAD'):
            # Existing wrappers live in included files on installed R16.x.
            # Update the TEMP default while preserving their other commands.
            block = re.sub(r'params\.TEMP\s*\|\s*default\([^)]*\)',
                           'params.TEMP|default(240)', block)
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
