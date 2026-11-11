"""Shared state colors, procedure transitions and monotonic RGB alarm timing."""
from types import SimpleNamespace as NS
import unittest

from test_settings_information import session
from payload.m300_settings import PAGES
from payload.m300_thermal import M300Thermal


def rgb(h):
    h.m._indicators(h.now)
    return tuple(h.pins['m300_led_' + c] for c in 'rgb')


class StatusLightsTests(unittest.TestCase):
    def test_print_preparation_barriers_are_red_or_white_and_real_pause_is_purple(self):
        with session() as h:
            control=NS(state='STARTING',phase='HEATING',busy=True)
            control.get_status=lambda now:dict(state=control.state,phase=control.phase,busy=control.busy)
            h.objects['m300_print_control']=control
            h.print_state='paused'  # Worker barrier, not pause_resume.is_paused.
            self.assertEqual(rgb(h),(1.,0.,0.))
            control.state,control.phase='ENDING','END_PARK'
            self.assertEqual(rgb(h),(1.,1.,1.))
            control.state,control.phase='RESUMING','HEATING'
            self.assertEqual(rgb(h),(1.,0.,1.))

    def test_ready_menu_navigation_does_not_change_the_printer_color(self):
        with session() as h:
            for page in ('main', 'klipper', 'zortrax', 'maintenance', 'material', *PAGES):
                with self.subTest(page=page):
                    h.menu.page = page
                    self.assertEqual(rgb(h), (0., 1., 0.))
            h.hotend.temperature = 190.  # Passive cooling is still Ready.
            self.assertEqual(rgb(h), (0., 1., 0.))

    def test_native_heating_print_pause_and_completion_share_one_policy(self):
        with session() as h:
            h.hotend.target = 230.
            h.bed.target = 60.
            h.print_state = 'printing'
            self.assertEqual(rgb(h), (1., 0., 0.))
            h.hotend.temperature, h.bed.temperature = 230., 60.
            self.assertEqual(rgb(h), (1., 1., 1.))
            h.pause.is_paused = True
            h.hotend.target = 240.  # Material handling while paused stays purple.
            self.assertEqual(rgb(h), (1., 0., 1.))
            h.print_state, h.pause.is_paused = 'complete', False
            h.hotend.target = h.bed.target = 0.
            self.assertEqual(rgb(h), (0., 1., 0.))
            h.bed.target = 60.
            self.assertEqual(rgb(h), (1., 0., 0.))  # Manual temperature hold.

    def test_homing_leveling_material_and_pad_mesh_phases_are_observed(self):
        for name in ('m300_motion', 'm300_calibration', 'm300_filament', 'm300_pad_mesh'):
            with self.subTest(owner=name), session() as h:
                status = dict(state='HOMING', busy=True, phase='Z_PREHEAT')
                h.objects[name] = NS(get_status=lambda now: status)
                self.assertEqual(rgb(h), (1., 0., 0.))
                status.update(state='PROBING', phase='PROBING')
                self.assertEqual(rgb(h), (1., 1., 1.))
                status.update(state='COMPLETE', busy=False)
                self.assertEqual(rgb(h), (0., 1., 0.))
                status.update(state='FAILED')
                self.assertEqual(rgb(h), (1., 0., 0.))
                h.now += 5.
                self.assertEqual(rgb(h), (0., 1., 0.))

    def test_alarm_starts_red_changes_each_five_seconds_and_resets_after_recovery(self):
        with session() as h:
            h.now = 123.456
            h.print_state = 'error'
            start = h.now
            for elapsed, expected in ((0., (1., 0., 0.)), (4.999, (1., 0., 0.)),
                    (5., (0., 1., 0.)), (9.999, (0., 1., 0.)),
                    (10., (0., 0., 1.)), (14.999, (0., 0., 1.)),
                    (15., (1., 0., 0.)), (38., (0., 1., 0.))):
                h.now = start + elapsed
                self.assertEqual(rgb(h), expected)
            h.print_state = 'standby'
            self.assertEqual(rgb(h), (0., 1., 0.))
            h.print_state = 'error'
            self.assertEqual(rgb(h), (1., 0., 0.))

    def test_alarm_overrides_fixed_white_disabled_and_sleep_but_retains_brightness(self):
        with session() as h:
            h.settings.set_option('led_brightness', 8)
            for mode, expected in (('WHITE', (.5, .5, .5)), ('DISABLE', (0., 0., 0.))):
                h.print_state = 'standby'
                h.settings.set_option('light_mode', mode)
                self.assertEqual(rgb(h), expected)
                h.print_state = 'error'
                self.assertEqual(rgb(h), (.5, 0., 0.))
                h.now += 5.
                self.assertEqual(rgb(h), (0., .5, 0.))
            h.m.state = 'SLEEP'
            self.assertEqual(rgb(h), (0., .5, 0.))

    def test_error_has_priority_over_heating_pause_and_busy_owners(self):
        with session() as h:
            h.hotend.target = 230.
            h.print_state = 'paused'
            h.objects['m300_pad_mesh'] = NS(get_status=lambda now:dict(state='FAILED', busy=False))
            self.assertEqual(rgb(h), (1., 0., 0.))
            h.objects['m300_pad_mesh'].get_status = lambda now:dict(state='COMPLETE', busy=False)
            self.assertEqual(rgb(h), (1., 0., 1.))

    def test_thermal_diagnostic_uses_the_same_policy_without_recursion_or_uart(self):
        with session() as h:
            thermal = M300Thermal(h.config)
            thermal.heaters = {'extruder': h.hotend, 'heater_bed': h.bed}
            thermal.ready = True
            h.objects['m300_thermal'] = thermal
            before = h.board_reads
            for state, expected in (('standby', (0, 1, 0)), ('printing', (1, 1, 1)),
                                    ('paused', (1, 0, 1)), ('error', (1, 0, 0))):
                h.print_state = state
                self.assertEqual(thermal.led_rgb(h.now), expected)
                self.assertEqual(rgb(h), expected)
            self.assertEqual(h.board_reads, before)

    def test_unchanged_colors_emit_no_repeated_pin_updates(self):
        with session() as h:
            writes = []
            for c in 'rgb':
                h.objects['output_pin m300_led_' + c].gcrq.send_async_request = (
                    lambda value, c=c: writes.append((c, value)))
            h.print_state = 'error'
            start = h.now
            for i in range(1501):
                h.now = start + i / 100.
                h.m._indicators(h.now)
            self.assertEqual(len(writes), 12)  # Initial RGB, then only 5/10/15 s.


if __name__ == '__main__':
    unittest.main()
