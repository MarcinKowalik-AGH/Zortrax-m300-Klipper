import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install


class InstallerTests(unittest.TestCase):
    def test_r164_temperature_migration_updates_includes_and_rolls_back_exactly(self):
        source=('[mcu]\nserial: /dev/ttyS1\n'
                '[m300_calibration]\nprocedure_temperature: 180\n'
                '[m300_filament]\nfilament_qualified: False\n'
                '[include m300_tests.cfg]\n'
                '#*# <--- SAVE_CONFIG --->\n#*# pid_Kp = 15.152\n')
        macros=('[gcode_macro TEST_ZORTRAX_LEVEL]\ngcode:\n'
                '    ZORTRAX_PROCEDURE_START OP=LEVEL TEMP={params.TEMP|default(180)|float}\n'
                '    M118 My retained command\n'
                '[gcode_macro ZORTRAX_LOAD]\ngcode:\n'
                '    ZORTRAX_PROCEDURE_START OP=LOAD TEMP={params.TEMP|default(0)|float}\n'
                '[gcode_macro ZORTRAX_UNLOAD]\ngcode:\n'
                '    ZORTRAX_PROCEDURE_START OP=UNLOAD TEMP={params.TEMP|default(0)|float}\n')
        self.config.write_text(source);path=self.config.parent/'m300_tests.cfg';path.write_text(macros)
        receipt=install.apply(self.root,self.config,install.plan(self.root,self.config))
        self.assertIn('procedure_temperature: 260',self.config.read_text())
        self.assertIn('procedure_temperature: 240',self.config.read_text())
        self.assertIn('filament_qualified: True',self.config.read_text())
        self.assertIn('default(260)',path.read_text())
        self.assertEqual(path.read_text().count('default(240)'),2)
        self.assertIn('M118 My retained command',path.read_text())
        self.assertEqual(install.plan(self.root,self.config),[])
        install.rollback(receipt,self.root,self.config)
        self.assertEqual(self.config.read_text(),source)
        self.assertEqual(path.read_text(),macros)

    def test_native_m07_upgrade_preserves_sensor_include_pid_e_z315_and_existing_test_macros(self):
        source=('[mcu]\nserial: /dev/ttyS1\nbaud: 1500000\n'
            '[stepper_z]\nposition_min: 0\nposition_max: 315\nrotation_distance: 4\n'
            '[extruder]\nrotation_distance: 26.133\n'
            '[m300_job]\nworkflow_qualified: False\n'
            '[m300_calibration]\nqualified: False\nworkflow: M07_STOCK\nstock_steps_per_mm: 800\n'
            '[include m300_sensors.cfg]\n[include m300_tests.cfg]\n'
            '#*# <--- SAVE_CONFIG --->\n#*# [extruder]\n#*# pid_kp = 15.152\n')
        self.config.write_text(source)
        sensors=self.config.parent/'m300_sensors.cfg';sensor_data=b'# Original sensor conversion bytes\n'
        sensors.write_bytes(sensor_data)
        macros=self.config.parent/'m300_tests.cfg'
        original_macro='[gcode_macro TEST_M300_STATUS]\ngcode:\n    M105\n'
        macros.write_text(original_macro)
        changes=install.plan(self.root,self.config)
        receipt=install.apply(self.root,self.config,changes)
        self.assertEqual(sensors.read_bytes(),sensor_data)
        for line in ('position_min: 0','position_max: 315','rotation_distance: 26.133',
                     'workflow_qualified: False','#*# pid_kp = 15.152','[include m300_sensors.cfg]'):
            self.assertIn(line,self.config.read_text())
        self.assertIn(original_macro.replace('TEST_M300_STATUS','TEST_ZORTRAX_STATUS'),macros.read_text())
        self.assertIn('[gcode_macro TEST_ZORTRAX_LEVEL]',macros.read_text())
        self.assertEqual(install.plan(self.root,self.config),[])
        install.rollback(receipt,self.root,self.config)
        self.assertEqual(self.config.read_text(),source)
        self.assertEqual(sensors.read_bytes(),sensor_data)
        self.assertEqual(macros.read_text(),original_macro)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name) / 'klipper'
        (self.root / 'klippy/extras').mkdir(parents=True)
        self.config = pathlib.Path(self.temp.name) / 'config/printer.cfg'
        self.config.parent.mkdir()
        self.original = b'[mcu]\nserial: /dev/ttyS1\n\n#*# <--- SAVE_CONFIG --->\n#*# pid_Kp = 15.152\n'
        self.config.write_bytes(self.original)
        self.previous_menu = (ROOT / 'tests/reference/r155_menu.py').read_bytes()
        (self.root / 'klippy/extras/m300_menu.py').write_bytes(self.previous_menu)
        self.previous_ui = (ROOT / 'tests/reference/previous_m11_state.py').read_bytes()
        (self.root / 'klippy/extras/m300_ui_m11_state.py').write_bytes(self.previous_ui)
        self.api = patch.object(install, 'check_api', return_value=None)
        self.api.start()
    def tearDown(self):
        self.api.stop()
        self.temp.cleanup()

    def test_plan_is_read_only_and_places_include_before_save_config(self):
        changes = install.plan(self.root, self.config)
        self.assertEqual(len(changes), len(install.NAMES) + 5)
        self.assertEqual(self.config.read_bytes(), self.original)
        after = next(new for p, _, new in changes if p == self.config)
        self.assertLess(after.index(b'[include'), after.index(b'#*# <--- SAVE_CONFIG'))
        self.assertTrue(after.endswith(b'#*# pid_Kp = 15.152\n'))

    def test_apply_idempotent_rollback_restores_exact_configuration(self):
        changes = install.plan(self.root, self.config)
        receipt = install.apply(self.root, self.config, changes)
        self.assertEqual(install.plan(self.root, self.config), [])
        self.assertEqual(install.rollback(receipt, self.root, self.config),
                         len(install.NAMES) + 5)
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertFalse((self.config.parent / 'm300_display.cfg').exists())

    def test_preserve_existing_valid_display_settings(self):
        settings = self.config.parent / 'm300_display.cfg'
        data = b'[m300_display]\ntimeout: 600\ndim_contrast: 20\n'
        settings.write_bytes(data)
        changes = install.plan(self.root, self.config)
        self.assertFalse(any(p == settings for p, _, _ in changes))
        self.assertEqual(settings.read_bytes(), data)

    def test_invalid_existing_configuration_refused(self):
        (self.config.parent / 'm300_display.cfg').write_text('[m300_display]\ntimeout: nan\n')
        with self.assertRaises(ValueError):
            install.plan(self.root, self.config)

    def test_rollback_does_not_clobber_later_edits(self):
        receipt = install.apply(self.root, self.config,
                                install.plan(self.root, self.config))
        self.config.write_text(self.config.read_text() + '# later user change\n')
        with self.assertRaises(ValueError):
            install.rollback(receipt, self.root, self.config)
        self.assertIn('# later user change', self.config.read_text())
        self.assertTrue((self.root / 'klippy/extras/m300_display.py').exists())

    def test_unknown_existing_module_refused_without_any_write(self):
        p = self.root / 'klippy/extras/m300_display.py'
        p.write_text('unknown')
        with self.assertRaises(ValueError):
            install.plan(self.root, self.config)
        self.assertEqual(p.read_text(), 'unknown')
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_unknown_core_module_is_not_overwritten_by_factory_upgrade(self):
        p = self.root / 'klippy/extras/m300_mcu.py'
        p.write_text('# local core change\n')
        with self.assertRaises(ValueError):
            install.plan(self.root, self.config)
        self.assertEqual(p.read_text(), '# local core change\n')
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_published_r157_presentation_is_a_supported_upgrade(self):
        path = self.root / 'klippy/extras/m300_ui_m11_state.py'
        path.write_bytes((ROOT / 'tests/reference/r157_ui_m11_state.py').read_bytes())
        changes = install.plan(self.root, self.config)
        self.assertTrue(any(p == path for p, _, _ in changes))
        install.apply(self.root, self.config, changes)
        self.assertEqual(path.read_bytes(), (ROOT / 'payload/m300_ui_m11_state.py').read_bytes())

    def test_known_r153_runtime_upgrades_without_newer_homing_marker(self):
        for reference in (ROOT / 'tests/reference/r153').glob('*.py'):
            (self.root / 'klippy/extras' / reference.name).write_bytes(reference.read_bytes())
        motion = self.root / 'klippy/extras/m300_motion.py'
        self.assertNotIn('HOMING_UI_ABI', motion.read_text())
        changes = install.plan(self.root, self.config)
        receipt = install.apply(self.root, self.config, changes)
        self.assertEqual(install.plan(self.root, self.config), [])
        self.assertEqual(motion.read_bytes(), (ROOT / 'payload/m300_motion.py').read_bytes())
        install.rollback(receipt, self.root, self.config)
        self.assertEqual(motion.read_bytes(), (ROOT / 'tests/reference/r153/m300_motion.py').read_bytes())

    def test_factory_upgrade_preserves_z_m07_extruder_and_both_saved_pid_blocks(self):
        body = ('[mcu]\nserial: /dev/ttyS1\n'
                '[stepper_z]\nmicrosteps: 16\nrotation_distance: 8\nposition_max: 30\n'
                '[m300_calibration]\nstock_steps_per_mm: 400\n'
                '[extruder]\nrotation_distance: 26.133\n'
                '#*# <--- SAVE_CONFIG --->\n'
                '#*# [extruder]\n#*# control = pid\n#*# pid_Kp = 15.152\n'
                '#*# [heater_bed]\n#*# control = pid\n#*# pid_Kp = 61.966\n')
        self.config.write_text(body)
        changes = install.plan(self.root, self.config)
        after = next(new.decode() for path, _, new in changes if path == self.config)
        self.assertEqual(after.split('#*#', 1)[1], body.split('#*#', 1)[1])
        for line in ('rotation_distance: 8', 'stock_steps_per_mm: 400',
                     'rotation_distance: 26.133', 'position_max: 300'):
            self.assertIn(line, after)
        self.assertNotIn('z_profile:', after)

    def test_r161_lifecycle_upgrade_preserves_z312_and_can_be_rolled_back(self):
        life = self.root / 'klippy/extras/m300_lifecycle.py'
        previous = (ROOT / 'tests/reference/r153/m300_lifecycle.py').read_bytes()
        life.write_bytes(previous)
        self.config.write_text('[mcu]\nserial: /dev/ttyS1\nrestart_method: command\n'
                               '[stepper_z]\nposition_max: 312\nrotation_distance: 4\n'
                               '[m300_lifecycle]\nreconnect_on_host_start: True\n')
        changes = install.plan(self.root, self.config)
        receipt = install.apply(self.root, self.config, changes)
        self.assertEqual(life.read_bytes(), (ROOT / 'payload/m300_lifecycle.py').read_bytes())
        self.assertIn('position_max: 312', self.config.read_text())
        self.assertIn('rotation_distance: 4', self.config.read_text())
        self.assertEqual(install.plan(self.root, self.config), [])
        install.rollback(receipt, self.root, self.config)
        self.assertEqual(life.read_bytes(), previous)

    def test_verified_previous_display_upgrade_and_exact_rollback(self):
        previous = ROOT / 'tests/reference/previous_display'
        for name in ('m300_display.py', 'm300_display_stream.py'):
            (self.root / 'klippy/extras' / name).write_bytes(
                (previous / name).read_bytes())
        settings = self.config.parent / 'm300_display.cfg'
        settings.write_text('[m300_display]\ntimeout: 600\nnormal_contrast: 80\ndim_contrast: 20\n')
        self.config.write_text('[include m300_display.cfg]\n' + self.original.decode())
        saved = self.config.read_bytes()
        changes = install.plan(self.root, self.config)
        self.assertEqual(len(changes), len(install.NAMES) + 4)
        receipt = install.apply(self.root, self.config, changes)
        self.assertEqual(install.plan(self.root, self.config), [])
        self.assertEqual(install.profile.split_saved(self.config.read_text())[1],
                         install.profile.split_saved(saved.decode())[1])
        self.assertIn('[include m300_tests.cfg]', self.config.read_text())
        install.rollback(receipt, self.root, self.config)
        self.assertEqual(self.config.read_bytes(), saved)
        for name in ('m300_display.py', 'm300_display_stream.py'):
            self.assertEqual((self.root / 'klippy/extras' / name).read_bytes(),
                             (previous / name).read_bytes())
        self.assertFalse((self.root / 'klippy/extras/m300_display_oem.py').exists())
        self.assertFalse((self.root / 'klippy/extras/m300_display_moon.json').exists())

    def test_failed_partial_apply_restores_all_prior_bytes(self):
        changes = install.plan(self.root, self.config)
        original_write = install.atomic_write
        calls = []
        def fail_once(path, data):
            calls.append(path)
            if len(calls) == 3:
                raise OSError('simulated full disk')
            return original_write(path, data)
        with patch.object(install, 'atomic_write', fail_once):
            with self.assertRaises(OSError):
                install.apply(self.root, self.config, changes)
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertFalse(any((self.root / 'klippy/extras' / name).exists()
                             for name in install.NAMES if name not in
                             ('m300_menu.py', 'm300_ui_m11_state.py')))
        self.assertEqual((self.root / 'klippy/extras/m300_menu.py').read_bytes(),
                         self.previous_menu)

    def test_wildcard_include_does_not_get_duplicate_explicit_include(self):
        self.config.write_text('[include *.cfg]\n')
        changes = install.plan(self.root, self.config)
        self.assertEqual(len(changes), len(install.NAMES) + 4)
        self.assertFalse(any(p == self.config for p, _, _ in changes))

    def test_included_inline_section_refuses_duplicate(self):
        self.config.write_text('[include other.cfg]\n')
        (self.config.parent / 'other.cfg').write_text('[m300_display]\n')
        with self.assertRaises(ValueError):
            install.plan(self.root, self.config)


if __name__ == '__main__':
    unittest.main()
