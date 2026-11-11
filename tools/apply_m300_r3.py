#!/usr/bin/env python3
"""Build R3 on reviewed M300 source; never contacts a physical printer.
Separate requested temperatures from existing ADC shutdown thresholds.
No increase to hotend limit and no guessed Micro Swiss temperature offset.
"""
import argparse, ast, hashlib, json, zipfile
from pathlib import Path

MODULE = r'''# SPDX-License-Identifier: GPL-3.0-or-later
"""One target-temperature policy for every native M300 heater entry point.

The sensor/MCU emergency limits remain unchanged. This guards set_temp and
alter_target, so G-code, Moonraker, OEM procedures and PID use the same limits.
It never owns PWM, changes sensor conversion, silently clips a target, or
qualifies the physical hotend. Micro Swiss M2580 retains the stock heater and
sensor; changing a heatbreak is not evidence for a higher safe temperature.
"""
import json
import math

REVISION = 'M300-R3-TARGET-LIMITS'
DEFAULT_TARGET_LIMITS = {'extruder': 270., 'heater_bed': 105.}


def target_limit(heater):
    """Respect a stricter native limit and leave measured-temperature checks alone."""
    return min(heater.max_temp, getattr(heater, 'm300_target_max', heater.max_temp))


def validate_target(printer, name, heater, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise printer.command_error('M300 %s: temperature must be finite' % name)
    # Zero is always available, including during a fault/stop.
    if value == 0.:
        return value
    limit = target_limit(heater)
    if not heater.min_temp <= value <= limit:
        raise printer.command_error(
            'M300 %s: requested %.2f C outside target range %.2f..%.2f C '
            '(sensor shutdown limit %.2f C)' %
            (name, value, heater.min_temp, limit, heater.max_temp))
    return value


class M300TemperaturePolicy:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.config = config
        self.gcode = self.printer.lookup_object('gcode')
        self.limits = {
            'extruder': config.getfloat('hotend_target_max', 270., minval=170., maxval=270.),
            'heater_bed': config.getfloat('bed_target_max', 105., above=0., maxval=105.),
        }
        self.heaters = {}
        self.bound = False
        self.printer.register_event_handler('klippy:connect', self._connect)
        self.gcode.register_command('ZORTRAX_TEMPERATURE_LIMITS', self.cmd_status,
                                   desc='Show target limits separately from sensor shutdown limits')

    def _connect(self):
        if self.bound:
            return
        collection = self.printer.lookup_object('heaters')
        heaters = {n: collection.lookup_heater(n) for n in self.limits}
        # Preflight the whole installation before wrapping any object.
        for name, heater in heaters.items():
            if not all(callable(getattr(heater, m, None)) for m in ('set_temp', 'alter_target')):
                raise self.config.error('M300 target policy: unsupported heater API: '+name)
            limit = min(self.limits[name], heater.max_temp)
            if not math.isfinite(limit) or limit < heater.min_temp:
                raise self.config.error('M300 target policy: invalid native heater range: '+name)
            if getattr(heater, 'target_temp', 0.) != 0.:
                raise self.config.error('M300 target policy must bind before positive heating')
        for name, heater in heaters.items():
            heater.m300_target_max = min(self.limits[name], heater.max_temp)
            for method in ('set_temp', 'alter_target'):
                original = getattr(heater, method)
                def guarded(value, original=original, name=name, heater=heater):
                    validate_target(self.printer, name, heater, value)
                    return original(value)
                setattr(heater, method, guarded)
        self.heaters = heaters
        self.bound = True

    def get_status(self, eventtime):
        return dict(revision=REVISION, bound=self.bound,
                    target_limits={n: target_limit(h) for n,h in self.heaters.items()},
                    sensor_shutdown_limits={n: h.max_temp for n,h in self.heaters.items()},
                    requested_limits=dict(self.limits), thermal_ceiling_increased=False)

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_TEMPERATURE_LIMITS '+json.dumps(
            self.get_status(0.), sort_keys=True))


def load_config(config):
    return M300TemperaturePolicy(config)
'''

REPLACEMENTS = {
 'm300_mcu.py': [
  ("        self.printer.load_object(config, 'm300_errors')", "        self.printer.load_object(config, 'm300_errors')\n        self.printer.load_object(config, 'm300_temperature_policy')")],
 'm300_print_control.py': [
  ('target and not heater.min_temp <= target <= heater.max_temp', 'target and not heater.min_temp <= target <= target_limit(heater)'),
  ('minval=minimum,maxval=heater.max_temp', 'minval=minimum,maxval=target_limit(heater)')],
 'm300_job.py': [
  ('self.standby_temp > self.hotend.max_temp', 'self.standby_temp > target_limit(self.hotend)'),
  ('or value < 0. or value > heater.max_temp', 'or value < 0. or value > target_limit(heater)')],
 'm300_filament.py': [
  ('self.standby_temperature > self.hotend.max_temp', 'self.standby_temperature > target_limit(self.hotend)'),
  ('self.hotend.min_extrude_temp <= target <= self.hotend.max_temp', 'self.hotend.min_extrude_temp <= target <= target_limit(self.hotend)')],
 'm300_calibration.py': [
  ("'temperature', self.hotend.min_extrude_temp, self.hotend.max_temp", "'temperature', self.hotend.min_extrude_temp, target_limit(self.hotend)")],
 'm300_native_maintenance.py': [
  ('heater.min_temp<=value<=heater.max_temp', 'heater.min_temp<=value<=target_limit(heater)')],
 'm300_native_motion.py': [
  ('self.hotend.min_temp < self.z_home_hotend_target < self.hotend.max_temp', 'self.hotend.min_temp < self.z_home_hotend_target < target_limit(self.hotend)')],
 'm300_pad_mesh.py': [
  ('heater.min_temp <= self.targets[name] <= heater.max_temp', 'heater.min_temp <= self.targets[name] <= target_limit(heater)')],
 'm300_zcode_policy.py': [
  ('(heater.min_temp,heater.max_temp)', '(heater.min_temp,target_limit(heater))')],
 'm300_job_sd.py': [
  ('(heater.min_temp, heater.max_temp)', '(heater.min_temp, target_limit(heater))')],
 'm300_thermal.py': [
  ('cap = 60. if check else self.heaters[heater].max_temp - 5.',
   'cap = 60. if check else min(target_limit(self.heaters[heater]), self.heaters[heater].max_temp - 5.)')],
 'm300_menu.py': [
  ("candidates = range(170, 301, 10) if kind == 'HOTEND' else range(40, 121, 10)",
   "candidates = range(170, 301, 10) if kind == 'HOTEND' else sorted(set([*range(40, 121, 10), 105]))"),
  ('heater.min_temp <= value <= heater.max_temp]', 'heater.min_temp <= value <= target_limit(heater)]')],
}

def changed(text, old, new, path):
    if new in text: return text
    if old not in text:
        raise ValueError('Unexpected source at '+str(path)+': '+old[:100])
    return text.replace(old,new)


def apply(root):
    src=root/'host/klippy/extras'
    port=root/'PORT.json'
    if port.is_file():
        meta=json.loads(port.read_text())
        if 'm300_temperature_policy.py' not in meta['host_update_files']:
            meta['host_update_files'].append('m300_temperature_policy.py')
            meta['self_contained_host_tests'] += 15
        port.write_text(json.dumps(meta,indent=2)+'\n')
    baseline_path=root/'host/update_template/SUPPORTED_BASELINES.json'
    baselines=json.loads(baseline_path.read_text())
    for filename in REPLACEMENTS:
        original=(src/filename).read_bytes()
        if b'm300_temperature_policy' not in original:
            digest=hashlib.sha256(original).hexdigest()
            baselines[filename]=sorted(set(baselines.get(filename,[])+[digest]))
    baseline_path.write_text(json.dumps(baselines,indent=2)+'\n')
    (src/'m300_temperature_policy.py').write_text(MODULE)
    for filename, pairs in REPLACEMENTS.items():
        path=src/filename;text=path.read_text()
        for old,new in pairs:text=changed(text,old,new,path)
        if filename!='m300_mcu.py' and 'from .m300_temperature_policy import target_limit' not in text:
            node=next(n for n in ast.parse(text).body if isinstance(n,(ast.Import,ast.ImportFrom)))
            lines=text.splitlines(True);lines.insert(node.lineno-1,'from .m300_temperature_policy import target_limit\n');text=''.join(lines)
        ast.parse(text);path.write_text(text)
    path=root/'host/update_template/install.py';text=path.read_text()
    text=changed(text,"NAMES += ('m300_menu_sprites.json',)","NAMES += ('m300_menu_sprites.json', 'm300_temperature_policy.py')",path);path.write_text(text)
    path=root/'host/config/m300_classic_base.cfg';text=path.read_text()
    text=changed(text,'max_temp: 120\n', '# Requested bed targets are capped at 105 C by m300_temperature_policy.\n# Keep the existing sensor/MCU emergency cutoff separate from the setpoint.\nmax_temp: 120\n',path)
    text=changed(text,'max_temp: 270\n','# Stock heater/sensor retained with Micro Swiss M2580; no higher limit is qualified.\nmax_temp: 270\n',path);path.write_text(text)
    # Same names, one process and exact field parity. Do not pretend measured
    # Micro Swiss temperatures, extrusion multipliers or PA values are known.
    bundle=root/'orca/Zortrax_M300_Classic_0p20_18_filaments.orca_printer'
    with zipfile.ZipFile(bundle) as z:
        if z.testzip():raise ValueError('Original bundle CRC failed')
        profiles={n:json.loads(z.read(n)) for n in z.namelist()}
    for path,p in profiles.items():
        if path.startswith('printer/'):
            if 'SET_PRESSURE_ADVANCE ADVANCE=0' not in p['machine_start_gcode']:
                p['machine_start_gcode']=p['machine_start_gcode'].replace('START_PRINT ', 'SET_PRESSURE_ADVANCE ADVANCE=0\nSTART_PRINT ',1)
            p['printer_notes']='M300 R3 / Micro Swiss M2580-04 preparation. Stock heater and sensor limits unchanged: nozzle 270C emergency limit, bed target <=105C. No automatic nozzle temperature offset; PID/temperature/flow/PA need measurements after assembly. M83 remains enabled. PA is explicitly zero until calibrated per filament.'
        elif path.startswith('filament/'):
            peek=p['name'].startswith('Z-PEEK ')
            p['enable_pressure_advance']=['1'];p['pressure_advance']=['0']
            p['adaptive_pressure_advance']=['0']
            for key in p:
                if '_plate_temp' in key:
                    p[key]=[str(min(float(p[key][0]),105)).removesuffix('.0')]
            if not peek and 'R3 Micro Swiss M2580:' not in p['filament_notes'][0]:
                p['filament_notes']=[p['filament_notes'][0]+' R3 Micro Swiss M2580: no unmeasured temperature offset. PA=0 is an explicit neutral setting, NOT calibration. Keep bed target <=105C.']
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,p in profiles.items():
            info=zipfile.ZipInfo(name,(2026,11,11,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,json.dumps(p,ensure_ascii=False,indent=4)+'\n')
    with zipfile.ZipFile(bundle) as z:
        if z.testzip():raise AssertionError('Generated CRC failed')
    payload=root/'host/update_template/payload'
    if payload.is_dir():
        for path in src.iterdir():
            if path.is_file():(payload/path.name).write_bytes(path.read_bytes())
    return hashlib.sha256(bundle.read_bytes()).hexdigest()

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path.cwd());a=ap.parse_args()
    print('R3_BUNDLE_SHA256='+apply(a.root.resolve()))
