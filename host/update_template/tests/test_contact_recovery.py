# Marcin Kowalik <mkowalik@agh.edu.pl>
# test_contact_recovery.py - Sprawdza opuszczenie stołu po utracie styku PC7.
"""Reported contact loss, bounded cleaning clearance and hard fault isolation."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from payload.m300_native_probe import is_contact_failure
from payload.m300_pad_mesh import M300PadMesh, GEOMETRY_DEFAULTS, geometry_points
from test_normal_operations import motion_fixture
from test_firmware131_contract import precision_harness, REFERENCE, homing


CONTACT_ERROR = 'M300 precision Z: PC7 contact was not stable after approach'


def failed_contact():
    m = motion_fixture()
    m.precision.run = Mock(side_effect=RuntimeError(CONTACT_ERROR))
    m.printer.invoke_shutdown = Mock()
    return m


class ContactRecoveryTests(unittest.TestCase):
    def test_reported_contact_loss_lowers_bed_100mm_and_invalidates_z(self):
        m = failed_contact()
        with self.assertRaisesRegex(RuntimeError, 'No contact - please clean nozzle'):
            m.home(axes='z')
        self.assertEqual(m.toolhead.get_position(), [150., 158., 100., 7.])
        self.assertEqual(m.homed, set('xy'))
        self.assertEqual(m.state, 'FAULT')
        self.assertEqual(m.contact_recovery, dict(status='RETRACTED', distance_mm=100., pc7_open=True))
        m.printer.invoke_shutdown.assert_not_called()
        self.assertIsNone(m._xy_clearance_position)

    def test_existing_260c_target_and_bed_are_cut_before_cleaning_drop(self):
        m = failed_contact()
        m.hotend.target = 260.
        bed = NS(target=60.)
        def off():
            m.hotend.target = bed.target = 0.
            m.events.append(('off',))
        m.heaters.turn_off_all_heaters = off
        with self.assertRaisesRegex(RuntimeError, 'No contact'):
            m.home(axes='z', filament_prepared=True)
        self.assertEqual((m.hotend.target, bed.target), (0., 0.))
        drop = ('move', (None, None, 100.), 5.)
        self.assertLess(m.events.index(('off',)), m.events.index(drop))
        self.assertEqual(m.events[-1], drop)

    def test_cleaned_contact_can_home_again_without_firmware_restart(self):
        m = failed_contact()
        with self.assertRaises(RuntimeError):
            m.home(axes='z')
        m.precision.run.side_effect = None
        m.precision.run.return_value = dict(contacts=0)
        m.home(axes='z')
        self.assertEqual(m.state, 'COMPLETE')
        self.assertEqual(m.homed, set('xyz'))
        self.assertEqual(m.toolhead.get_position()[2], 5.)
        self.assertIsNone(m.contact_recovery)
        m.printer.invoke_shutdown.assert_not_called()

    def test_contact_still_closed_after_drop_never_causes_another_approach(self):
        m = failed_contact()
        def failed(token):
            m.precision.endstop.query_endstop.return_value = True
            raise RuntimeError(CONTACT_ERROR)
        m.precision.run.side_effect = failed
        with self.assertRaisesRegex(RuntimeError, 'PC7 remains closed'):
            m.home(axes='z')
        self.assertEqual(m.toolhead.get_position()[2], 100.)
        self.assertFalse(m.contact_recovery['pc7_open'])
        self.assertNotIn('z', m.homed)
        m.printer.invoke_shutdown.assert_not_called()

    def test_recovery_at_bottom_clips_to_native_z_limit(self):
        m = failed_contact()
        m.homed.add('z')
        m.toolhead.set_position([150., 158., 300., 17.])
        recovery = m.recover_contact_failure(lambda: m._check(m.token))
        self.assertEqual(recovery['distance_mm'], 15.)
        self.assertEqual(m.toolhead.get_position()[2], 315.)
        self.assertEqual(m.toolhead.get_position()[3], 17.)
        self.assertNotIn('z', m.homed)

    def test_unknown_coarse_z_does_not_authorize_a_blind_cleaning_drop(self):
        m = failed_contact()
        def coarse(params):
            m.homed.discard('z')
            raise RuntimeError('No trigger on probe after full movement')
        m.native_G28 = coarse
        with self.assertRaisesRegex(RuntimeError, 'Z is not referenced'):
            m.home(axes='z')
        self.assertEqual(m.contact_recovery['status'], 'UNREFERENCED')
        self.assertEqual([e[1][2] for e in m.events if e[0] == 'move' and e[1][2] is not None], [304.])
        m.printer.invoke_shutdown.assert_not_called()

    def test_mcu_guard_rejection_aborts_recovery_and_retains_shutdown(self):
        m = failed_contact()
        def failed(token):
            m.board.require_motion.side_effect = RuntimeError('M300 guard latched')
            raise RuntimeError(CONTACT_ERROR)
        m.precision.run.side_effect = failed
        with self.assertRaises(RuntimeError):
            m.home(axes='z')
        m.printer.invoke_shutdown.assert_called_once_with('M300 contact retreat failed: M300 guard latched')
        self.assertNotIn('z', m.homed)
        self.assertFalse(any(e[0] == 'move' and e[1][2] == 100. for e in m.events))

    def test_restart_during_drain_prevents_cleaning_motion(self):
        m = failed_contact()
        def failed(token):
            m.toolhead.wait_moves = lambda: m._stop('gcode:request_restart')
            raise RuntimeError(CONTACT_ERROR)
        m.precision.run.side_effect = failed
        with self.assertRaises(RuntimeError):
            m.home(axes='z')
        self.assertFalse(any(e[0] == 'move' and e[1][2] == 100. for e in m.events))
        self.assertNotIn('z', m.homed)

    def test_invalid_recovery_position_cannot_move_or_remain_homed(self):
        m = failed_contact()
        def failed(token):
            m.toolhead.set_position([150., 158., float('nan'), 17.])
            raise RuntimeError(CONTACT_ERROR)
        m.precision.run.side_effect = failed
        with self.assertRaises(RuntimeError):
            m.home(axes='z')
        m.printer.invoke_shutdown.assert_called_once()
        self.assertIn('no valid native Z frame', m.printer.invoke_shutdown.call_args.args[0])
        self.assertNotIn('z', m.homed)

    def test_unexpected_precision_error_still_requests_shutdown(self):
        m = failed_contact()
        m.precision.run.side_effect = RuntimeError('native probe returned an invalid position')
        with self.assertRaisesRegex(RuntimeError, 'invalid position'):
            m.home(axes='z')
        m.printer.invoke_shutdown.assert_called_once()
        self.assertFalse(any(e[0] == 'move' and e[1][2] == 100. for e in m.events))

    def test_real_native_reference_rejects_the_unstable_contact_before_publication(self):
        h, ref = precision_harness(REFERENCE['z_references'][1])
        query = h.endstop.query_endstop
        def opens_after_approach(now):
            if any(e[0] == 'contact' and e[1] is True for e in h.events):
                return False
            return query(now)
        h.endstop.query_endstop = opens_after_approach
        with patch.dict('sys.modules', {'payload.homing': homing}), self.assertRaisesRegex(
                RuntimeError, 'PC7 contact was not stable') as caught:
            ref.run(1)
        self.assertTrue(is_contact_failure(caught.exception))
        self.assertEqual(ref.references, [])

    def test_error_classifier_does_not_treat_transport_or_sensor_fault_as_contact(self):
        for message in ('Lost communication with MCU', 'Timer too close',
                        'Heater extruder not heating at expected rate',
                        'M300 precision Z: bounded contact/release deadline exceeded',
                        'M300 precision Z: non-finite native Z result',
                        'M300 precision Z: PC7 must own exactly one native Z stepper'):
            with self.subTest(message=message):
                self.assertFalse(is_contact_failure(RuntimeError(message)))

    def test_pad_mesh_contact_loss_uses_same_drop_and_never_publishes_failed_mesh(self):
        m = motion_fixture()
        m.homed.add('z')
        m.toolhead.set_position([31., 31., 1., 17.])
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.geometry = dict(GEOMETRY_DEFAULTS)
        mesh.points = geometry_points(mesh.geometry)
        mesh.busy, mesh.report = False, {'profile': 'previous'}
        mesh.shift, mesh.horizontal_z = 1., 6.
        mesh.printer, mesh.reactor = m.printer, m.reactor
        mesh.toolhead, mesh.kin, mesh.motion = m.toolhead, m.toolhead.get_kinematics(), m
        mesh._preflight = lambda: None
        mesh._prepare = lambda token: setattr(mesh, 'phase', 'PROBING')
        mesh._check_session = lambda token: None
        mesh._publish = Mock()
        mesh._turn_off = Mock()
        mesh.gcode = NS(create_gcode_command=lambda *args: args[-1])
        mesh.probe_points = NS(update_probe_points=lambda *args: None,
            start_probe=Mock(side_effect=RuntimeError('No trigger on probe after full movement')))
        gcmd = NS(get=lambda key, default: default, get_command_parameters=dict,
                  get_int=lambda key, default, **kw: default,
                  get_float=lambda key, default: default, respond_info=Mock())
        with self.assertRaisesRegex(RuntimeError, 'No contact - please clean nozzle'):
            mesh.cmd_calibrate(gcmd)
        self.assertEqual(mesh.state, 'FAILED')
        self.assertFalse(mesh.busy)
        self.assertEqual(mesh.contact_recovery['distance_mm'], 100.)
        self.assertEqual(m.toolhead.get_position(), [31., 31., 101., 17.])
        self.assertNotIn('z', m.homed)
        mesh._publish.assert_not_called()
        mesh._turn_off.assert_called_once()
        self.assertEqual(mesh.report, {'profile': 'previous'})

