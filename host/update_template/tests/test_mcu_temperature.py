"""Optional die temperature: capabilities, freshness and diagnostic isolation."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from payload.m300_mcu_temperature import M300MCUTemperature, temperature_from_adc


def fixture(constants=None, **settings):
    clock = [100.]
    reactor = NS(monotonic=lambda: clock[0])
    mcu = NS(get_constants=lambda: constants if constants is not None else {
        'MCU': 'stm32f103xe', 'M300_MCU_TEMPERATURE_ABI': 1},
        estimated_print_time=lambda now: now)
    adc = NS(get_mcu=lambda: mcu, setup_adc_sample=Mock(), setup_adc_callback=Mock())
    pins = NS(setup_pin=Mock(return_value=adc))
    gcode = NS(register_command=Mock())
    objects = {'pins': pins, 'gcode': gcode}
    printer = NS(get_reactor=lambda: reactor, lookup_object=lambda n: objects[n],
                 register_event_handler=Mock(), config_error=RuntimeError)
    config = NS(get_printer=lambda: printer, error=RuntimeError,
                getfloat=lambda n, default, **kw: settings.get(n, default))
    module = M300MCUTemperature(config)
    return module, clock, adc, pins, objects


class MCUTemperatureTest(unittest.TestCase):
    def test_nominal_transfer_and_sign(self):
        self.assertAlmostEqual(temperature_from_adc(1.43/3.3, 3.3, 0.), 25.)
        self.assertAlmostEqual(temperature_from_adc((1.43-.0043*50)/3.3, 3.3, 0.), 75.)

    def test_only_internal_native_adc_no_heater_or_extra_series(self):
        module, clock, adc, pins, objects = fixture()
        pins.setup_pin.assert_called_once_with('adc', 'mcu:ADC_TEMPERATURE')
        adc.setup_adc_sample.assert_called_once_with(5., .001, 8,
                                                    minval=0., maxval=1., range_check_count=0)
        self.assertNotIn('heaters', objects)

    def test_rejects_old_firmware_before_ready(self):
        module, *_ = fixture({'MCU': 'stm32f103xe'})
        with self.assertRaisesRegex(RuntimeError, '1.0.9'):
            module._identify()

    def test_rejects_wrong_chip_family(self):
        module, *_ = fixture({'MCU': 'stm32f207', 'M300_MCU_TEMPERATURE_ABI': 1})
        with self.assertRaises(RuntimeError):
            module._identify()

    def test_valid_sample_and_calibration_offset(self):
        module, clock, *_ = fixture(adc_voltage=3.27, temperature_offset=2.)
        module._identify();module._receive([(100., 1.43/3.27)])
        self.assertAlmostEqual(module.get_status(100.)['temperature'], 27.)
        self.assertEqual(module.get_status(100.)['state'], 'READY')

    def test_stale_reading_is_not_presented_as_current(self):
        module, clock, *_ = fixture()
        module._identify();module._receive([(100., 1.43/3.3)])
        self.assertIsNone(module.get_status(116.)['temperature'])
        self.assertEqual(module.get_status(116.)['state'], 'STALE')

    def test_rails_and_nonfinite_values_are_diagnostic_failures(self):
        for value in (0., 1., float('nan'), float('inf')):
            module, *_ = fixture()
            module._identify();module._receive([(100., value)])
            self.assertEqual(module.get_status(100.)['state'], 'INVALID_ADC')
            self.assertIsNone(module.get_status(100.)['temperature'])

    def test_late_or_future_sample_cannot_refresh_status(self):
        for read_time in (1., 102., float('nan')):
            module, *_ = fixture()
            module._identify();module._receive([(read_time, .43)])
            self.assertEqual(module.get_status(100.)['state'], 'STALE')

    def test_shutdown_disconnect_and_command_no_actuator_requests(self):
        module, *_ = fixture()
        module._identify();module._receive([(100., .43)])
        module._shutdown();module._receive([(100., .43)])
        self.assertIsNone(module.get_status(100.)['temperature'])
        module._disconnect()
        gcmd = NS(respond_info=Mock());module.cmd_temperature(gcmd)
        self.assertIn('DISCONNECTED', gcmd.respond_info.call_args[0][0])

    def test_nonfinite_calibration_is_rejected(self):
        for setting in ('report_time', 'adc_voltage', 'temperature_offset'):
            with self.assertRaisesRegex(RuntimeError, 'finite'):
                fixture(**{setting: float('nan')})

    def test_delayed_sample_preserves_measurement_age(self):
        module, clock, *_ = fixture()
        module._identify();module._receive([(90., 1.43/3.3)])
        self.assertEqual(module.get_status(100.)['sample_age'], 10.)
        self.assertIsNone(module.get_status(106.)['temperature'])


if __name__ == '__main__':
    unittest.main()
