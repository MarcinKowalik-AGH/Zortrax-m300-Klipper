"""Normal operation boundaries, migration and Fluidd category regression tests."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

import test_display
from payload.m300_native_motion import M300NativeMotion
import m300_profile as profile
from setup_fluidd import merge_groups, category
from test_native_menu import fixture as menu_fixture


def motion_fixture():
    motion = M300NativeMotion.__new__(M300NativeMotion)
    motion.token = motion.phase_id = 0
    motion.state = motion.phase = 'IDLE'
    motion.operator_homing = None
    motion.reason, motion.result, motion.ready = '', None, True
    motion.homing_speeds = motion.failure_phase = None
    motion.home_xy, motion.travel_speed = (150., 158.), 50.
    motion.z_home_hotend_target, motion.clearance, motion.lift_speed = 180., 5., 5.
    motion.z_home_temperature_tolerance = 5.
    motion.z_home_heat_timeout = 600.
    motion.reactor = NS(monotonic=lambda: 1.)
    motion.events, motion.homed = [], set('xy')
    position = [100., 100., 299., 17.]
    hotend = NS(target=0., measured=180., check_busy=lambda now: False)
    hotend.get_temp = lambda now: (hotend.measured, hotend.target)
    motion.hotend = hotend
    def set_temperature(heater, target, wait=False):
        heater.target = target
        motion.events.append(('heat', target, wait))
    motion.heaters = NS(set_temperature=set_temperature)
    rail = NS(get_range=lambda: (0., 315.), get_homing_info=lambda: NS(positive_dir=False))
    kin = NS(get_status=lambda now: {'homed_axes': ''.join(a for a in 'xyz' if a in motion.homed)},
             rails=[None, None, rail],
             clear_homing_state=lambda axes: motion.homed.difference_update(axes))
    def set_position(coords, homing_axes=''):
        position[:] = coords
        motion.homed.update(homing_axes)
    def manual_move(coords, speed):
        if coords[2] is not None and 'z' not in motion.homed:
            raise RuntimeError('Must home axis first')
        motion.events.append(('move', tuple(coords), speed))
        for i, value in enumerate(coords):
            if value is not None:
                position[i] = value
    motion.toolhead = NS(get_kinematics=lambda: kin, manual_move=manual_move,
                         set_position=set_position,
                         get_position=lambda: position[:], wait_moves=lambda: None,
                         get_last_move_time=lambda: 1., check_busy=lambda now: (1., 2., True))
    motion.printer = NS(command_error=RuntimeError, is_shutdown=lambda: False,
                        lookup_object=lambda name, default=None: default, send_event=Mock())
    motion.gcode = NS(create_gcode_command=lambda name, text, params: params)
    def native_home(params):
        motion.events.append(('home', ''.join(params)))
        for axis in params:
            position['XYZ'.index(axis)] = 0.
            motion.homed.add(axis.lower())
    motion.native_G28 = native_home
    motion.precision = NS(run=lambda token: dict(contacts=0), check_temperature=Mock(),
                          probe=NS(get_offsets=lambda:(0.,0.,0.)),
                          endstop=NS(query_endstop=Mock(return_value=False)))
    motion.board = NS(mcu=NS(is_fileoutput=lambda: False), require_motion=Mock(), hardware=NS(get_status=lambda: {'effective_z_steps_per_mm': 400,
                                                     'hardware_revision': 5}))
    return motion


class NormalHomingTests(unittest.TestCase):
    def test_operator_homing_presentation_leaves_leveling_and_print_in_control(self):
        for axes, leveling, printing, expected in (
                ('xy', False, False, 'HOME_XY'), ('xyz', False, False, 'HOME_ALL'),
                ('z', False, False, 'HOME_Z'), ('xyz', True, False, None),
                ('xyz', False, True, None), ('z', False, True, None)):
            with self.subTest(axes=axes, leveling=leveling, printing=printing):
                motion = motion_fixture()
                if printing:
                    motion.printer.lookup_object = {
                        'virtual_sdcard': NS(work_timer=object())
                    }.get
                status = motion.home(axes=axes, oem_leveling=leveling)
                self.assertEqual(status['operation'], expected)
                self.assertEqual(status['state'], 'COMPLETE')
                self.assertEqual(motion.printer.send_event.called, expected is not None)

    def test_xy_needs_no_heat_or_clearance_declaration_and_keeps_z_e(self):
        m = motion_fixture()
        m.homed.clear()
        m.home(axes='xy')
        self.assertEqual(m.events, [('home', 'Y'), ('home', 'X')])
        self.assertEqual(m.toolhead.get_position()[2:], [299., 17.])

    def test_xyz_preheats_180_then_native_xy_native_z_and_five_mm_clearance(self):
        m = motion_fixture()
        m.homed.clear()
        m.home(axes='xyz')
        self.assertEqual(m.events, [('heat', 180., False), ('home', 'Y'), ('home', 'X'),
            ('move', (150., 158., None), 50.), ('home', 'Z'),
            ('move', (None, None, 5.), 5.), ('heat', 0., False)])
        self.assertEqual(m.toolhead.get_position()[3], 17.)
        self.assertEqual(m.get_status(1.)['homed_axes'], 'xyz')

    def test_repeated_z_home_does_not_accumulate_clearance_or_request_z304(self):
        m = motion_fixture()
        for _ in range(3):
            m.home(axes='z')
            self.assertEqual(m.toolhead.get_position()[2], 5.)
        ztargets = [e[1][2] for e in m.events if e[0] == 'move' and e[1][2] is not None]
        self.assertEqual(ztargets, [5., 5., 5.])

    def test_active_pc7_without_known_z_releases_before_heat_and_xy(self):
        m = motion_fixture()
        m.homed.clear()
        probe_states = iter([True, False, False, False])
        z_homed_at_query = []
        def query(print_time):
            z_homed_at_query.append('z' in m.homed)
            return next(probe_states)
        m.precision.endstop.query_endstop.side_effect = query
        m.home(axes='xyz')
        self.assertEqual(z_homed_at_query, [False] * 4)
        self.assertEqual(m.events[:4], [('move', (None, None, 300.), 1.),
            ('heat', 180., False), ('home', 'Y'), ('home', 'X')])
        self.assertEqual(m.events[-3:], [('home', 'Z'),
            ('move', (None, None, 5.), 5.), ('heat', 0., False)])
        self.assertEqual(m.get_status(1.)['homed_axes'], 'xyz')

    def test_persistent_pc7_without_known_z_stops_after_one_retreat(self):
        m = motion_fixture()
        m.precision.endstop.query_endstop.return_value = True
        with self.assertRaisesRegex(RuntimeError, 'NO_RELEASE'):
            m.home(axes='xyz')
        self.assertEqual(m.events, [('move', (None, None, 300.), 1.)])
        self.assertNotIn('z', m.homed)
        self.assertEqual(m.get_status(1.)['failure_phase'], 'Z_CHECK_CONTACT')

    def test_homed_active_pc7_gets_one_bounded_retreat_and_recheck(self):
        for reopens in (False, True):
            with self.subTest(reopens=reopens):
                m = motion_fixture()
                m.homed.add('z')
                m.precision.endstop.query_endstop.side_effect = [True, not reopens, False, False]
                if reopens:
                    m.home(axes='z')
                    self.assertEqual(m.state, 'COMPLETE')
                else:
                    with self.assertRaisesRegex(RuntimeError, 'NO_RELEASE'):
                        m.home(axes='z')
                    self.assertEqual(len(m.events), 1)
                self.assertEqual(m.events[0], ('move', (None, None, 300.), 1.))
                m.board.require_motion.assert_called_once()

    def test_contact_that_closes_at_center_releases_before_native_z_seek(self):
        m = motion_fixture()
        m.precision.endstop.query_endstop.side_effect = [False, False, True, False]
        m.home(axes='z')
        self.assertEqual(m.events[1:4], [('move', (150., 158., None), 50.),
            ('move', (None, None, 300.), 1.), ('home', 'Z')])

    def test_contact_reclosed_after_retreat_refuses_xy_and_another_retreat(self):
        m = motion_fixture()
        m.precision.endstop.query_endstop.side_effect = [True, False, True]
        with self.assertRaisesRegex(RuntimeError, 'NO_RELEASE: PC7 closed again'):
            m.home(axes='xyz')
        self.assertEqual(m.events, [('move', (None, None, 300.), 1.),
            ('heat', 180., False), ('heat', 0., False)])
        self.assertNotIn('z', m.homed)

    def test_retreat_respects_native_z_limit(self):
        for z, expected_moves in ((314.75, [('move', (None, None, 315.), 1.)]),
                                  (315., [])):
            with self.subTest(z=z):
                m = motion_fixture()
                m.toolhead.set_position([100., 100., z, 17.])
                m.precision.endstop.query_endstop.return_value = True
                with self.assertRaisesRegex(RuntimeError, 'NO_RELEASE'):
                    m.home(axes='z')
                self.assertEqual(m.events, expected_moves)
                self.assertNotIn('z', m.homed)

    def test_failed_retreat_discards_temporary_z_frame(self):
        m = motion_fixture()
        m.precision.endstop.query_endstop.return_value = True
        m.toolhead.manual_move = Mock(side_effect=RuntimeError('move rejected'))
        with self.assertRaisesRegex(RuntimeError, 'move rejected'):
            m.home(axes='z')
        self.assertEqual(m.events, [])
        self.assertNotIn('z', m.homed)

    def test_default_idle_disables_xye_only_and_keeps_z_homed(self):
        m = motion_fixture()
        m.homed.add('z')
        motors = NS(get_steppers=lambda: ['stepper_x', 'stepper_y', 'stepper_z', 'extruder'],
                    set_motors_enable=Mock())
        stats = NS(get_status=Mock(return_value={'state': 'paused'}))
        objects = {'stepper_enable': motors, 'print_stats': stats}
        m.printer.lookup_object = objects.get
        m.cmd_idle_release(None)
        motors.set_motors_enable.assert_not_called()
        stats.get_status.return_value = {'state': 'complete'}
        m.cmd_idle_release(None)
        motors.set_motors_enable.assert_called_once_with(['stepper_x', 'stepper_y', 'extruder'], False)
        self.assertEqual(m.homed, {'z'})
        self.assertEqual(m.events, [])

    def test_existing_hotter_user_target_is_kept(self):
        m = motion_fixture()
        m.hotend.target = 240.
        m.hotend.measured = 200.
        m.hotend.check_busy = Mock(return_value=True)
        m.home(axes='z')
        self.assertEqual([e for e in m.events if e[0] == 'heat'], [('heat', 240., False)])
        self.assertEqual(m.hotend.target, 240.)
        m.hotend.check_busy.assert_not_called()

    def test_nozzle_above_minimum_does_not_wait_to_cool(self):
        for target in (0., 180.):
            with self.subTest(target=target):
                m = motion_fixture()
                m.hotend.target, m.hotend.measured = target, 240.
                m.hotend.check_busy = Mock(return_value=True)
                m.reactor.pause = Mock(side_effect=AssertionError('waited for cooldown'))
                m.home(axes='z')
                self.assertEqual(m.hotend.target, target)
                self.assertIn(('home', 'Z'), m.events)
                m.hotend.check_busy.assert_not_called()

    def test_cold_nozzle_waits_until_measured_minimum(self):
        m = motion_fixture()
        m.hotend.measured = 179.9
        def warm(until):
            self.assertEqual(m.events, [('heat', 180., False)])
            m.hotend.measured = 180.
            return until
        m.reactor.pause = Mock(side_effect=warm)
        m.home(axes='xyz')
        m.reactor.pause.assert_called_once()
        self.assertIn(('home', 'Z'), m.events)

    def test_lost_temperature_after_xy_blocks_coarse_z(self):
        m = motion_fixture()
        m.precision.check_temperature.side_effect = RuntimeError('below contact minimum')
        with self.assertRaisesRegex(RuntimeError, 'below contact minimum'):
            m.home(axes='xyz')
        self.assertIn(('home', 'X'), m.events)
        self.assertNotIn(('home', 'Z'), m.events)
        self.assertEqual(m.hotend.target, 0.)

    def test_z_with_unknown_xy_is_rejected_before_heating_or_movement(self):
        m = motion_fixture()
        m.homed.clear()
        with self.assertRaisesRegex(RuntimeError, 'Home XY'):
            m.home(axes='z')
        self.assertEqual(m.events, [])

    def test_native_endstop_error_cleans_owned_heat_without_clearance_move(self):
        m = motion_fixture()
        def error(params):
            raise RuntimeError('Endstop still triggered after retract')
        m.native_G28 = error
        with self.assertRaisesRegex(RuntimeError, 'Endstop still triggered'):
            m.home(axes='z')
        self.assertEqual(m.hotend.target, 0.)
        self.assertEqual(m.state, 'FAULT')
        self.assertFalse(any(e[0] == 'move' and e[1][2] is not None for e in m.events))

    def test_restart_during_preheat_cannot_continue_old_homing(self):
        m = motion_fixture()
        def interrupted(heater, target, wait=False):
            heater.target = target
            m.events.append(('heat', target, wait))
            if target > 0.:
                m._stop('gcode:request_restart')
        m.heaters.set_temperature = interrupted
        with self.assertRaisesRegex(RuntimeError, 'session ended'):
            m.home(axes='z')
        self.assertFalse(any(e[0] in ('move', 'home') for e in m.events))
        self.assertEqual(m.state, 'CANCELLED')
        self.assertEqual(m.hotend.target, 0.)

    def test_shutdown_during_native_home_does_not_restore_old_positive_target(self):
        m = motion_fixture()
        m.hotend.target = 100.
        def interrupted(params):
            m.printer.is_shutdown = lambda: True
            m._stop()
        m.native_G28 = interrupted
        with self.assertRaises(RuntimeError):
            m.home(axes='z')
        self.assertEqual([e for e in m.events if e[0] == 'heat'], [('heat', 180., False)])

    def test_preheat_has_its_own_deadline_and_never_moves_on_timeout(self):
        m = motion_fixture()
        clock = [0.]
        m.reactor.monotonic = lambda: clock[0]
        def pause(until):
            clock[0] = until
            return until
        m.reactor.pause = pause
        m.hotend.measured = 0.
        with self.assertRaisesRegex(RuntimeError, 'preheat timed out after 600 s'):
            m.home(axes='z')
        self.assertEqual(clock[0], 600.)
        self.assertEqual(m.failure_phase, 'Z_PREHEAT')
        self.assertEqual(m.events, [('heat', 180., False), ('heat', 0., False)])

    def test_native_g28_x0_y0_selectors_are_accepted(self):
        m = motion_fixture()
        m.cmd_G28(NS(get_command_parameters=lambda: {'G': '28', 'X': '0', 'Y': '0'}, error=RuntimeError))
        self.assertEqual(m.events, [('home', 'Y'), ('home', 'X')])

    def test_stale_oem_job_cannot_start_homing(self):
        m = motion_fixture()
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            m.home(owner_job=NS(), job_token=1)
        self.assertEqual(m.events, [])


class ProfileTests(unittest.TestCase):
    def test_direct_uart_uses_native_command_reset_without_changing_baud(self):
        for reset in ('', 'restart_method: arduino\n', 'restart_method: command\n'):
            new = profile.convert_text('[mcu]\nserial: /dev/ttyS1\nbaud: 1500000\n' + reset)
            section = dict(profile.blocks(new)[1])['mcu']
            self.assertEqual(profile.option(section, 'restart_method'), 'command')
            self.assertEqual(profile.option(section, 'baud'), '1500000')
            self.assertEqual(profile.option(section, 'serial'), '/dev/ttyS1')
            self.assertEqual(profile.convert_text(new), new)

    def test_migrates_only_commissioning_limits_and_preserves_calibrated_e_pid(self):
        text = ('[printer]\nmax_velocity: 200\nmax_accel: 700\nmax_z_velocity: 1\nmax_z_accel: 10\n'
                '[stepper_z]\nrotation_distance: 8\nposition_max: 30\nhoming_speed: .5\n'
                '[extruder]\nrotation_distance: 26.133\npid_Kp: 15.152\n'
                '[m300_motion]\nz_safety_profile: Z400_30MM_R15_5_0_HOMING_OLED\nhome_xy: 150, 158\n'
                '#*# <--- SAVE_CONFIG --->\n#*# pid_Kp = 61.966\n')
        new = profile.convert_text(text)
        sections = dict(profile.blocks(new)[1])
        self.assertEqual(profile.option(sections['printer'], 'max_velocity'), '300')
        self.assertEqual(profile.option(sections['printer'], 'max_accel'), '700')
        self.assertEqual(profile.option(sections['stepper_z'], 'position_max'), '300')
        self.assertEqual(profile.option(sections['extruder'], 'rotation_distance'), '26.133')
        self.assertEqual(profile.option(sections['m300_motion'], 'z_home_hotend_target'), '180')
        self.assertEqual(profile.split_saved(new)[1], profile.split_saved(text)[1])
        self.assertEqual(profile.convert_text(new), new)

    def test_deliberate_higher_limits_and_non_test_geometry_are_preserved(self):
        new = profile.convert_text('[printer]\nmax_velocity: 400\nmax_accel: 1300\n'
                                   '[stepper_z]\nposition_max: 299\nrotation_distance: 4\n')
        sections = dict(profile.blocks(new)[1])
        self.assertEqual(float(profile.option(sections['printer'], 'max_velocity')), 400)
        self.assertEqual(profile.option(sections['stepper_z'], 'position_max'), '299')
        self.assertEqual(profile.option(sections['stepper_z'], 'rotation_distance'), '4')

    def test_obsolete_arm_check_buttons_leave_normal_ui(self):
        new = profile.convert_text('[gcode_macro PID_ARM]\ngcode: THERMAL_ARM\n'
                                   '[gcode_macro USER_MACRO]\ngcode: G4 P1\n')
        self.assertNotIn('PID_ARM', new)
        self.assertIn('USER_MACRO', new)


class GroupTests(unittest.TestCase):
    def test_classifies_confirmed_and_unconfirmed_functions(self):
        for name in ('PID_SAVE', 'PID_HOTEND', 'CANCEL_PRINT'):
            self.assertEqual(category(name), 'Klipper')
        for name in ('ZORTRAX_STATUS', 'ZORTRAX_LIGHT', 'ZORTRAX_FANS',
                     'ZORTRAX_LEVEL','ZORTRAX_LOAD','ZORTRAX_UNLOAD',
                     'ZORTRAX_HEAT','ZORTRAX_PLATFORM_UP','ZORTRAX_PLATFORM_DOWN'):
            self.assertEqual(category(name), 'ZORTRAX M300')
        for name in ('ZORTRAX_PRINT', 'TEST_M300_XY'):
            self.assertEqual(category(name), 'TEST M300')
        self.assertIsNone(category('MY_OTHER_PRINTER_MACRO'))

    def test_merge_preserves_unrelated_and_hidden_macro_preferences(self):
        before = {'categories': [{'id': 'other', 'name': 'Other'}],
                  'stored': [{'name': 'PID_SAVE', 'categoryId': 'other', 'visible': False, 'color': 'red'},
                             {'name': 'MY_MACRO', 'categoryId': 'other'}], 'other_setting': 5}
        after, assigned = merge_groups(before, ['PID_SAVE', 'TEST_M300_XY', 'ZORTRAX_STATUS'])
        self.assertEqual(before['stored'][0]['categoryId'], 'other')
        self.assertEqual(after['stored'][1], before['stored'][1])
        self.assertFalse(after['stored'][0]['visible'])
        self.assertEqual(after['stored'][0]['color'], 'red')
        self.assertEqual(merge_groups(after, list(assigned))[0], after)

    def test_duplicate_macro_or_category_is_rejected(self):
        for before in ({'stored': [{'name': 'PID_SAVE'}, {'name': 'pid_save'}]},
                       {'categories': [{'id': '1', 'name': 'Klipper'}, {'id': '2', 'name': 'Klipper'}]}):
            with self.assertRaises(ValueError):
                merge_groups(before, ['PID_SAVE'])


class NormalMenuTests(unittest.TestCase):
    def test_root_has_three_groups_and_tests_are_separate(self):
        menu, _ = menu_fixture()
        menu.page = 'main'
        self.assertEqual([label for label, _ in menu.rows(1.)[1]],
                         ['Klipper', 'Zortrax M300', 'Service / Tests'])
        menu.page = 'klipper'
        rows = menu.rows(1.)[1]
        self.assertEqual(rows[0][0], 'Back')
        self.assertIn(('Home XYZ', ('motion_home_xyz',)), rows)
        self.assertFalse(any('TEST' in label or 'CONFIRM' in label or 'SPLIT' in label for label, _ in rows))

    def test_normal_homing_click_queues_native_command_and_can_expire(self):
        menu, objects = menu_fixture()
        objects['m300_motion'].normal_control = True
        menu.page = 'klipper'
        menu.select(('motion_home_xyz',), 1.)
        self.assertEqual(menu.commands, [])
        menu.generation += 1
        menu.scheduled.pop()(2.)
        self.assertEqual(menu.commands, [])
        objects['m300_motion'].home.assert_not_called()


if __name__ == '__main__':
    unittest.main()
