"""Pinned native two-pass homing with modeled PC7 and physical Z steps.

The native retract, position updates and no-movement rejection execute
unchanged. MCU contact/step timing and the probe-session boundary are modeled;
these tests do not qualify a physical printer.
"""
from types import SimpleNamespace as NS
import unittest

from test_native_leveling import Harness, homing
from test_normal_operations import motion_fixture


class CoarseHome:
    def __init__(self, scale=400, release_at=0., guard=True):
        h = self.h = Harness(scale)
        self.motion = m = motion_fixture()
        m.printer, m.toolhead, m.reactor = h.printer, h.toolhead, h.reactor
        m.state, m.phase = 'HOMING', 'HOME_Z_NATIVE_PROBE'
        m.precision.endstop = h.endstop
        self.release_at, self.latched, self.starts = release_at, False, 0
        self.results, self.session_ended = [], False
        self.rail = NS(get_range=lambda: (0., 315.),
            get_endstops=lambda: [(h.endstop, 'probe')], get_homing_info=lambda: NS(
            speed=5., second_homing_speed=2.5, retract_dist=1., retract_speed=5.))
        h.kin.rails = [None, None, self.rail]
        h.objects['toolhead'] = h.toolhead
        h.objects['gcode'] = NS(create_gcode_command=lambda name, text, params: NS(
            get_command=lambda: name, get=lambda key, default=None: params.get(key, default)))
        h.objects['probe'] = NS(start_probe_session=lambda cmd: NS(
            run_probe=self.run_probe, pull_probed_results=self.pull,
            end_probe_session=lambda: setattr(self, 'session_ended', True)))
        original_position, original_move = h.toolhead.set_position, h.toolhead.move
        h.toolhead.set_position = lambda p, **kw: original_position(p)
        def move(p, speed):
            original_move(p, speed)
            if h.stepper.actual / scale >= self.release_at:
                self.latched = False
        h.toolhead.move = move
        h.toolhead.manual_move = lambda p, speed: move([
            old if new is None else new for old, new in zip(h.position, list(p) + [None] * (4-len(p)))], speed)
        h.endstop.query_endstop = lambda now: self.latched or h.stepper.actual <= 0
        original_start = h.endstop.home_start
        def start(*args, **kwargs):
            self.starts += 1
            return original_start(*args, **kwargs)
        h.endstop.home_start = start
        def drip(target, speed, completion):
            # A closed contact at arm time triggers before any physical step.
            if h.endstop.query_endstop(h.now):
                h.trigger_time = h.now
            elif target[2] - h.stepper.offset <= 0.:
                h.stepper.actual = 0
                self.latched = self.release_at > 0.
                h.trigger_time = h.now
            else:
                h.stepper.actual = round((target[2] - h.stepper.offset) * scale)
                h.trigger_time = 0.
            h.events.append(('seek', self.starts, h.stepper.actual))
        h.toolhead.drip_move = drip
        original_event = h.printer.send_event
        def event(name, *args):
            original_event(name, *args)
            if guard and name == 'homing:homing_move_begin':
                m._native_probe_begin(*args)
        h.printer.send_event = event
        self.native = homing.PrinterHoming.__new__(homing.PrinterHoming)
        self.native.printer = h.printer

    def run_probe(self, gcmd):
        h = self.h
        target = h.position[:]
        target[2] = 0.
        result = self.native.probing_move(h.endstop, target,
            float(gcmd.get('PROBE_SPEED')),
            check_movement=not self.native.check_probe_first_home(gcmd))
        self.results.append(NS(bed_z=result[2]))

    def pull(self):
        results, self.results = self.results, []
        return results

    def run(self):
        native = homing.Homing(self.h.printer)
        native._do_home_z_via_probe([self.rail], [None, None, 472.5, None],
                                    [None, None, 0., None])


class NativeZReleaseTests(unittest.TestCase):
    def test_native_second_pass_reproduces_reported_error_without_release_guard(self):
        h = CoarseHome(release_at=3., guard=False)
        with self.assertRaisesRegex(RuntimeError, 'Probe triggered prior to movement'):
            h.run()
        self.assertEqual(h.starts, 2)

    def test_one_five_mm_retreat_releases_pc7_then_native_second_pass_succeeds(self):
        for scale in (400, 800):
            with self.subTest(scale=scale):
                h = CoarseHome(scale, release_at=3.)
                h.run()
                self.assertTrue(h.session_ended)
                self.assertEqual(h.starts, 2)
                self.assertEqual(h.h.stepper.actual, 0)
                self.assertEqual(h.h.position, [150., 158., 0., 17.])
                self.assertEqual(h.motion.native_z_checks, [
                    dict(pass_number=1, pc7_active_before=False, retreat_mm=0., pc7_open=True),
                    dict(pass_number=2, pc7_active_before=True, retreat_mm=5., pc7_open=True)])
                self.assertEqual([e[1][2] for e in h.h.events if e[0] == 'move'], [1., 7.])

    def test_already_open_pc7_keeps_native_retract_and_speeds_without_extra_move(self):
        h = CoarseHome()
        h.run()
        self.assertEqual(h.starts, 2)
        self.assertEqual([e[1][2] for e in h.h.events if e[0] == 'move'], [1.])
        self.assertEqual([c['retreat_mm'] for c in h.motion.native_z_checks], [0., 0.])
        self.assertEqual(h.h.position[2], 0.)

    def test_persistent_short_stops_before_second_seek_after_only_one_retreat(self):
        h = CoarseHome(release_at=float('inf'))
        with self.assertRaisesRegex(RuntimeError, 'NO_RELEASE: PC7 still closed before native Z pass 2'):
            h.run()
        self.assertEqual(h.starts, 1)
        self.assertEqual([e[1][2] for e in h.h.events if e[0] == 'move'], [1., 7.])
        self.assertFalse(h.motion.native_z_checks[-1]['pc7_open'])
        self.assertFalse(h.session_ended)

    def test_late_contact_after_open_precheck_still_triggers_native_safety_error(self):
        h = CoarseHome()
        start = h.h.endstop.home_start
        def late_close(*args, **kwargs):
            result = start(*args, **kwargs)
            if h.starts == 2:
                h.latched = True
            return result
        h.h.endstop.home_start = late_close
        with self.assertRaisesRegex(RuntimeError, 'Probe triggered prior to movement'):
            h.run()
        self.assertEqual([c['retreat_mm'] for c in h.motion.native_z_checks], [0., 0.])

    def test_first_pass_closed_contact_never_moves_in_native_forcepos_frame(self):
        h = CoarseHome()
        h.latched = True
        with self.assertRaisesRegex(RuntimeError, 'PC7 closed before native Z pass 1'):
            h.run()
        self.assertEqual(h.starts, 0)
        self.assertFalse(any(e[0] in ('move', 'seek') for e in h.h.events))

    def test_release_without_z_room_does_not_extend_native_travel_limits(self):
        h = CoarseHome()
        h.motion.native_z_checks = [dict(pass_number=1)]
        h.h.toolhead.set_position([150., 158., 312., 17.])
        h.latched = True
        hmove = homing.HomingMove(h.h.printer, [(h.h.endstop, 'probe')])
        with self.assertRaisesRegex(RuntimeError, 'CLEARANCE'):
            h.motion._native_probe_begin(hmove)
        self.assertFalse(any(e[0] == 'move' for e in h.h.events))
        self.assertEqual(h.rail.get_range(), (0., 315.))

    def test_restart_during_contact_query_cannot_authorize_release_move(self):
        h = CoarseHome()
        h.motion.native_z_checks = [dict(pass_number=1)]
        def restart(now):
            h.h.shutdown = True
            return True
        h.h.endstop.query_endstop = restart
        hmove = homing.HomingMove(h.h.printer, [(h.h.endstop, 'probe')])
        with self.assertRaisesRegex(RuntimeError, 'session ended'):
            h.motion._native_probe_begin(hmove)
        self.assertFalse(any(e[0] == 'move' for e in h.h.events))

    def test_other_homing_or_probe_owners_cannot_start_recovery_moves(self):
        for state, phase, owned in (('IDLE', 'HOME_Z_NATIVE_PROBE', True),
                ('HOMING', 'HOME_X', True), ('HOMING', 'Z_FIVE_CONTACT_REFERENCES', True),
                ('HOMING', 'HOME_Z_NATIVE_PROBE', False)):
            with self.subTest(state=state, phase=phase, owned=owned):
                h = CoarseHome()
                h.motion.state, h.motion.phase = state, phase
                h.latched = True
                hmove = NS(get_mcu_endstops=lambda: [h.h.endstop] if owned else [])
                h.motion._native_probe_begin(hmove)
                self.assertEqual(h.motion.native_z_checks, [])
                self.assertEqual(h.h.events, [])
