"""Optional die temperature: capabilities, freshness and diagnostic isolation."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from payload.m300_mcu_temperature import M300MCUTemperature, temperature_from_adc, GRAPH_SENSOR


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
    if settings.pop('existing_graph', False):
        objects[GRAPH_SENSOR] = object()
    heaters = NS(register_sensor=Mock())
    printer = NS(get_reactor=lambda: reactor, lookup_object=lambda n, default=None: objects.get(n, default),
                 add_object=lambda n, obj: objects.__setitem__(n, obj),
                 load_object=lambda cfg, n: objects.setdefault(n, heaters),
                 register_event_handler=Mock(), config_error=RuntimeError, command_error=RuntimeError)
    config = NS(get_printer=lambda: printer, error=RuntimeError,
                getfloat=lambda n, default, **kw: settings.get(n, default),
                getboolean=lambda n, default: settings.get(n, default),
                getsection=lambda n: NS(get_name=lambda: n))
    module = M300MCUTemperature(config)
    return module, clock, adc, pins, objects


class MCUTemperatureTest(unittest.TestCase):
    def test_nominal_transfer_and_sign(self):
        self.assertAlmostEqual(temperature_from_adc(1.43/3.3, 3.3, 0.), 25.)
        self.assertAlmostEqual(temperature_from_adc((1.43-.0043*50)/3.3, 3.3, 0.), 75.)

    def test_only_internal_native_adc_no_heater_or_extra_series(self):
        module, clock, adc, pins, objects = fixture(show_on_graph=False)
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

    def test_graph_uses_one_adc_and_standard_sensor_name(self):
        module, clock, adc, pins, objects = fixture()
        self.assertEqual(pins.setup_pin.call_count, 1)
        self.assertIn(GRAPH_SENSOR, objects)
        section, view = objects['heaters'].register_sensor.call_args[0]
        self.assertEqual(section.get_name(), GRAPH_SENSOR)
        self.assertIs(view.source, module)
        self.assertTrue(module.get_status(100.)['graph_series'])

    def test_graph_returns_same_reading_and_extrema(self):
        module, clock, adc, pins, objects = fixture()
        view = objects[GRAPH_SENSOR]
        module._identify();module._receive([(100., 1.43/3.3)])
        self.assertAlmostEqual(view.get_temp(100.)[0], 25.)
        self.assertEqual(view.get_status(100.)['temperature'], module.get_status(100.)['temperature'])
        clock[0]=105.;module._receive([(105., (1.43-.0043*10)/3.3)])
        self.assertAlmostEqual(view.get_status(105.)['measured_max_temp'], 35.)
        self.assertAlmostEqual(view.get_status(105.)['measured_min_temp'], 25.)

    def test_graph_does_not_publish_stale_or_shutdown_temperature(self):
        module, clock, adc, pins, objects = fixture()
        view = objects[GRAPH_SENSOR]
        module._identify();module._receive([(100., 1.43/3.3)])
        self.assertIsNone(view.get_status(116.)['temperature'])
        with self.assertRaisesRegex(RuntimeError, 'fresh sample'):
            view.get_temp(116.)
        module._shutdown()
        self.assertIsNone(view.get_status(100.)['temperature'])

    def test_graph_name_collision_is_explicit(self):
        with self.assertRaisesRegex(RuntimeError, 'already in use'):
            fixture(existing_graph=True)


if __name__ == '__main__':
    unittest.main()
