"""FILEOUTPUT-only introspection of the target guard and its native backends.

Never changes heater targets, pins, motion or runtime policy. This module is
copied only into the isolated CI host, never into a release's runtime.
"""
import json
import logging
from . import heaters


class ThermalBindings:
    def __init__(self, config):
        self.printer = config.get_printer()
        if not self.printer.lookup_object('mcu').is_fileoutput():
            raise config.error('Thermal binding inspection requires FILEOUTPUT')
        self.printer.register_event_handler('klippy:ready', self.check)

    def check(self):
        policy = self.printer.lookup_object('m300_temperature_policy')
        assert policy.bound
        checked = []
        for name in ('extruder', 'heater_bed'):
            heater = self.printer.lookup_object('heaters').lookup_heater(name)
            assert policy.heaters[name] is heater
            for method in ('set_temp', 'alter_target'):
                guarded = getattr(heater, method)
                assert guarded.__module__ == 'extras.m300_temperature_policy'
                assert guarded.__qualname__ == 'M300TemperaturePolicy._connect.<locals>.guarded'
                original, bound_name, bound_heater = guarded.__defaults__
                assert bound_name == name and bound_heater is heater
                assert original.__self__ is heater
                assert original.__func__ is getattr(heaters.Heater, method)
                checked.append(name + '.' + method)
        logging.info('M300_CI_THERMAL_BINDINGS %s', json.dumps({
            'native_backends': checked, 'PASS': True,
            'targets_changed': False, 'physical_hardware': False}, sort_keys=True))


def load_config(config):
    return ThermalBindings(config)
