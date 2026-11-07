"""R16 normal-operation configuration migration; keeps calibration text intact."""
from pathlib import Path
import glob
import hashlib
import math
import re

HEADER = re.compile(r'^\[([^]\r\n]+)\]\s*(?:[#;].*)?$', re.M)
MACRO_RENAMES = {'TEST_M300_STATUS': 'TEST_ZORTRAX_STATUS',
                 'TEST_M300_XY': 'TEST_ZORTRAX_XY',
                 'ZORTRAX_BED_MESH': 'BED_MESH'}
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
LEGACY_PAD_MESH_FIELDS = ('PROFILE PREVIEW CORNER_PAD_WIDTH CENTER_PAD_WIDTH EDGE_MARGIN '
    'FRONT_RIGHT_X FRONT_RIGHT_Y FRONT_LEFT_X FRONT_LEFT_Y CENTER_X CENTER_Y '
    'REAR_RIGHT_X REAR_RIGHT_Y REAR_LEFT_X REAR_LEFT_Y FIT_TRAVEL TRAVEL_MARGIN HOTEND_TEMP BED_TEMP').split()
PAD_MESH_FIELDS = LEGACY_PAD_MESH_FIELDS + [name+'_BOUNDS' for name in
    ('FRONT_RIGHT','FRONT_LEFT','CENTER','REAR_RIGHT','REAR_LEFT')]
OLD_PAD_COMMAND_SHAS = {'43d2381d020cfc8c449cc0aebd664303e3fe4b51677f3f43caa384a684dca86f',
    'bb879deed981f80f8912ec8ce0ca64dc817654460836e4390c9b5e7e21d78760',
    '9e60cebc0cb43c6d113a2a9982e9715d99fb55190508bee4ef57fe936fdf45be'}
DROP = {'m300_test01'} | {'gcode_macro ' + n for n in (
    'PID_ARM', 'PID_HEAT_CHECK', 'PID_STOP', 'ZORTRAX_TEST_PRINT_FAN',
    'ZORTRAX_TEST_HOTEND_FAN', 'ZORTRAX_FAN_SPEED', 'ZORTRAX_FAN_STOP')}


def pad_mesh_command(indent='    ',fields=None):
    # Fluidd discovers one params.FIELD reference per line. Build the one
    # native command from separate lines, preserving omitted config values.
    fields = PAD_MESH_FIELDS if fields is None else fields
    lines = ['{% set _m300_pad_args = [] %}']
    for key in fields:
        value = 'params.'+key
        if key.endswith('_BOUNDS'):value = "("+value+"|replace(' ',''))"
        lines.append("{%% set _m300_pad_args = _m300_pad_args + ['%s=' ~ %s] "
                     "if params.%s is defined else _m300_pad_args %%}" % (key,value,key))
    lines.append("BED_MESH_CALIBRATE {_m300_pad_args|join(' ')}")
    return ('\n'+indent).join(lines)


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


def convert_text(text, stock_xy=None):
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
        if stock_xy is not None and section == 'gcode_macro TEST_ZORTRAX_XY':
            _, commands = gcode_body(block)
            old_digest = hashlib.sha256('\n'.join(commands).encode()).hexdigest()
            if old_digest == 'b6cca4397430d4c0dafd97e51f4383cd467d2c689acec5defd54baf97b59b910':
                block = stock_xy
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
        elif section == 'heater_fan hotend':
            # Same 50 C ON / 45 C OFF thermostat as the autonomous MCU.
            # The M300 native fan adapter supplies the 5 C hysteresis and
            # ignores heater target; retain native pin/PWM ownership.
            block = set_option(block, 'heater_temp', '50')
        elif section == 'm300_pad_mesh':
            # Replace the previous stock bed-span threshold. This is the
            # complete 25-point surface range, not probe-repeat tolerance.
            span = option(block, 'max_bed_span')
            if span is not None and float(span) == .5:
                block = set_option(block, 'max_bed_span', '0.8')
            hotend = option(block, 'hotend_temperature')
            if hotend is not None and float(hotend) == 180.:
                block = set_option(block, 'hotend_temperature', '260')
        elif section == 'gcode_macro BED_MESH':
            indent = re.search(r'(?m)^([ \t]*)\{% set _m300_pad_args = \[\] %\}',block)
            if indent:
                prefix = indent[1]
                old = prefix+pad_mesh_command(prefix,LEGACY_PAD_MESH_FIELDS)
                block = block.replace(old,prefix+pad_mesh_command(prefix),1)
            def migrate_pad(match):
                if hashlib.sha256(match[2].strip().encode()).hexdigest() in OLD_PAD_COMMAND_SHAS:
                    return match[1] + pad_mesh_command(match[1])
                return match[0]
            block = re.sub(r'(?m)^([ \t]*)(BED_MESH_CALIBRATE[^\r\n]*)$',migrate_pad,block)
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
        elif section in ('gcode_macro ZORTRAX_PLATFORM_UP', 'gcode_macro ZORTRAX_PLATFORM_DOWN'):
            block = re.sub(r'SPEED=\{params\.SPEED\s*\|\s*default\(1\)\s*\|\s*float\}',
                           "{% if 'SPEED' in params %}SPEED={params['SPEED']|float}{% endif %}", block)
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


THERMAL_TABLES = 'm300_temperature_sensors.cfg'
SERVICE_CONFIG = 'm300_services.cfg'
LAYOUT_MARKER = '# M300 organized configuration v1'
SERVICE_SECTIONS = frozenset(('m300_pad_mesh', 'm300_job', 'm300_filament',
    'm300_nvm', 'm300_sd', 'm300_maintenance', 'm300_calibration', 'm300_motion',
    'm300_menu', 'm300_material_ui', 'm300_menu_ui', 'm300_browser',
    'm300_zcode_policy', 'm300_settings', 'm300_models', 'm300_print_ui'))
PID_MACROS = frozenset('gcode_macro '+name for name in
    ('PID_HOTEND', 'PID_BED', 'PID_SAVE', 'PID_STATUS'))


def _without_option(block, key):
    return re.sub(r'(?mi)^[ \t]*'+re.escape(key)+r'[ \t]*[:=][^\r\n]*(?:\r?\n|$)', '', block)


def _format_block(block):
    # Continuation lines, Jinja, option values and SAVE_CONFIG are not parsed
    # as assignments. In particular, no thermal number is rounded or fitted.
    lines = []
    for line in block.rstrip().splitlines():
        if re.match(r'^#(?:control\s*=\s*watermark| R8 PID transition:| M300 R16\.[0-9]+ native| Confirmed M300-specific presentation/settings\.)', line):
            continue
        if line and not line[0].isspace() and not line.startswith(('#', ';', '[')):
            line = re.sub(r'^([^:=\s]+)[ \t]*[:=][ \t]*', r'\1: ', line, count=1)
        lines.append(line.expandtabs(4).rstrip())
    return '\n'.join(lines).rstrip()+'\n\n'


def organize_tree(tree, root):
    """Opt-in layout cleanup of the active include graph, never backup files.

    Preserve hardware values, active macros, state paths/identity and the exact
    root SAVE_CONFIG block. New files are inside the same configuration root.
    Unknown duplicate sections and custom target files are not overwritten.
    """
    root = root.resolve()
    tree = {p.resolve(): text for p, text in tree.items()}
    parsed = {p: blocks(text) for p, text in tree.items()}
    flat = [(p, name, block) for p, (_, sections, _) in parsed.items()
            for name, block in sections if not name.lower().startswith('include ')]
    names = {}
    for p, name, block in flat:
        names.setdefault(name.lower(), []).append((p, block))
    for name, records in names.items():
        meaningful = [block for _, block in records
                      if any(line.strip() and not line.lstrip().startswith(('#', ';'))
                             for line in block.splitlines()[1:])]
        if len(meaningful) > 1:
            raise ValueError('Organize requires unambiguous sections: '+name)
    section_map = {name: block for _, name, block in flat}
    native = option(section_map.get('m300_mcu', ''), 'native_control', 'False').lower() in ('true', '1', 'yes', 'on')
    if not native:
        raise ValueError('Organize requires an already native M300 configuration')
    main_saved = parsed[root][2]
    for path, (_, _, saved) in parsed.items():
        if saved and path != root:
            raise ValueError('Keep SAVE_CONFIG only in the main printer configuration')
    custom_cycle = any(re.search(r'\bZORTRAX_CYCLE_(?:STATUS|ACTION)\b', block)
                       for _, name, block in flat if name.startswith('gcode_macro '))
    cycle = section_map.get('m300_cycle', '')
    cycle_keys = set(re.findall(r'(?m)^([^\s#;\[:=]+)\s*[:=]', cycle))
    retire_cycle = (bool(cycle) and cycle_keys <= {'qualified'} and not custom_cycle
                    and option(cycle, 'qualified', 'False').lower() in ('false', '0', 'no', 'off')
                    and option(section_map.get('m300_job', ''), 'workflow_qualified', 'False').lower()
                    in ('false', '0', 'no', 'off'))
    report = dict(layout=1, thermal_sections=[], service_sections=[],
                  removed_empty_duplicates=[], removed_inactive=[], pid_macros=[])
    thermal, services, pid = [], [], []
    kept = {}
    emitted = set()
    for path, (prefix, sections, saved) in parsed.items():
        out = []
        for name, block in sections:
            lower = name.lower()
            if lower.startswith('include '):
                out.append(block)
                continue
            content = any(line.strip() and not line.lstrip().startswith(('#', ';'))
                          for line in block.splitlines()[1:])
            if len(names.get(lower, ())) > 1 and not content:
                report['removed_empty_duplicates'].append(name)
                continue
            if lower in emitted:
                continue
            emitted.add(lower)
            if retire_cycle and name == 'm300_cycle':
                report['removed_inactive'].append('m300_cycle: unqualified legacy M08')
                continue
            if retire_cycle and name == 'm300_resources':
                block = _without_option(block, 'require_cycle_owner')
            if retire_cycle and name == 'm300_job':
                block = _without_option(block, 'm08_cycle_enabled')
            if name == 'm300_maintenance':
                for key, default in (('max_jog_distance', 5.), ('jog_speed', 1.), ('fan_test_seconds', 5.)):
                    value = option(block, key)
                    if value is not None and float(value) == default:
                        block = _without_option(block, key)
                        report['removed_inactive'].append('m300_maintenance.'+key+': redundant legacy default')
            if name == 'gcode_macro ZORTRAX_PRINT':
                _, commands = gcode_body(block)
                known = ['{% if params.FILENAME is not defined %}',
                    '{action_raise_error("Select a checked file: ZORTRAX_PRINT FILENAME=...")}',
                    '{% endif %}', 'START_PRINT {rawparams}']
                if commands == known and option(section_map.get('m300_job', ''), 'workflow_qualified', 'False').lower() in ('false', '0', 'no', 'off'):
                    report['removed_inactive'].append('ZORTRAX_PRINT: disabled legacy checked-file wrapper')
                    continue
            if lower.startswith('adc_temperature '):
                # Retain every original conversion line byte-for-byte.
                thermal.append(block.rstrip()+'\n\n')
                report['thermal_sections'].append(name)
            elif name in SERVICE_SECTIONS:
                services.append(_format_block(block))
                report['service_sections'].append(name)
            elif name in PID_MACROS:
                pid.append(_format_block(block))
                report['pid_macros'].append(name)
            else:
                out.append(_format_block(block))
        kept[path] = (prefix, out, saved)
    result = {}
    for path, (prefix, out, saved) in kept.items():
        if path.name in (THERMAL_TABLES, SERVICE_CONFIG):
            if prefix and not prefix.startswith(LAYOUT_MARKER):
                raise ValueError('Refusing an unrecognized generated configuration file: '+str(path))
            if out:
                raise ValueError('Unrelated sections in generated configuration file: '+str(path))
            continue
        if path == root:
            old_prefix = prefix if not prefix.startswith(('# M300 TEST01:', '# Zortrax M300 Classic - hardware')) else ''
            prefix = ('# Zortrax M300 Classic - hardware and native Klipper settings.\n'
                      '# Procedure settings: '+SERVICE_CONFIG+'\n'
                      '# Temperature conversions: '+THERMAL_TABLES+'\n\n'+old_prefix)
        elif path.name == 'm300_fluidd.cfg' and prefix.startswith('# ZORTRAX M300 / R7.'):
            prefix = '# M300 Classic native procedures and shared Fluidd commands.\n\n'
        content = prefix+''.join(out)
        if path == root:
            for name, values in ((THERMAL_TABLES, thermal), (SERVICE_CONFIG, services)):
                include = '[include '+name+']\n'
                if values and not any(section.lower() == 'include '+name
                                      for section, _ in blocks(content)[1]):
                    # Sensors must precede heater loading. Services use native
                    # resources after the main hardware declarations.
                    if name == THERMAL_TABLES:
                        at = len(prefix)
                        content = content[:at]+include+'\n'+content[at:]
                    else:
                        content = content.rstrip()+'\n\n'+include+'\n'
        if path.name == 'klipper_calibration.cfg':
            content = '# Standard native Klipper PID calibration aliases.\n\n'+''.join(out)+''.join(pid)
        result[path] = content.rstrip()+'\n\n'+saved
    for name, data, title in ((THERMAL_TABLES, thermal, 'Original temperature conversion tables; values are unchanged.'),
                              (SERVICE_CONFIG, services, 'M300 procedure, geometry, menu and persistent-state settings.')):
        if data:
            path = root.parent/name
            if path.exists() and path not in tree:
                raise ValueError('Refusing to overwrite a non-included configuration file: '+str(path))
            result[path] = LAYOUT_MARKER+'\n# '+title+'\n\n'+''.join(data)
    calibration = root.parent/'klipper_calibration.cfg'
    if pid and calibration not in result:
        raise ValueError('Organize requires the installed klipper_calibration.cfg include')
    if split_saved(result[root])[1] != main_saved:
        raise ValueError('SAVE_CONFIG changed during layout cleanup')
    return result, report


def organize_moonraker(text, *, fluidd_config_unused=False):
    """Retire stock web updaters superseded by the verified project bundle.

    Match exact upstream repositories. Preserve server, paths, CORS and the
    effective trusted-client set; this is not a security-policy migration.
    """
    prefix, sections, saved = blocks(text)
    out, removed = [], []
    for name, block in sections:
        repo = option(block, 'repo', option(block, 'origin', ''))
        if (name == 'update_manager fluidd' and repo == 'fluidd-core/fluidd'
                and option(block, 'type') == 'web'):
            removed.append(name)
            continue
        if (name == 'update_manager fluidd-config' and fluidd_config_unused
                and repo.rstrip('/').removesuffix('.git') == 'https://github.com/fluidd-core/fluidd-config'):
            removed.append(name)
            continue
        if name == 'authorization':
            lines, seen, in_clients = [], set(), False
            for line in block.splitlines(keepends=True):
                if line and not line[0].isspace() and not line.startswith(('#', ';', '[')):
                    in_clients = bool(re.match(r'^trusted_clients\s*[:=]', line))
                if in_clients and line[:1].isspace() and line.strip() and not line.lstrip().startswith(('#', ';')):
                    value = line.strip()
                    if value in seen:
                        continue
                    seen.add(value)
                lines.append(line)
            block = ''.join(lines)
        out.append(block)
    return prefix+''.join(out)+saved, removed
