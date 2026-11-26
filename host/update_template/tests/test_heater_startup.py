# Marcin Kowalik <mkowalik@agh.edu.pl>
# test_heater_startup.py - Sprawdza okno kontroli dogrzewania M300 i zachowanie konfiguracji operatora.
"""Native verification tuning, include ownership and exact config rollback."""
import configparser
from pathlib import Path
import unittest

import install
import m300_profile as profile
import test_install


class HeaterStartupTests(unittest.TestCase):
    def fixture(self):
        h = test_install.InstallerTests(methodName='runTest')
        h.setUp()
        self.addCleanup(h.tearDown)
        return h

    def test_new_host_and_upgrade_share_40_second_gain_window(self):
        config = configparser.RawConfigParser()
        config.read_string((Path(__file__).resolve().parents[1]/'payload/m300_classic_base.cfg').read_text())
        self.assertEqual(dict(config['verify_heater extruder']), {'check_gain_time': '40'})
        self.assertEqual(profile.option(profile.EXTRUDER_VERIFY, 'check_gain_time'), '40')

    def test_upgrade_preserves_saved_pid_and_can_roll_back_exactly(self):
        h = self.fixture()
        saved = '#*# <--- SAVE_CONFIG --->\n#*# [extruder]\n#*# pid_kp = 15.123\n'
        original = '[mcu]\nserial: /dev/ttyS1\n' + saved
        h.config.write_text(original)
        receipt = install.apply(h.root, h.config, install.plan(h.root, h.config))
        text = h.config.read_text()
        self.assertLess(text.index('[verify_heater extruder]'), text.index('#*#'))
        self.assertTrue(text.endswith(saved))
        self.assertEqual(install.plan(h.root, h.config), [])
        install.rollback(receipt, h.root, h.config)
        self.assertEqual(h.config.read_text(), original)

    def test_existing_root_verification_parameters_are_preserved(self):
        h = self.fixture()
        custom = '[verify_heater extruder]\ncheck_gain_time: 30\nmax_error: 90\n'
        h.config.write_text('[mcu]\nserial: /dev/ttyS1\n' + custom)
        install.apply(h.root, h.config, install.plan(h.root, h.config))
        self.assertIn(custom, h.config.read_text())
        self.assertEqual(h.config.read_text().count('[verify_heater extruder]'), 1)

    def test_existing_verification_include_is_not_duplicated_or_modified(self):
        h = self.fixture()
        included = h.config.parent/'heater_checks.cfg'
        custom = '[verify_heater extruder]\ncheck_gain_time: 25\nheating_gain: 3\n'
        included.write_text(custom)
        h.config.write_text('[mcu]\nserial: /dev/ttyS1\n[include heater_checks.cfg]\n')
        install.apply(h.root, h.config, install.plan(h.root, h.config))
        self.assertNotIn('[verify_heater extruder]', h.config.read_text())
        self.assertEqual(included.read_text(), custom)
        self.assertEqual(install.plan(h.root, h.config), [])
