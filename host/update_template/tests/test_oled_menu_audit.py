# Marcin Kowalik <mkowalik@agh.edu.pl>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Operator paths through the acknowledged OLED, shared macros and owners."""
import base64
import hashlib
import json
from pathlib import Path
import unittest
import zlib

import install
import test_install as installer_tests

from test_settings_information import session
from test_procedure_return import motion
from payload.m300_activity_graphics import menu_symbol


def select(h, label):
    rows = h.oled._rows(h.now)[1]
    h.oled.selection = next(i for i, row in enumerate(rows) if row[0] == label)
    h.oled._render(h.now)
    h.panel_display.pump()
    h.oled._select(h.now)
    while h.callbacks:
        h.callbacks.pop(0)(h.now)
    h.p._tick(h.now)


class OledMenuAuditTests(unittest.TestCase):
    def test_previous_published_oled_modules_upgrade_and_roll_back_without_allowing_local_edits(self):
        h = installer_tests.InstallerTests(methodName='runTest')
        h.setUp()
        self.addCleanup(h.tearDown)
        previous = json.loads((Path(__file__).parent/'reference/r1617_oled_modules.json').read_text())
        installed = {}
        for name, record in previous['files'].items():
            data = zlib.decompress(base64.b64decode(record['zlib_base64']))
            self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
            path = h.root/'klippy/extras'/name
            path.write_bytes(data)
            installed[path] = data
        receipt = install.apply(h.root, h.config, install.plan(h.root, h.config))
        for path, old in installed.items():
            self.assertNotEqual(path.read_bytes(), old)
            self.assertEqual(path.read_bytes(), (Path(__file__).resolve().parents[1]/'payload'/path.name).read_bytes())
        self.assertEqual(install.plan(h.root, h.config), [])
        install.rollback(receipt, h.root, h.config)
        for path, old in installed.items():
            self.assertEqual(path.read_bytes(), old)
        path = next(iter(installed))
        modified = installed[path] + b'\n# unreviewed local change\n'
        path.write_bytes(modified)
        with self.assertRaisesRegex(ValueError, 'unknown M300 runtime module'):
            install.plan(h.root, h.config)
        self.assertEqual(path.read_bytes(), modified)

    def test_fan_test_entered_from_oled_keeps_both_switches_and_returns_to_its_row(self):
        with session() as h:
            h.ui.history.stack[:] = ['main', 'zortrax']
            selected = next(i for i, row in enumerate(h.menu.rows(h.now)[1]) if row[0] == 'Fan test')
            select(h, 'Fan test')
            self.assertEqual((h.menu.page, h.oled.page), ('fan_test', 'm04'))
            for label in ('Toggle upper fan (Disabled)', 'Toggle lower fan (Disabled)',
                          'Toggle upper fan (Enabled)', 'Toggle lower fan (Enabled)'):
                select(h, label)
                self.assertEqual((h.menu.page, h.oled.page), ('fan_test', 'm04'))
            select(h, 'Back')
            self.assertEqual((h.menu.page, h.oled.page, h.oled.selection), ('maintenance', 'm04', selected))
            self.assertEqual(h.ui.history.stack, ['main', 'zortrax'])
            self.assertIsNone(h.fans.test)
            h.assert_restored(self)

    def test_fan_test_long_press_uses_back_instead_of_the_status_shortcut(self):
        for selection in (0, 1, 2):
            with self.subTest(selection=selection), session() as h:
                select(h, 'Fan test')
                h.oled.selection = selection
                h.oled._render(h.now)
                h.panel_display.pump()
                h.panel_packet(False)
                h.panel_packet(True, 1, 0, 0, 1)
                h.p._tick(h.now)
                self.assertEqual((h.menu.page, h.oled.page), ('maintenance', 'm04'))
                self.assertEqual(h.menu.rows(h.now)[1][h.oled.selection][0], 'Fan test')
                self.assertIsNone(h.fans.test)
                h.assert_restored(self)

    def test_status_repaint_after_a_fan_toggle_cannot_end_the_interactive_test(self):
        with session() as h:
            select(h, 'Fan test')
            select(h, 'Toggle upper fan (Disabled)')
            token, phase, speed = h.fans.token, h.fans.phase, h.upper.speed
            h.oled._show_status()
            h.p._tick(h.now)
            self.assertEqual((h.menu.page, h.oled.page), ('fan_test', 'm04'))
            self.assertEqual((h.fans.token, h.fans.phase, h.upper.speed), (token, phase, speed))
            self.assertIsNotNone(h.fans.test)
            select(h, 'Back')
            self.assertEqual(h.menu.page, 'maintenance')

    def test_an_old_completion_update_cannot_steal_the_active_fan_view(self):
        with session() as h:
            status, update = motion(h)
            update('COMPLETE')
            h.menu._navigate('maintenance')
            h.oled.page = 'm04'
            select(h, 'Fan test')
            select(h, 'Toggle lower fan (Disabled)')
            h.now += .1
            status['phase_id'] += 1  # A late observation of the old session.
            h.p._tick(h.now)
            self.assertEqual(h.p.view(h.now)['owner'], 'm300_fans')
            self.assertEqual((h.menu.page, h.oled.page), ('fan_test', 'm04'))
            self.assertTrue(h.fans.test['lower'])

    def test_current_procedure_opens_an_idle_oled_view_and_back_returns_to_maintenance(self):
        with session() as h:
            select(h, 'Current procedure')
            self.assertEqual((h.menu.page, h.oled.page), ('procedure', 'm04'))
            self.assertFalse(h.p.view(h.now)['busy'])
            select(h, 'Back')
            self.assertEqual((h.menu.page, h.oled.page), ('maintenance', 'm04'))
            self.assertEqual(h.menu.rows(h.now)[1][h.oled.selection][0], 'Current procedure')

    def test_fan_fault_back_restores_navigation_without_clearing_the_fault(self):
        with session() as h:
            select(h, 'Fan test')
            h.cooling['forced_cooling'] = True
            h.fans._tick(h.now)
            h.p._tick(h.now)
            self.assertEqual(h.fans.state, 'FAULT')
            select(h, 'Back')
            self.assertEqual((h.menu.page, h.oled.page), ('maintenance', 'm04'))
            self.assertEqual(h.fans.state, 'FAULT')
            self.assertTrue(h.cooling['forced_cooling'])

    def test_current_procedure_does_not_restart_or_reset_an_active_fan_test(self):
        with session() as h:
            select(h, 'Fan test')
            select(h, 'Toggle upper fan (Disabled)')
            token, phase, speed = h.fans.token, h.fans.phase, h.upper.speed
            h.run('M300_PROCEDURE')
            self.assertEqual((h.menu.page, h.oled.page), ('fan_test', 'm04'))
            self.assertEqual((h.fans.token, h.fans.phase, h.upper.speed), (token, phase, speed))

    def test_explicit_current_procedure_reopens_a_dismissed_homing_view_without_restarting_it(self):
        with session() as h:
            status, update = motion(h)
            h.oled._show_status()
            update()
            h.oled._show_status()
            h.menu._navigate('maintenance')
            h.oled.page = 'm04'
            token, phase = status['session_token'], status['phase_id']
            select(h, 'Current procedure')
            self.assertEqual((h.menu.page, h.oled.page), ('procedure', 'm04'))
            self.assertEqual((status['session_token'], status['phase_id']), (token, phase))
            update('COMPLETE')
            self.assertEqual((h.menu.page, h.oled.page), ('maintenance', 'm04'))

    def test_back_from_a_homing_fault_restores_the_screen_that_started_it(self):
        with session() as h:
            h.oled._show_status()
            status, update = motion(h)
            update()
            update('FAULT')
            select(h, 'Back')
            self.assertEqual(h.oled.page, 'status')
            self.assertEqual(status['state'], 'FAULT')

    def test_explicit_terminal_view_always_offers_back_without_clearing_its_owner(self):
        with session() as h:
            select(h, 'Fan test')
            h.action('BACK')
            h.p._tick(h.now)
            token = h.fans.token
            select(h, 'Current procedure')
            self.assertEqual(h.menu.page, 'procedure')
            select(h, 'Back')
            self.assertEqual((h.menu.page, h.oled.page), ('maintenance', 'm04'))
            self.assertEqual((h.fans.token, h.fans.state), (token, 'COMPLETE'))

    def test_pid_menu_uses_the_same_public_macros_as_fluidd(self):
        with session() as h:
            h.menu.page = 'native_pid'
            rows = dict(h.menu.rows(h.now)[1])
            self.assertEqual(rows['Hotend PID 200C'], ('native_gcode', 'PID_HOTEND TARGET=200'))
            self.assertEqual(rows['Bed PID 60C'], ('native_gcode', 'PID_BED TARGET=60'))
            self.assertEqual(rows['Save calibration'], ('native_gcode', 'PID_SAVE'))
            for label, native in (('Hotend PID 200C', 'PID_CALIBRATE HEATER=extruder TARGET=200'),
                                  ('Bed PID 60C', 'PID_CALIBRATE HEATER=heater_bed TARGET=60'),
                                  ('Save calibration', 'SAVE_CONFIG')):
                self.assertEqual(menu_symbol('native_pid', 'm04', [(label, rows[label])]),
                                 menu_symbol('native_pid', 'm04', [(label, ('native_gcode', native))]))
            for state in ('printing', 'paused'):
                h.print_state = state
                self.assertTrue(all(action is None for _, action in h.menu.rows(h.now)[1][1:]))

    def test_material_macros_from_oled_keep_the_invoking_row_after_completion(self):
        for label, operation, waiting in (('Load the material', 'LOAD', 'WAIT_INSERT'),
                                           ('Unload the material', 'UNLOAD', 'WAIT_UNLOAD')):
            with self.subTest(operation=operation), session() as h:
                h.menu.page = 'material'
                h.ui.history.stack[:] = ['main', 'zortrax']
                select(h, label)
                self.assertEqual(h.menu.page, 'procedure')
                self.assertEqual(h.f.get_status(h.now)['operation'], operation)
                h.heat(h.f, waiting)
                h.action('CONFIRM')
                h.until(h.f, 'COMPLETE')
                h.p._tick(h.now)
                self.assertEqual((h.menu.page, h.oled.page), ('material', 'm04'))
                self.assertEqual(h.menu.rows(h.now)[1][h.oled.selection][0], label)
                self.assertEqual(h.ui.history.stack, ['main', 'zortrax'])
                h.assert_restored(self)


if __name__ == '__main__':
    unittest.main()
