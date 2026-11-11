# SPDX-License-Identifier: GPL-3.0-or-later
"""305/105C normal-operation target policy. User reports successful hardware
operation2026-11-11; software tests do not claim physical validation.
Separate measured-temperature cutoffs310/120 fit the unchanged independent
MCU ADC guard1941/1741/3941. No PWM, sensor conversion or motion changes.
"""
import json
import math

REVISION = 'M300-305-105-R1'
DEFAULT_TARGET_LIMITS = {'extruder': 305., 'heater_bed': 105.}


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
            'extruder': config.getfloat('hotend_target_max', 305., minval=170., maxval=305.),
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
                    requested_limits=dict(self.limits),
                    hardware_validation='USER_REPORTED_2026-11-11',
                    user_reported_targets={'extruder': 305., 'heater_bed': 105.},
                    automated_hardware_test=False,
                    independent_mcu_guard_changed=False)

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_TEMPERATURE_LIMITS '+json.dumps(
            self.get_status(0.), sort_keys=True))


def load_config(config):
    return M300TemperaturePolicy(config)
