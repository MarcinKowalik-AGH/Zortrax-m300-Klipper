"""Synthetic factory record for actual Klippy FILEOUTPUT tests only.

CI copies this file to its generated Klippy tree. It is never a host payload.
It uses the production identity/apply path, native C stepper solver and M07.
"""
import json


class Fixture:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.board = self.printer.lookup_object('m300_mcu')
        if not self.board.mcu.is_fileoutput():
            raise config.error('CI factory fixture is FILEOUTPUT-only')
        self.header = config.getint('header')
        self.raw = config.getint('raw')
        self.expected_steps = config.getint('expected_steps')
        self.start = None
        self.printer.register_event_handler('klippy:mcu_identify', self._identify)
        self.printer.lookup_object('gcode').register_command(
            'ZORTRAX_CI_SCALE_CHECK', self.check)

    def _identify(self):
        from .m300_hardware import decode_factory
        identity = decode_factory(self.header, self.raw)
        assert self.board.hardware.state == 'FILEOUTPUT_NO_FACTORY_READ'
        packet = dict(header=self.header, raw=self.raw, valid=int(identity['valid']),
                      revision=identity['revision'] or 0,
                      z_steps=identity['z_steps_per_mm'] or 0)
        try:
            self.board.hardware._apply_identity(packet)
        except ValueError as exc:
            raise self.printer.config_error('CI synthetic factory record: ' + str(exc)) from None

    def check(self, gcmd):
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.flush_step_generation()
        kin = toolhead.get_kinematics()
        stepper = next(s for s in kin.get_steppers() if s.get_name() == 'stepper_z')
        if gcmd.get('MODE', 'END') == 'START':
            self.start = stepper.get_mcu_position()
            return
        actual = stepper.get_mcu_position() - self.start
        m07 = self.printer.lookup_object('m300_calibration').machine.stock_steps_per_mm
        assert actual == self.expected_steps, (actual, self.expected_steps)
        assert abs(stepper.get_step_dist() * self.expected_steps - 1) < 1e-9
        assert m07 == self.expected_steps, (m07, self.expected_steps)
        gcmd.respond_info('M300_CI_FACTORY ' + json.dumps({
            'native_steps_for_1mm': actual, 'M07_steps_per_mm': m07,
            'synthetic_factory_record': True, 'physical_hardware': False}))


def load_config(config):
    return Fixture(config)
