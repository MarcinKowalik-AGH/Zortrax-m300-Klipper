# Marcin Kowalik <mkowalik@agh.edu.pl>
# test_contact_notice.py - Sprawdza wygaszenie alarmu styku po poprawnym bazowaniu Z.
"""A recovered contact notice must not keep the normal RGB state in ERROR."""
from unittest.mock import Mock
import unittest

from payload.m300_error_codes import classify, NONE, SHUTDOWN
from payload.m300_pad_mesh import M300PadMesh
from test_normal_operations import motion_fixture
from test_oem_errors import errors_session


MISSING = ('No contact - please clean nozzle and pad contacts, then repeat homing. '
           'Cause: No trigger on m300_z_reference after full movement')


def home_fixture(errors):
    motion = motion_fixture()
    motion.precision.run = Mock(return_value=dict(
        method='FIVE_SUCCESSIVE_RELEASE_REFERENCES', contacts=5))
    motion.printer.lookup_object = lambda name, default=None: errors if name == 'm300_errors' else default
    return motion


class ContactNoticeTests(unittest.TestCase):
    def test_native_precision_missing_trigger_is_contact_error_42(self):
        self.assertEqual(classify(MISSING, source='m300_motion'), (42, NONE))

    def test_successful_physical_z_home_clears_notice_rgb_and_mcu_metadata(self):
        with errors_session() as h:
            record = h.errors.record(MISSING, source='m300_motion')
            h.flush_errors()
            self.assertEqual(h.m.status_led_rgb(h.now), (1., 0., 0.))
            h.now += 10.
            self.assertEqual(h.m.status_led_rgb(h.now), (0., 0., 1.))
            motion = home_fixture(h.errors)
            h.objects['m300_motion'] = motion
            motion.home(axes='z')
            self.assertEqual(motion.state, 'COMPLETE')
            self.assertIsNone(h.errors.current)
            self.assertEqual(h.writes[-1][1], [0, NONE, 0])
            self.assertEqual(h.m.status_led_rgb(h.now), (0., 1., 0.))
            h.now += 10.
            self.assertEqual(h.m.status_led_rgb(h.now), (0., 1., 0.))
            self.assertIsNone(h.m._light_error_since)
            self.assertEqual(h.errors.history[-1]['id'], record['id'])
            h.flush_errors()
            self.assertIsNone(h.errors.current)

    def test_reported_legacy_unnumbered_contact_notice_also_clears(self):
        with errors_session() as h:
            h.errors.record(MISSING, source='m300_motion', code=0, kind=SHUTDOWN)
            home_fixture(h.errors).home(axes='z')
            self.assertIsNone(h.errors.current)

    def test_failed_mesh_history_survives_but_recovered_contact_no_longer_drives_rgb(self):
        for acknowledge_first, info_notice in ((False, False), (True, False), (True, True)):
            with self.subTest(acknowledge_first=acknowledge_first, info_notice=info_notice), errors_session() as h:
                pad = M300PadMesh.__new__(M300PadMesh)
                pad.state, pad.busy, pad.run_id = 'FAILED', False, 'failed-contact-run'
                pad.printer = h.printer
                pad.measurements = [[31., 31., 0.01]]
                h.objects['m300_pad_mesh'] = pad
                record = h.errors.record(MISSING, source='m300_pad_mesh')
                if acknowledge_first:
                    h.errors.acknowledge(record['id'])
                if info_notice:
                    info = h.errors.record('No models on SD card', source='m300_browser', code=101)
                self.assertEqual(h.m.status_led_rgb(h.now), (1., 0., 0.))
                motion = home_fixture(h.errors)
                h.objects['m300_motion'] = motion
                motion.home(axes='z')
                if info_notice:
                    self.assertEqual(h.errors.current['id'], info['id'])
                else:
                    self.assertIsNone(h.errors.current)
                self.assertEqual(pad.state, 'FAILED')
                self.assertEqual(pad.measurements, [[31., 31., 0.01]])
                self.assertTrue(pad.contact_error_resolved)
                self.assertEqual(pad.get_ownership_status(h.now)['state'], 'IDLE')
                self.assertEqual(h.m.status_led_rgb(h.now), (0., 1., 0.))

    def test_resolved_mesh_notice_cannot_release_another_run_or_an_active_measurement(self):
        for run_id, state, busy in (('new-run', 'FAILED', False),
                                     ('old-run', 'PROBING', True)):
            with self.subTest(run_id=run_id), errors_session() as h:
                pad = M300PadMesh.__new__(M300PadMesh)
                pad.state, pad.busy, pad.run_id = 'FAILED', False, 'old-run'
                pad.printer = h.printer
                h.objects['m300_pad_mesh'] = pad
                h.errors.record(MISSING, source='m300_pad_mesh')
                pad.state, pad.busy, pad.run_id = state, busy, run_id
                home_fixture(h.errors).home(axes='z')
                self.assertFalse(getattr(pad, 'contact_error_resolved', False))
                self.assertEqual(pad.get_ownership_status(h.now)['state'], state)

    def test_xy_home_or_fileoutput_cannot_clear_the_contact_notice(self):
        for axes, fileoutput in (('xy', False), ('z', True)):
            with self.subTest(axes=axes, fileoutput=fileoutput), errors_session() as h:
                record = h.errors.record(MISSING, source='m300_motion')
                motion = home_fixture(h.errors)
                motion.board.mcu.is_fileoutput = lambda: fileoutput
                motion.home(axes=axes)
                self.assertEqual(h.errors.current['id'], record['id'])

    def test_failed_rehome_keeps_the_contact_alarm(self):
        with errors_session() as h:
            h.errors.record(MISSING, source='m300_motion')
            motion = home_fixture(h.errors)
            motion.precision.run.side_effect = RuntimeError(
                'M300 precision Z: PC7 contact was not stable after approach')
            with self.assertRaisesRegex(RuntimeError, 'No contact'):
                motion.home(axes='z')
            self.assertIsNotNone(h.errors.current)
            self.assertEqual(h.m.status_led_rgb(h.now), (1., 0., 0.))

    def test_a_new_notice_during_homing_is_not_dismissed_by_the_old_token(self):
        with errors_session() as h:
            h.errors.record(MISSING, source='m300_motion')
            motion = home_fixture(h.errors)
            result = motion.precision.run.return_value
            def new_notice(token):
                h.errors.record('No trigger on probe after full movement', source='m300_pad_mesh')
                return result
            motion.precision.run.side_effect = new_notice
            motion.home(axes='z')
            self.assertEqual(h.errors.current['source'], 'm300_pad_mesh')

    def test_fatal_heater_or_mcu_alarms_survive_the_notice_resolver(self):
        for reason in ('Heater extruder not heating at expected rate',
                       'M300 guard fault platform_connector_PE15'):
            with self.subTest(reason=reason), errors_session() as h:
                notice = h.errors.record(MISSING, source='m300_motion')
                fault = h.errors.record(reason, source='klipper_shutdown', fatal=True)
                self.assertFalse(h.errors.resolve_contact_notice(notice['id']))
                self.assertEqual(h.errors.current['id'], fault['id'])
                self.assertEqual(h.errors.current['fatal'], True)

    def test_unrelated_procedure_fault_is_not_a_resolved_contact_notice(self):
        with errors_session() as h:
            record = h.errors.record('Calibration failed', source='m300_calibration')
            home_fixture(h.errors).home(axes='z')
            self.assertEqual(h.errors.current['id'], record['id'])

    def test_shutdown_blocks_resolving_even_a_nonfatal_contact_notice(self):
        with errors_session() as h:
            record = h.errors.record(MISSING, source='m300_motion')
            h.errors.printer.is_shutdown = lambda: True
            self.assertFalse(h.errors.resolve_contact_notice(record['id']))
            self.assertEqual(h.errors.current['id'], record['id'])

