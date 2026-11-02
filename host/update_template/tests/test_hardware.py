"""Factory scale selection, transport capability errors and startup boundaries."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

import test_display  # staged payload imports
from payload.m300_hardware import (M300Hardware, FACTORY_HEADER, FACTORY_ADDRESS,
                                   decode_factory)
from payload.m300_motion import Z400_CONTRACT, z400_contract_check


def packet(raw=0xe5, header=FACTORY_HEADER):
    identity = decode_factory(header, raw)
    return dict(header=header, raw=raw, valid=int(identity['valid']),
                revision=identity['revision'] or 0, z_steps=identity['z_steps_per_mm'] or 0)


def fixture(profile='factory', fileoutput=False):
    class Config:
        options = {'microsteps': 16, 'full_steps_per_rotation': 200,
                   'gear_ratio': '', 'step_pin': 'PB7'}
        error = RuntimeError
        def getchoice(self, name, choices, default):
            return profile
        def getsection(self, name):
            return self
        def getint(self, name, default=None):
            return self.options.get(name, default)
        def get(self, name, default=None):
            return self.options.get(name, default)
    config = Config()
    config.options = dict(config.options)
    mcu = NS(is_fileoutput=lambda: fileoutput,
             _config_helper=NS(is_config_finalized=lambda: False),
             get_constants=lambda: {'M300_FACTORY_ABI': 1,
                                    'M300_FACTORY_HW_ADDRESS': FACTORY_ADDRESS,
                                    'M300_MODEL': 'M300_CLASSIC'},
             check_valid_response=lambda fmt: True)
    class Stepper:
        rotation = 8.
        changes = 0
        get_name = lambda self: 'stepper_z'
        get_mcu = lambda self: mcu
        get_rotation_distance = lambda self: (self.rotation, 3200)
        def set_rotation_distance(self, value):
            self.rotation, self.changes = value, self.changes + 1
    stepper = Stepper()
    kin = NS(get_steppers=lambda: [stepper])
    toolhead = NS(get_kinematics=lambda: kin,
                  get_status=lambda now: {'homed_axes': ''})
    printer = NS(lookup_object=lambda name: toolhead,
                 get_reactor=lambda: NS(monotonic=lambda: 1.),
                 register_event_handler=Mock())
    board = NS(printer=printer, mcu=mcu, mcu_name='mcu',
               gcode=NS(register_command=Mock()))
    hw = M300Hardware(board, config)
    hw._query_factory = Mock(return_value=packet())
    return hw, stepper, config


class DecoderTests(unittest.TestCase):
    def test_all_byte_values_and_both_sides_of_revision_boundary(self):
        for raw in range(256):
            decoded = decode_factory(FACTORY_HEADER, raw)
            valid = 0xe0 <= raw < 0xff
            self.assertEqual(decoded['valid'], valid, raw)
            if valid:
                self.assertEqual(decoded['revision'], raw - 0xe0)
                self.assertEqual(decoded['z_steps_per_mm'], 800 if raw < 0xe5 else 400)
            else:
                self.assertIsNone(decoded['z_steps_per_mm'])

    def test_erased_wrong_id_wrong_length_and_endian_headers(self):
        for header in (0xffffffff, 0xaabb0003, 0xaabb0203, 0xaabb0102, 0x0301bbaa):
            self.assertFalse(decode_factory(header, 0xe5)['valid'])

    def test_invalid_protocol_number_types_and_ranges(self):
        for header, raw in ((True, 0xe5), (FACTORY_HEADER, True),
                            (-1, 0xe5), (2**32, 0xe5),
                            (FACTORY_HEADER, -1), (FACTORY_HEADER, 256)):
            with self.assertRaises(ValueError):
                decode_factory(header, raw)


class HardwareTests(unittest.TestCase):
    def test_hw05_selects_400_without_writing_configuration(self):
        hw, stepper, config = fixture()
        before = dict(config.options)
        hw._identify()
        self.assertEqual(stepper.rotation, 8.)
        self.assertEqual(hw.selected_z_steps(), 400)
        self.assertEqual(hw.get_status()['hardware_label'], 'HW05')
        self.assertEqual(config.options, before)

    def test_hw04_selects_800_from_the_same_application(self):
        hw, stepper, _ = fixture()
        hw._query_factory.return_value = packet(0xe4)
        hw._identify()
        self.assertEqual(stepper.rotation, 4.)
        self.assertEqual(hw.get_status()['configured_rotation_distance'], 8.)
        self.assertEqual(hw.get_status()['effective_z_steps_per_mm'], 800)

    def test_query_is_once_without_runtime_polling_or_registered_motion_hooks(self):
        hw, _, _ = fixture()
        hw._identify()
        hw.get_status(); hw.get_status()
        hw._query_factory.assert_called_once_with()
        events = hw.printer.register_event_handler.call_args_list
        self.assertEqual([call.args[0] for call in events], ['klippy:mcu_identify'])

    def test_broken_or_erased_record_never_changes_step_scale(self):
        for response in (packet(0xff), packet(0xe5, 0xffffffff), packet(0xdf)):
            hw, stepper, _ = fixture()
            hw._query_factory.return_value = response
            with self.assertRaisesRegex(RuntimeError, 'missing/corrupt'):
                hw._identify()
            self.assertEqual(stepper.changes, 0)
            self.assertFalse(hw.applied)

    def test_inconsistent_telemetry_is_rejected(self):
        hw, stepper, _ = fixture()
        hw._query_factory.return_value = dict(packet(0xe4), z_steps=400)
        with self.assertRaisesRegex(RuntimeError, 'disagrees'):
            hw._identify()
        self.assertEqual(stepper.changes, 0)

    def test_config_override_reports_hw04_but_keeps_operator_scale(self):
        hw, stepper, _ = fixture('config')
        hw._query_factory.return_value = packet(0xe4)
        hw._identify()
        self.assertEqual(hw.get_status()['stock_z_steps_per_mm'], 800)
        self.assertEqual(hw.get_status()['effective_z_steps_per_mm'], 400)
        self.assertIsNone(hw.selected_z_steps())
        self.assertEqual(stepper.changes, 0)

    def test_config_override_does_not_interpret_missing_record_as_hw05(self):
        hw, stepper, _ = fixture('config')
        hw._query_factory.return_value = packet(0xff, 0xffffffff)
        hw._identify()
        self.assertEqual(hw.state, 'CONFIG_OVERRIDE')
        self.assertIsNone(hw.get_status()['hardware_label'])
        self.assertEqual(stepper.changes, 0)

    def test_old_mcu_requires_matching_application_in_factory_mode(self):
        hw, stepper, _ = fixture()
        hw.mcu.get_constants = lambda: {}
        with self.assertRaisesRegex(RuntimeError, 'R14.5'):
            hw._identify()
        hw._query_factory.assert_not_called()
        self.assertEqual(stepper.changes, 0)

    def test_old_mcu_remains_usable_with_explicit_configuration_override(self):
        hw, stepper, _ = fixture('config')
        hw.mcu.get_constants = lambda: {}
        hw._identify()
        self.assertEqual(hw.state, 'MCU_FACTORY_ABI_UNAVAILABLE')
        self.assertEqual(stepper.changes, 0)

    def test_fileoutput_does_not_fabricate_factory_or_uart_evidence(self):
        hw, stepper, _ = fixture(fileoutput=True)
        hw._identify()
        hw._query_factory.assert_not_called()
        self.assertEqual(hw.state, 'FILEOUTPUT_NO_FACTORY_READ')
        self.assertFalse(hw.factory['valid'])
        self.assertEqual(stepper.changes, 0)

    def test_timeout_reports_error_and_never_applies_scale(self):
        hw, stepper, _ = fixture()
        hw._query_factory.side_effect = RuntimeError('no MCU response')
        with self.assertRaisesRegex(RuntimeError, 'no MCU response'):
            hw._identify()
        self.assertEqual(hw.state, 'ERROR')
        self.assertEqual(stepper.changes, 0)

    def test_cannot_apply_to_a_finalized_mcu_or_a_homed_frame(self):
        for finalized in (True, False):
            hw, stepper, _ = fixture()
            hw.mcu._config_helper.is_config_finalized = lambda: finalized
            if not finalized:
                hw.printer.lookup_object('toolhead').get_status = lambda now: {'homed_axes': 'z'}
            with self.assertRaises(RuntimeError):
                hw._identify()
            self.assertEqual(stepper.changes, 0)

    def test_wrong_microsteps_fullsteps_pin_or_gearing_is_not_hidden(self):
        for key, value in (('microsteps', 32), ('full_steps_per_rotation', 400),
                           ('gear_ratio', '2:1'), ('step_pin', 'PB4')):
            hw, stepper, config = fixture()
            config.options[key] = value
            with self.assertRaisesRegex(RuntimeError, 'factory Z requires'):
                hw._identify()
            self.assertEqual(stepper.changes, 0)

    def test_mismatched_native_steps_per_rotation_is_rejected(self):
        hw, stepper, _ = fixture()
        stepper.get_rotation_distance = lambda: (8., 6400)
        with self.assertRaisesRegex(RuntimeError, '3200'):
            hw._identify()
        self.assertEqual(stepper.changes, 0)

    def test_reconnect_uses_a_new_read_instead_of_previous_identity(self):
        old, _, _ = fixture()
        old._identify()
        new, stepper, _ = fixture()
        new._query_factory.return_value = packet(0xe4)
        new._identify()
        self.assertEqual(stepper.rotation, 4.)
        self.assertEqual(old.selected_z_steps(), 400)
        self.assertEqual(new.selected_z_steps(), 800)

    def test_commissioning_contract_accepts_both_scales_without_changing_limits(self):
        for scale in (400, 800):
            values = dict(Z400_CONTRACT)
            values['stepper_z', 'rotation_distance'] = 3200. / scale
            values['m300_calibration', 'stock_steps_per_mm'] = scale
            report = z400_contract_check(values, scale)
            self.assertEqual(report['configured_steps_per_mm'], scale)
            self.assertEqual(report['z_soft_max_mm'], 30)
        with self.assertRaises(ValueError):
            z400_contract_check(dict(Z400_CONTRACT), 800)


if __name__ == '__main__':
    unittest.main()
