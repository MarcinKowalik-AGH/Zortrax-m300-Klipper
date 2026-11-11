"""Reproduce beta.14's idle-clock livelock and exercise real dispatch entrypoints.

Native ToolHead timing methods and G-code/pause parsers are unmodified snapshots.
MCU position, heaters and wall clock are modeled; no physical-printer claim.
"""
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

from test_print_control import Harness
from test_macro_dispatch import ENV, templates
from tests.reference.native_toolhead_timing import ToolHeadTiming
import m300_profile


class NativeClock(ToolHeadTiming):
    def __init__(self, h):
        self.h = h
        self.reactor = h.reactor
        self.printer = h.printer
        self.mcu = NS(estimated_print_time=lambda now: now)
        self.motion_queuing = NS(calc_step_gen_restart=lambda now: h.busy_until)
        self.print_time = h.busy_until
        self.special_queuing_state = 'NeedPrime'
        self.pending = False
        self.reads = self.flushes = 0
        self.lookahead = NS(is_empty=lambda: not self.pending,
                            set_flush_time=lambda value: None)
        h.toolhead.get_last_move_time = self.read
        h.toolhead.check_busy = self.status

    def _process_lookahead(self):
        if self.pending:
            self.flushes += 1
            self.pending = False
            self.print_time = max(self.print_time, self.h.busy_until)

    def read(self):
        self.reads += 1
        return self.get_last_move_time()

    def status(self, now):
        self.print_time = max(self.print_time, self.h.busy_until)
        return self.check_busy(now)


def deposited_moves(h):
    old = [100., 110., 10., 17.]
    result = []
    for item in h.events:
        if item[0] != 'move':continue
        pos = list(item[1])
        if pos[3] > old[3]:
            axes = ''.join(axis for i, axis in enumerate('xyz') if pos[i] != old[i])
            result.append((axes, old, pos))
        old = pos
    return result


class PrintDrainPurgeTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.addCleanup(self.h.close)
        self.clock = NativeClock(self.h)

    def start(self, args=''):
        h = self.h
        h.run('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60 ' + args)
        h.stop_worker()
        h.control_until('IDLE')

    def test_reference_reproduces_old_empty_queue_polling_livelock(self):
        h = self.h
        for _ in range(100):
            h.now += .25
            h.toolhead.get_last_move_time()  # beta.14 implementation
            queued, now, empty = h.toolhead.check_busy(h.now)
            self.assertTrue(empty)
            self.assertAlmostEqual(queued-now, .25)
            self.assertFalse(queued <= now)

    def test_idle_drain_never_reprimes_native_clock(self):
        for _ in range(100):
            self.h.now += .25
            self.assertTrue(self.h.c._drained(self.h.now))
        self.assertEqual(self.clock.reads, 0)

    def test_pending_lookahead_is_flushed_once_then_observed(self):
        h = self.h
        self.clock.pending = True
        h.busy_until = h.now + 3.
        self.assertFalse(h.c._drained(h.now))
        for _ in range(13):
            h.now += .25
            result = h.c._drained(h.now)
        self.assertTrue(result)
        self.assertEqual((self.clock.reads, self.clock.flushes), (1, 1))

    def test_fluidd_pause_endpoint_parks_after_worker_and_motion_drain(self):
        h = self.h
        h.web._endpoints['pause_resume/pause'](None)
        h.step_control()
        self.assertEqual(h.position[:3], [100., 110., 10.])
        h.stop_worker()
        h.control_until('PAUSED')
        self.assertEqual(h.position[:3], [300., 305., 15.])
        self.assertTrue(h.pause.is_paused)
        self.assertEqual(h.sd.file_position, 123)

    def test_fluidd_resume_endpoint_restores_origin_and_native_worker(self):
        h = self.h
        h.pause_print()
        h.web._endpoints['pause_resume/resume'](None)
        h.control_until('IDLE')
        self.assertEqual(h.position[:3], [100., 110., 10.])
        self.assertFalse(h.pause.is_paused)
        self.assertEqual(h.sd.work_timer, 'native')

    def test_fluidd_cancel_active_print_closes_file_and_finishes_park(self):
        h = self.h
        h.web._endpoints['pause_resume/cancel'](None)
        self.assertEqual((h.hotend.target, h.bed.target), (0., 0.))
        h.stop_worker()
        h.control_until('IDLE')
        self.assertIsNone(h.sd.current_file)
        self.assertFalse(h.pause.is_paused)
        self.assertEqual(h.print_state, 'cancelled')
        self.assertEqual(h.position[:2], [300., 305.])
        self.assertNotIn(('native_resume',), h.events)

    def test_fluidd_cancel_during_parking_is_not_a_second_pause(self):
        h = self.h
        h.web._endpoints['pause_resume/pause'](None)
        h.stop_worker()
        h.step_control()
        h.web._endpoints['pause_resume/cancel'](None)
        h.control_until('IDLE')
        self.assertEqual(h.print_state, 'cancelled')
        self.assertFalse(h.pause.is_paused)
        self.assertIsNone(h.sd.current_file)

    def test_cancel_clears_native_pause_before_waiting_for_motion(self):
        h = self.h
        h.pause_print()
        h.busy_until = h.now + 20.
        h.web._endpoints['pause_resume/cancel'](None)
        h.step_control()
        self.assertEqual(h.print_state, 'cancelled')
        self.assertIsNone(h.sd.current_file)
        self.assertFalse(h.pause.is_paused)
        self.assertEqual(h.c.phase, 'WAIT_CANCEL_DRAIN')
        h.control_until('IDLE')

    def test_cancel_with_lost_homing_still_closes_native_job(self):
        h = self.h
        h.pause_print()
        h.homed = ''
        h.run('CANCEL_PRINT')
        h.control_until('IDLE')
        self.assertEqual(h.print_state, 'cancelled')
        self.assertFalse(h.pause.is_paused)
        self.assertEqual((h.hotend.target, h.bed.target), (0., 0.))

    def test_end_does_not_stall_in_idle_clock_drain(self):
        h = self.h
        h.run('ZORTRAX_PRINT_END')
        h.stop_worker()
        h.control_until('IDLE')
        self.assertEqual(h.position[:3], [300., 305., 15.])
        self.assertEqual((h.hotend.target, h.bed.target), (0., 0.))
        self.assertEqual(h.sd.work_timer, 'native')  # EOF still native-owned

    def test_start_has_two_y_and_two_x_extruding_lines(self):
        self.start()
        lines = deposited_moves(self.h)
        self.assertEqual([x[0] for x in lines], ['y', 'y', 'x', 'x'])
        self.assertGreater(lines[0][2][1], lines[0][1][1])
        self.assertLess(lines[1][2][1], lines[1][1][1])
        self.assertGreater(lines[2][2][0], lines[2][1][0])
        self.assertLess(lines[3][2][0], lines[3][1][0])
        self.assertTrue(all(abs(x[2][2]-.28)<1.e-9 for x in lines))

    def test_cr10_350mm_request_is_clipped_to_m300_not_509mm_park(self):
        self.start('PURGE=350')
        lines = deposited_moves(self.h)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0][2][1], 300.)
        self.assertEqual(lines[2][2][0], 300.)
        for _, begin, end in lines:
            self.assertTrue(all(0. <= p <= 300. for p in begin[:2]+end[:2]))
        for _, begin, end in lines:
            distance = sum(abs(a-b) for a,b in zip(begin[:2],end[:2]))
            self.assertAlmostEqual(end[3]-begin[3], distance*20./350., places=4)

    def test_cancel_after_completion_does_not_restore_heaters_later(self):
        h = self.h
        h.pause_print()
        h.run('CANCEL_PRINT')
        h.control_until('IDLE')
        h.step_control(1900.)
        self.assertEqual((h.hotend.target, h.bed.target), (0., 0.))
        self.assertEqual(h.print_state, 'cancelled')

    def test_nonfinite_or_negative_purge_is_rejected_before_stopping_print(self):
        h = self.h
        for value in ('nan', 'inf', '-1', '0', '1001'):
            with self.subTest(value=value):
                with self.assertRaises(h.printer.command_error):
                    h.run('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60 PURGE='+value)
                self.assertEqual(h.c.state, 'IDLE')
                self.assertFalse(h.sd.must_pause_work)

    def test_start_macro_uses_slicer_targets_and_forwards_purge(self):
        h = self.h
        text = ENV.from_string(templates()['START_PRINT']).render(
            params={'PURGE':'350'}, printer=NS(extruder=h.hotend,heater_bed=h.bed))
        h.run(text)
        self.assertEqual(h.c.operation['targets'], {'hotend':240., 'bed':60.})
        self.assertEqual(h.c.operation['purge_length'], 350.)

    def test_start_macro_explicit_targets_win_over_slicer_targets(self):
        h = self.h
        text = ENV.from_string(templates()['START_PRINT']).render(
            params={'EXTRUDER_TEMP':'230','BED_TEMP':'50'},
            printer=NS(extruder=h.hotend,heater_bed=h.bed))
        h.run(text)
        self.assertEqual(h.c.operation['targets'], {'hotend':230., 'bed':50.})

    def test_exact_beta14_start_macro_migrates_idempotently(self):
        old = '''[gcode_macro START_PRINT]
description: Concurrent heating, M300 native homing, saved mesh and bounded purge
gcode:
    {% set hotend = params.EXTRUDER_TEMP|default(0)|float %}
    {% set bed = params.BED_TEMP|default(60)|float %}
    {% set mesh = params.MESH|default('AUTO') %}
    ZORTRAX_PRINT_START EXTRUDER_TEMP={hotend} BED_TEMP={bed} MESH={mesh}
'''
        new = m300_profile.convert_text(old)
        self.assertIn('params.PURGE', new)
        self.assertIn('printer.extruder.target', new)
        self.assertEqual(m300_profile.convert_text(new), new)

    def test_operator_modified_start_macro_is_not_overwritten(self):
        old = '[gcode_macro START_PRINT]\ngcode:\n    M117 Operator macro\n    G1 X8\n'
        self.assertEqual(m300_profile.convert_text(old), old)

    def test_purge_error_restores_parser_state_without_resuming(self):
        h = self.h
        h.run('G91\nM82\nM220 S150\nM221 S200')
        original = h.toolhead.move
        def fail_extrusion(pos,speed):
            if pos[3] > h.position[3]:raise h.printer.command_error('injected purge error')
            return original(pos,speed)
        h.toolhead.move = fail_extrusion
        h.gmove.move_with_transform = fail_extrusion
        h.run('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        h.stop_worker()
        for _ in range(40):h.step_control()
        self.assertEqual(h.c.state, 'FAILED')
        self.assertFalse(h.gmove.absolute_coord)
        self.assertTrue(h.gmove.allow_absolute_extrude)
        self.assertAlmostEqual(h.gmove.speed_factor, 1.5/60.)
        self.assertEqual(h.gmove.extrude_factor, 2.)
        self.assertNotIn(('native_resume',), h.events)

if __name__ == '__main__':unittest.main()
