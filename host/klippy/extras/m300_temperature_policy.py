# SPDX-License-Identifier: GPL-3.0-or-later
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
