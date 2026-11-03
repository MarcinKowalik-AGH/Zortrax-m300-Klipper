"""Native print state projection, OLED acknowledgement and delayed dispatch."""
from contextlib import contextmanager
from types import SimpleNamespace as NS
import unittest

from payload.m300_print_ui import M300PrintUI
from test_settings_information import session


def sample(**fields):
    event = dict(pressed=False, presses=0, releases=0, shorts=0, longs=0, delta=0)
    event.update(fields)
    return event


@contextmanager
def printing():
    with session() as h:
        h.sd = h.objects['virtual_sdcard']
        h.sd.print_stats = NS(state='printing', filename='one.gcode')
        h.sd.current_file = NS(name='one.gcode')
        h.sd.work_timer = object()
        h.ui_print = M300PrintUI(h.config)
        h.ui_print._ready()
        h.objects['m300_print_ui'] = h.ui_print
        h.oled.page = 'status'
        h.oled.menu_reverse = False
        h.status_wire = bytes([17]) * 8192
        h.oled.status_screen = NS(render=lambda now: h.status_wire)
        h.commands = []
        h.gcode.run_script_from_command = h.commands.append
        h.replayed = []
        h.objects['m300_models'] = NS(
            reprint_status=lambda now: dict(available=True, token='a'*32, filename='one.gcode'),
            reprint=h.replayed.append)
        yield h


def acknowledged(h):
    h.oled._render(h.now)
    h.oled.stream.previous = h.oled._render_wire
    return h.ui_print.receipt(h.oled.stream, h.oled._input_context())


def panel(h, event, receipt=None):
    return h.ui_print.panel(event, h.now, h.now, receipt, lambda: True,
                            printing_status=h.oled.page == 'status')


def pause(h):
    h.sd.print_stats.state = 'paused'
    h.sd.work_timer = None
    h.pause.is_paused = h.pause.sd_paused = True


class PrintContextTests(unittest.TestCase):
    def test_status_short_click_and_menu_navigation_during_print(self):
        with printing() as h:
            def deliver(event):
                h.oled.encoder.update = lambda params, received: event
                h.oled._panel({'#receive_time': h.now})
                h.callbacks.pop(0)(h.now)
                h.now += .25

            h.oled.page, h.menu.page = 'm04', 'settings'
            self.assertEqual(acknowledged(h)[0], h.status_wire)
            self.assertEqual(h.oled.page, 'status')
            deliver(sample(pressed=True, presses=1))
            deliver(sample(shorts=1, releases=1))
            self.assertEqual(h.oled.page, 'm04')
            self.assertIsNone(acknowledged(h))
            _, rows = h.menu.rows(h.now)
            self.assertGreater(len(rows), 1)
            old_selection = h.oled.selection
            deliver(sample(delta=1))
            self.assertNotEqual(h.oled.selection, old_selection)
            self.assertFalse(h.commands)
            self.assertEqual(h.sd.print_stats.state, 'printing')

    def test_oled_hold_calls_native_pause_once_and_consumes_release(self):
        with printing() as h:
            for i in range(42):
                acknowledged(h)
                h.oled.encoder.update = lambda params, received, i=i: sample(
                    pressed=True, presses=int(i == 0), longs=int(i == 3))
                h.oled._panel({'#receive_time': h.now})
                h.callbacks.pop(0)(h.now)
                if i < 40:
                    self.assertFalse(h.callbacks)
                    self.assertFalse(h.commands)
                elif i == 40:
                    h.callbacks.pop(0)(h.now)
                    pause(h)
                h.now += .25
            ack = acknowledged(h)
            self.assertTrue(panel(h, sample(shorts=1, releases=1), ack))
            self.assertEqual(h.commands, ['PAUSE'])
            self.assertEqual(ack[2][1], 'PAUSED')

    def test_external_pause_updates_shared_actions_and_stop_requires_ack(self):
        with printing() as h:
            pause(h)
            ack = acknowledged(h)
            self.assertEqual([r[0] for r in ack[3]],
                             ['Resume the print', 'Change the material', 'Stop the print'])
            panel(h, sample(delta=2), ack)
            panel(h, sample(shorts=1), ack)
            self.assertFalse(h.callbacks)
            ack = acknowledged(h)
            panel(h, sample(shorts=1), ack)
            ack = acknowledged(h)
            self.assertEqual(ack[2][1], 'STOP_CONFIRM')
            self.assertEqual(ack[4], 0)
            panel(h, sample(delta=1), ack)
            panel(h, sample(shorts=1), acknowledged(h))
            h.callbacks.pop(0)(h.now)
            self.assertEqual(h.commands, ['CANCEL_PRINT'])

    def test_old_pause_click_cannot_resume_next_file(self):
        with printing() as h:
            pause(h)
            panel(h, sample(shorts=1), acknowledged(h))
            self.assertTrue(h.callbacks)
            h.ui_print._new_file()
            h.callbacks.pop(0)(h.now)
            self.assertFalse(h.commands)

    def test_material_procedure_owns_screen_and_m25_has_no_saved_resume(self):
        with printing() as h:
            h.sd.print_stats.state = 'paused'
            self.assertEqual(acknowledged(h)[2][1], 'SD_PAUSED')
            self.assertFalse(acknowledged(h)[3])
            pause(h)
            h.objects['m300_filament'] = NS(machine=NS(active=True))
            self.assertIsNone(h.ui_print.view(h.now))

    def test_completion_requires_drained_queue_and_hold_then_close_is_local(self):
        with printing() as h:
            h.sd.print_stats.state = 'complete'
            h.sd.current_file = h.sd.work_timer = None
            h.busy_until = h.now + 1
            self.assertEqual(acknowledged(h)[2][1], 'DRAINING')
            h.now += 1.
            for i in range(41):
                panel(h, sample(pressed=True, presses=int(i == 0)), acknowledged(h))
                h.now += .25
            h.callbacks.pop(0)(h.now)
            self.assertEqual(h.replayed, ['a'*32])
            panel(h, sample(releases=1), acknowledged(h))
            panel(h, sample(shorts=1, releases=1), acknowledged(h))
            self.assertIsNone(h.ui_print.view(h.now))
            self.assertEqual(h.ui_print.view(h.now, include_dismissed=True)[1], 'a'*32)
