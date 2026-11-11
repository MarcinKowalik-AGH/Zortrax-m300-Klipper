"""Fault injection at procedure boundaries and the shared error dispatcher."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from test_oem_errors import errors_session
from test_normal_operations import motion_fixture
from payload.m300_error_codes import report, SHUTDOWN
from payload.m300_thermal import M300Thermal
from payload.m300_models import M300Models
from tests.reference.native_gcode import CommandError


def thermal(h):
    t = M300Thermal.__new__(M300Thermal)
    t.printer, t.reactor = h.printer, h.reactor
    t.running_native, t.active, t.phase = False, True, 1
    t.state, t.reason = 'CHECK_HEATING', ''
    t.heaters = dict(extruder=h.hotend, heater_bed=h.bed)
    t.board = NS(get_mcu=lambda: NS(estimated_print_time=lambda now: now))
    for heater in t.heaters.values():
        heater.set_pwm = Mock()
        heater.set_temp(60.)
    return t


class ProcedureErrorsTests(unittest.TestCase):
    def test_filament_fault_reports_original_cause_before_shutdown_and_cuts_heat(self):
        with errors_session() as h:
            h.run('ZORTRAX_LOAD')
            h.f._fault('native material queue drain deadline expired')
            record = h.errors.current
            self.assertEqual(record['source'], 'm300_filament')
            self.assertEqual(record['reason'], 'native material queue drain deadline expired')
            self.assertEqual(record['code'], 0)  # No invented jam/gear diagnosis.
            self.assertTrue(record['fatal'])
            self.assertTrue(h.shutdown)
            self.assertEqual(h.hotend.target, 0.)
            h.f._shutdown()
            h.errors._shutdown('M300 filament fault: ' + record['reason'], {})
            self.assertEqual(h.errors.current['id'], record['id'])

    def test_reporting_failure_cannot_prevent_homing_heater_cleanup(self):
        m = motion_fixture()
        m.native_G28 = Mock(side_effect=RuntimeError('Probe triggered prior to movement'))
        errors = NS(record=Mock(side_effect=RuntimeError('observer failed')), current=None)
        m.printer.lookup_object = lambda name, default=None: errors if name == 'm300_errors' else default
        with self.assertLogs(level='ERROR'), self.assertRaisesRegex(RuntimeError, 'Probe triggered'):
            m.home(axes='z')
        self.assertEqual(m.hotend.target, 0.)
        self.assertEqual(m.state, 'FAULT')

    def test_reporting_failure_cannot_prevent_native_maintenance_shutdown(self):
        with errors_session() as h:
            h.run('ZORTRAX_HEAT')
            h.errors.record = Mock(side_effect=RuntimeError('observer failed'))
            with self.assertLogs(level='ERROR'):
                h.m._fault('native move failed')
            self.assertTrue(h.shutdown)
            self.assertEqual(h.hotend.target, 0.)

    def test_fan_output_failure_reports_and_requests_protective_shutdown(self):
        with errors_session() as h:
            h.fans._print_async = Mock(side_effect=RuntimeError('PWM queue failed'))
            with self.assertRaisesRegex(RuntimeError, 'PWM queue failed'):
                h.fans.start_oem()
            self.assertTrue(h.shutdown)
            self.assertEqual(h.errors.current['source'], 'm300_fans')
            self.assertIn('PWM queue failed', h.errors.current['reason'])
            self.assertTrue(h.errors.current['fatal'])

    def test_protective_fan_test_end_reports_without_inventing_printer_shutdown(self):
        with errors_session() as h:
            h.fans.start_oem()
            h.cooling['status_fresh'] = False
            h.fans._tick(h.now)
            self.assertEqual(h.fans.state, 'FAULT')
            self.assertIsNone(h.fans.test)
            self.assertFalse(h.shutdown)
            self.assertEqual(h.errors.current['title'], 'Procedure failed')
            self.assertFalse(h.errors.current['fatal'])

    def test_thermal_fault_cuts_both_heaters_and_reports_before_shutdown(self):
        with errors_session() as h:
            t = thermal(h)
            t.stop('extruder not heating at expected rate', fault=True)
            self.assertTrue(h.shutdown)
            self.assertEqual(h.errors.current['source'], 'm300_thermal')
            self.assertEqual(h.errors.current['code'], 10)
            self.assertEqual([heater.target for heater in t.heaters.values()], [0., 0.])
            for heater in t.heaters.values():
                heater.set_pwm.assert_called_once_with(h.now, 0.)

    def test_thermal_cleanup_exception_still_requests_shutdown_with_original_cause(self):
        with errors_session() as h:
            t = thermal(h)
            t.heaters['extruder'].set_temp = Mock(side_effect=RuntimeError('heater queue failed'))
            with self.assertRaisesRegex(RuntimeError, 'heater queue failed'):
                t.stop('thermal deadline exceeded', fault=True)
            self.assertTrue(h.shutdown)
            self.assertEqual(h.errors.current['reason'], 'thermal deadline exceeded')

    def test_settings_write_failure_is_a_notice_and_does_not_publish_a_value(self):
        with errors_session() as h:
            old = h.nvm.get_setting('oled_brightness')
            h.nvm.store.update = Mock(side_effect=OSError('No space left on device'))
            with self.assertRaisesRegex(CommandError, 'No space left'):
                h.nvm.set_setting('oled_brightness', 8)
            self.assertEqual(h.nvm.get_setting('oled_brightness'), old)
            self.assertFalse(h.nvm.is_busy())
            self.assertEqual(h.errors.current['source'], 'm300_nvm')
            self.assertEqual(h.errors.current['title'], 'Procedure failed')
            self.assertFalse(h.shutdown)

    def test_nested_sd_import_keeps_the_first_typed_failure_and_one_identity(self):
        with errors_session() as h:
            exc = OSError('read timeout')
            first = report(h.printer, exc, source='m300_sd')
            report(h.printer, exc, source='m300_models')
            h.gcode.respond_raw('!! read timeout')
            self.assertEqual(h.errors.current['id'], first['id'])
            self.assertEqual(h.errors.current['code'], 4)
            self.assertEqual(len(h.errors.history), 1)
            report(h.printer, exc, source='m300_job', fatal=True)
            self.assertEqual(h.errors.current['code'], 4)
            self.assertEqual(h.errors.current['reason'], 'read timeout')
            self.assertTrue(h.errors.current['fatal'])

    def test_unknown_fault_is_visible_while_unrelated_input_rejections_are_not(self):
        with errors_session() as h:
            for reason in ('Expired Settings view; refresh before choosing',
                           'M300 fans: m300_motion owns resources', 'DISTANCE must be positive'):
                h.gcode.respond_raw('!! ' + reason)
            self.assertIsNone(h.errors.current)
            report(h.printer, 'backend operation could not finish', source='native_print')
            h.flush_errors()
            self.assertEqual(h.errors.current['code'], 0)
            self.assertFalse(h.errors.current['fatal'])
            self.assertIn('// action:prompt_text Procedure failed', h.lines)

    def test_native_print_error_hook_reports_even_without_console_output(self):
        with errors_session() as h:
            models = M300Models.__new__(M300Models)
            models.printer, models.gcode, models.job = h.printer, h.gcode, h.job
            models.native_load = models.native_print = None
            stats = NS(state='printing', note_complete=lambda: None, note_pause=lambda: None)
            original = Mock(side_effect=lambda msg: setattr(stats, 'state', 'error'))
            stats.note_error = original
            models.v_sd = NS(_load_file=lambda *a, **kw: None, print_stats=stats)
            models._ready()
            stats.note_error('unsupported operation in the active print')
            original.assert_called_once_with('unsupported operation in the active print')
            self.assertEqual(h.errors.current['source'], 'native_print')
            self.assertEqual(h.errors.current['reason'], 'unsupported operation in the active print')

    def test_lifecycle_invalidation_does_not_close_an_already_published_fatal_notice(self):
        with errors_session() as h:
            h.shutdown = True
            report(h.printer, 'PWM queue failed', source='m300_fans', fatal=True)
            h.flush_errors();h.lines.clear()
            h.p.invalidate()
            self.assertFalse(any('action:prompt_end' in line for line in h.lines))

    def test_native_pid_interruption_is_a_nonfatal_procedure_notice(self):
        with errors_session() as h:
            h.gcode.respond_raw('!! pid_calibrate interrupted')
            self.assertEqual(h.errors.current['source'], 'gcode')
            self.assertEqual(h.errors.current['title'], 'Procedure failed')
            self.assertEqual(h.errors.current['kind'], SHUTDOWN)
            self.assertFalse(h.errors.current['fatal'])

    def test_oled_timeout_reports_once_without_shutting_down_the_printer(self):
        with errors_session() as h:
            h.oled.stream.step = Mock(side_effect=TimeoutError('ACK deadline expired'))
            h.oled._send_one(h.now)
            h.oled._send_one(h.now)
            self.assertEqual(len(h.errors.history), 1)
            self.assertEqual(h.errors.current['source'], 'm300_oled')
            self.assertFalse(h.errors.current['fatal'])
            self.assertFalse(h.shutdown)
            self.assertFalse(any(e[0] in ('heat', 'move') for e in h.events))

    def test_first_mcu_oled_fault_is_observed_without_flooding_repeat_status(self):
        with errors_session() as h:
            h.oled.mcu_oled_stats = None
            packet = dict(blocks=0, wire=0, queued=0, peak=0, fault=1,
                          spi_hz=4500000, max_busy_ticks=0)
            h.oled._stats(packet)
            h.oled._stats(packet)
            h.flush_errors()
            self.assertEqual(len(h.errors.history), 1)
            self.assertEqual(h.errors.current['source'], 'm300_oled')
            self.assertIn('OLED DMA fault', h.errors.current['reason'])
            self.assertFalse(h.shutdown)
