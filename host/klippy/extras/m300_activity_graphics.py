# SPDX-License-Identifier: GPL-3.0-or-later
"""Semantic OLED artwork selected from existing cached status, without control I/O."""
import base64
from collections import namedtuple
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import zlib

Symbol = namedtuple('Symbol', 'key animated')
PREFIX = 'activity:'
TERMINAL = frozenset(('COMPLETE', 'CANCELLED', 'CANCELLING', 'FAULT', 'ERROR', 'FAILED', 'IDLE'))
FAULT_STATES = frozenset(('FAULT', 'ERROR', 'FAILED', 'SHUTDOWN'))


def symbol(name, animated=False):
    return Symbol(PREFIX+name, bool(animated))


class ActivityGraphics:
    """Decode only visible frames; at most 32 native 1,250-byte frames cached."""
    def __init__(self, path=None):
        path = path or Path(__file__).with_name('m300_activity_sprites.json')
        self.spec = json.loads(Path(path).read_text())
        if (self.spec.get('format') != 'M300_ACTIVITY_SPRITES_V1'
                or len(self.spec.get('symbols', {})) != 24):
            raise ValueError('Invalid M300 activity artwork catalog')
        for record in self.spec['symbols'].values():
            if ((record.get('width'), record.get('height'), record.get('frame_ms')) != (50,50,500)
                    or len(record.get('frames', ())) != 4):
                raise ValueError('Invalid M300 activity animation metadata')

    def get(self, key, now=0.):
        name = key[len(PREFIX):] if key.startswith(PREFIX) else key
        record = self.spec['symbols'].get(name)
        if record is None:
            return None
        now = float(now)
        if not math.isfinite(now):
            now = 0.
        index = int(max(0., now)*1000 // record['frame_ms']) % len(record['frames'])
        return self._frame(name, index)

    @lru_cache(maxsize=32)
    def _frame(self, name, index):
        record = self.spec['symbols'][name]
        frame = record['frames'][index]
        raw = zlib.decompress(base64.b64decode(frame['zlib_b64'], validate=True))
        if (record['width'], record['height'], len(raw)) != (50, 50, 1250):
            raise ValueError('Invalid M300 activity frame geometry')
        if hashlib.sha256(raw).hexdigest() != frame['sha256']:
            raise ValueError('M300 activity frame integrity mismatch')
        return 50, 50, raw


def fault_symbol(status):
    """Explain a reported failure; this never detects or raises a new fault."""
    if not status or str(status.get('state', '')).upper() not in FAULT_STATES:
        return None
    reason = ' '.join(str(status.get(key) or '') for key in
                      ('fault_code', 'error_code', 'reason', 'last_error', 'error')).lower()[:1024]
    normalized = reason.replace('_', ' ').replace('-', ' ')
    if status.get('platform_connector_fault') is True or any(word in normalized for word in
            ('platform connector', 'platform cable', 'bed connector')):
        return symbol('platform_connector', True)
    if status.get('filament_jam') is True or any(word in normalized for word in
            ('filament jam', 'filament stuck', 'extruder jam')):
        return symbol('filament_jam', True)
    if status.get('filament_runout') is True or 'filament runout' in normalized:
        return symbol('filament_runout', True)
    if any(word in normalized for word in ('emergency stop', 'm112', 'e stop')):
        return symbol('emergency_stop', True)
    if any(word in normalized for word in ('overheat', 'overtemp', 'max temp', 'maximum temperature')):
        heater = str(status.get('heater') or status.get('operation') or '').lower()
        return symbol('bed_overheat' if 'bed' in heater or 'bed' in normalized else 'hotend_overheat', True)
    if any(word in normalized for word in ('thermistor', 'adc out of range', 'sensor fault',
                                          'temperature sensor', 'invalid adc', 'heater feedback failed')):
        return symbol('sensor_fault', True)
    if any(word in normalized for word in ('heating failed', 'not heating', 'heater not',
                                          'heating timeout', 'heating timed out')):
        return symbol('heating_failed', True)
    if any(word in normalized for word in ('pc7', 'probe', 'trigger', 'no release', 'contact')):
        return symbol('probe_contact_fault', True)
    if any(word in normalized for word in ('connection lost', 'mcu disconnected', 'host disconnected')):
        return symbol('connection_lost', True)
    return None


def procedure_symbol(owner, status):
    fault = fault_symbol(status)
    if fault:
        return fault
    state = status.get('state', '')
    if state in TERMINAL:
        return None
    if status.get('can_confirm_resume_clean') is True or state in ('WAIT_CLEAN', 'WAIT_CLEAN_NOZZLE'):
        return symbol('clean_nozzle', True)
    if owner == 'm300_pad_mesh':
        return symbol('bed_mesh', status.get('busy') is True)
    if owner == 'm300_maintenance' and status.get('operation') in ('PLATFORM_UP', 'PLATFORM_DOWN'):
        return Symbol('0x0801cb24' if status['operation']=='PLATFORM_UP' else '0x0801cc24',
                      status.get('busy') is True and state == 'MOVING')
    if owner in ('m300_maintenance', 'm300_filament', 'm300_thermal', 'm300_job'):
        if state in ('HEATING', 'REHEATING', 'WAIT_HEAT', 'CHECK_HEATING', 'PID_RUNNING'):
            heater = str(status.get('heater') or status.get('operation') or '').upper()
            return symbol('heat_bed' if heater in ('BED', 'HEATER_BED') else 'heat_nozzle', True)
        if state in ('COOLING', 'WAIT_COOL', 'CHECK_COAST'):
            return symbol('cooling', True)
    return None


PAGE_SYMBOLS = {
    'info_printer': '0x0801dc08', 'info_firmware': PREFIX+'firmware_update',
    'setting_oled_brightness': PREFIX+'oled_brightness',
    'setting_led_brightness': PREFIX+'led_brightness',
    'setting_light_mode': '0x0801d55c', 'setting_sound': '0x0801d72c',
    'setting_sleep_mode': '0x0801d908', 'setting_language': '0x0801dab4',
    'setting_sort_mode': '0x0801c4f4', 'native_pid': PREFIX+'heat_nozzle',
    'native_moves': '0x0801cb24', 'native_move_x': '0x0801cb24',
    'native_move_y': '0x0801cb24', 'native_move_z': '0x0801cb24',
    'bed_mesh': PREFIX+'bed_mesh', 'fans': PREFIX+'fan_upper',
    'sd_status': PREFIX+'sd_read', 'board': PREFIX+'link_status',
    'oled_link': PREFIX+'link_status', 'inputs': '0x0801dc08', 'temps': PREFIX+'heat_nozzle',
    'diagnostics': '0x0801c958', 'tests': '0x0801c958',
    'service_status': '0x0801c958', 'native_job': '0x08020fb8',
}


def menu_symbol(page, panel_page, rows=(), selected=0, *, fan=None, browser=None, sd=None, models=None):
    """Menu previews are static. Only a reported active fan or file I/O animates."""
    if page == 'fan_test':
        fan = fan or {}
        channel = 'lower' if selected == 2 else 'upper'
        enabled = fan.get(channel+'_enabled') is True or channel == 'upper' and fan.get('upper_cooling') is True
        return symbol('fan_'+channel, enabled and selected in (1, 2) and fan.get('busy') is True)
    if page == 'fans':
        fan = fan or {}
        action = rows[selected][1] if rows and 0<=selected<len(rows) else None
        lower = selected in (2,3) or isinstance(action,tuple) and action[0]=='fan_set'
        duty = (fan.get('channels', {}).get('print' if lower else 'hotend', {}).get('effective_duty'))
        enabled = type(duty) in (int,float) and duty>0 and fan.get('mcu_status_fresh') is True
        return symbol('fan_lower' if lower else 'fan_upper', enabled and selected != 0)
    if panel_page == 'temps':
        return symbol('heat_bed' if selected == 2 else 'heat_nozzle')
    if page in ('models', 'browser', 'model_file', 'preview', 'confirm_print'):
        sd, browser, models = sd or {}, browser or {}, models or {}
        if page in ('model_file', 'preview', 'confirm_print') and models.get('state')=='ERROR':
            return fault_symbol(models) or Symbol('0x0801be48',False)
        if sd.get('busy') is True:
            return symbol('sd_read', True)
        if models.get('busy') is True:
            return symbol('file_convert', True)
        if browser.get('busy') is True:
            return symbol('file_convert' if page in ('model_file', 'preview', 'confirm_print') else 'sd_read', True)
        if page == 'browser' and browser.get('source') == 'sd':
            return symbol('sd_read')
    action = rows[selected][1] if rows and 0 <= selected < len(rows) else None
    if isinstance(action, tuple) and action:
        kind = action[0]
        target = action[1] if len(action)>1 else None
        if kind == 'page' and target in PAGE_SYMBOLS:
            return Symbol(PAGE_SYMBOLS[target], False)
        if kind == 'browse' and target == 'sd':
            return symbol('sd_read')
        if kind == 'fan_set' or kind == 'fan_test' and target == 'PRINT':
            return symbol('fan_lower')
        if kind == 'fan_test' and target == 'HOTEND':
            return symbol('fan_upper')
        if kind == 'service' and target in ('FAN_PRINT', 'FAN_HOTEND'):
            return symbol('fan_lower' if target=='FAN_PRINT' else 'fan_upper')
        if (kind == 'service' and target in ('HOTEND', 'BED')) or kind == 'temperatures':
            return symbol('heat_bed' if target == 'BED' else 'heat_nozzle')
        if kind == 'native_gcode':
            command = str(target).strip().upper()
            name = command.split(maxsplit=1)[0] if command else ''
            if name in ('ZORTRAX_BED_MESH', 'M300_PAD_MESH_CALIBRATE', 'BED_MESH_CALIBRATE'):
                return symbol('bed_mesh')
            if name in ('ZORTRAX_HEAT', 'M104', 'M109'):
                return symbol('heat_nozzle')
            if name in ('M140', 'M190') or name == 'PID_CALIBRATE' and 'HEATER=HEATER_BED' in command:
                return symbol('heat_bed')
            if name == 'PID_CALIBRATE':
                return symbol('heat_nozzle')
            if name in ('TURN_OFF_HEATERS', 'ZORTRAX_COOL'):
                return symbol('cooling')
            if name in ('ZORTRAX_FAN_TEST_START', 'ZORTRAX_FAN_UPPER', 'ZORTRAX_FANS'):
                return symbol('fan_upper')
            if name == 'ZORTRAX_FAN_LOWER':
                return symbol('fan_lower')
            if name in ('FIRMWARE_RESTART', 'RESTART', 'SAVE_CONFIG'):
                return symbol('firmware_update')
            if name == 'M112':
                return symbol('emergency_stop')
    key = PAGE_SYMBOLS.get(page) or PAGE_SYMBOLS.get(panel_page)
    return Symbol(key, False) if key else None
