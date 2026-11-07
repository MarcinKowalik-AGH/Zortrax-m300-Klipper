"""Configuration layout migration preserves effective hardware and saved PID."""
import configparser
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_display
import install
import m300_profile as profile


SAVED = ('#*# <---------------------- SAVE_CONFIG ---------------------->\n'
         '#*# DO NOT EDIT THIS BLOCK OR BELOW. The contents are auto-generated.\n'
         '#*# [extruder]\n#*# control = pid\n#*# pid_kp = 15.152\n'
         '#*# [heater_bed]\n#*# control = pid\n#*# pid_kp = 61.966\n')
SOURCE = ('# M300 TEST01: diagnostics only; no automatic ARM, motion, heat or flash.\n'
    '[mcu]\nserial = /dev/ttyS1\nbaud = 750000\n'
    '[m300_mcu]\nnative_control = True\n'
    '[printer]\nkinematics = cartesian\nmax_velocity = 300\nmax_accel = 700\nmax_z_velocity = 35.0\nmax_z_accel = 75.0\n'
    '[stepper_x]\nmicrosteps = 128\nposition_max = 300\nhoming_speed =50\n'
    '[stepper_y]\nposition_max = 305\n'
    '[stepper_z]\nrotation_distance = 4\nposition_max = 315\nhoming_speed = 15\n'
    '[probe]\npin = ^!PC7\nz_offset = 0\n'
    '[bed_mesh]\nmesh_min: 0,0\nmesh_max: 300,305\n'
    '[m300_pad_mesh]\n[m300_pad_mesh]\ncenter_bounds: 130,130,180,180\ncenter_x: 155\nedge_margin: 0\n'
    '[adc_temperature HOT]\ntemperature1 = 0\nvoltage1 = 0\ntemperature2 = 250\nvoltage2 = 1.25\n'
    '[adc_temperature BED]\ntemperature1 = 28048\nvoltage1 = 0.00079853479853479856\ntemperature2 = 738\nvoltage2 = 0.016769230769230769\n'
    '[extruder]\nrotation_distance = 26.133\nsensor_type = HOT\nmax_temp = 300\n'
    '[heater_bed]\nsensor_type = BED\nmax_temp = 120\n'
    '[m300_resources]\nrequire_motion_owner: True\nrequire_calibration_workflow: M07_STOCK\nrequire_cycle_owner: True\n'
    '[m300_job]\nworkflow_qualified: False\nm08_cycle_enabled: True\npause_timeout: 3600\n'
    '[m300_cycle]\nqualified: False\n'
    '[m300_maintenance]\nmax_jog_distance: 5\njog_speed: 1\nfan_test_seconds: 5\nservice_timeout: 300\n'
    '[m300_nvm]\npath: /home/klipper/retained/state.json\nmachine_id: KEPT\nmechanics_id: ALSO_KEPT\n'
    '[m300_motion]\nmode: native\nhome_xy: 150,158\n'
    '[include klipper_calibration.cfg]\n[include m300_fluidd.cfg]\n'+SAVED)
FLUIDD = ('# ZORTRAX M300 / R7. All physical work stays in M03/M07/M08.\n'
    '[gcode_macro PID_HOTEND]\ngcode:\n    PID_CALIBRATE HEATER=extruder TARGET={params.TARGET|default(200)|float}\n'
    '[gcode_macro ZORTRAX_PRINT]\ngcode:\n'
    '  {% if params.FILENAME is not defined %}\n'
    '    {action_raise_error("Select a checked file: ZORTRAX_PRINT FILENAME=...")}\n'
    '  {% endif %}\n  START_PRINT {rawparams}\n'
    '[gcode_macro MY_MACRO]\ngcode:\n    M118 Retained custom command\n')


def source_tree(folder):
    root = folder/'printer.cfg'
    return root, {root: SOURCE, folder/'m300_fluidd.cfg': FLUIDD,
                  folder/'klipper_calibration.cfg': '# Empty standard calibration aliases\n'}


def values(tree):
    parser = configparser.RawConfigParser(strict=False, inline_comment_prefixes=('#',';'))
    parser.read_string('\n'.join(block for text in tree.values()
                      for name, block in profile.blocks(text)[1] if not name.startswith('include ')))
    return {s: dict(parser.items(s)) for s in parser.sections()}


class ConfigLayoutTests(unittest.TestCase):
    def test_effective_hardware_geometry_paths_and_pid_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, tree = source_tree(Path(tmp))
            result, report = profile.organize_tree(tree, root)
            before, after = values(tree), values(result)
            for name, settings in before.items():
                expected = dict(settings)
                if name in ('m300_cycle','gcode_macro ZORTRAX_PRINT'):
                    self.assertNotIn(name, after)
                    continue
                for key in ({'m300_resources':['require_cycle_owner'],
                    'm300_job':['m08_cycle_enabled'],
                    'm300_maintenance':['max_jog_distance','jog_speed','fan_test_seconds']}.get(name, ())):
                    expected.pop(key)
                self.assertEqual(after[name], expected, name)
            self.assertEqual(profile.split_saved(result[root])[1], SAVED)
            self.assertEqual(report['removed_empty_duplicates'], ['m300_pad_mesh'])
            self.assertIn('M118 Retained custom command', result[root.parent/'m300_fluidd.cfg'])

    def test_temperature_conversion_blocks_are_moved_without_editing_a_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, tree = source_tree(Path(tmp))
            result, _ = profile.organize_tree(tree, root)
            old = {n:b.strip() for n,b in profile.blocks(tree[root])[1] if n.startswith('adc_temperature ')}
            new = {n:b.strip() for n,b in profile.blocks(result[root.parent/profile.THERMAL_TABLES])[1]}
            self.assertEqual(new, old)
            self.assertNotIn('[adc_temperature ', result[root])
            self.assertLess(result[root].index('[include '+profile.THERMAL_TABLES+']'),result[root].index('[extruder]'))

    def test_second_cleanup_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, tree = source_tree(Path(tmp))
            result, _ = profile.organize_tree(tree, root)
            again, _ = profile.organize_tree(result, root)
            self.assertEqual(result, again)

    def test_custom_cycle_references_and_nondefault_jog_hints_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, tree = source_tree(Path(tmp))
            tree[root] = SOURCE.replace('jog_speed: 1','jog_speed: 2').replace('max_jog_distance: 5','max_jog_distance: 8')
            tree[root.parent/'m300_fluidd.cfg'] += '[gcode_macro MY_CYCLE]\ngcode:\n    ZORTRAX_CYCLE_STATUS\n'
            result, _ = profile.organize_tree(tree, root)
            after = values(result)
            self.assertIn('m300_cycle', after)
            self.assertEqual(after['m300_resources']['require_cycle_owner'], 'True')
            self.assertEqual(after['m300_job']['m08_cycle_enabled'], 'True')
            self.assertEqual(after['m300_maintenance']['jog_speed'], '2')
            self.assertEqual(after['m300_maintenance']['max_jog_distance'], '8')

    def test_unknown_duplicate_or_nonincluded_target_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, tree = source_tree(Path(tmp))
            duplicate = dict(tree);duplicate[root] = SOURCE.replace(SAVED, '\n[mcu]\nbaud: 500000\n'+SAVED)
            with self.assertRaisesRegex(ValueError, 'unambiguous'):
                profile.organize_tree(duplicate, root)
            target = root.parent/profile.THERMAL_TABLES
            target.write_text('# Custom unrelated sensor table\n')
            with self.assertRaisesRegex(ValueError, 'non-included'):
                profile.organize_tree(tree, root)
            self.assertEqual(target.read_text(), '# Custom unrelated sensor table\n')

    def test_saved_include_data_and_non_native_mode_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, tree = source_tree(Path(tmp))
            nonnative = dict(tree);nonnative[root] = SOURCE.replace('native_control = True','native_control = False')
            with self.assertRaisesRegex(ValueError, 'already native'):
                profile.organize_tree(nonnative, root)
            tree[root.parent/'m300_fluidd.cfg'] += SAVED
            with self.assertRaisesRegex(ValueError, 'SAVE_CONFIG only'):
                profile.organize_tree(tree, root)

    def test_moonraker_cleanup_preserves_access_and_custom_update_sources(self):
        text = ('[server]\nhost: 0.0.0.0\nport: 7125\n'
            '[authorization]\ntrusted_clients:\n    192.168.0.0/16\n    10.0.0.0/8\n    192.168.0.0/16\n'
            'cors_domains:\n    *.local\n'
            '[update_manager fluidd]\ntype: web\nrepo: fluidd-core/fluidd\npath: /home/klipper/fluidd\n'
            '[update_manager fluidd-config]\norigin: https://github.com/fluidd-core/fluidd-config.git\n'
            '[update_manager custom]\nrepo: owner/custom\n')
        result, removed = profile.organize_moonraker(text, fluidd_config_unused=True)
        self.assertEqual(removed, ['update_manager fluidd','update_manager fluidd-config'])
        self.assertEqual(result.count('192.168.0.0/16'), 1)
        self.assertIn('10.0.0.0/8', result)
        self.assertIn('    *.local', result)
        self.assertIn('repo: owner/custom', result)
        self.assertEqual(profile.organize_moonraker(result,fluidd_config_unused=True)[0], result)
        custom = text.replace('fluidd-core/fluidd\n', 'owner/personal-fluidd\n')
        self.assertIn('[update_manager fluidd]',profile.organize_moonraker(custom)[0])

    def test_real_installer_organizes_atomically_and_rolls_back_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'klipper';extras=root/'klippy/extras';extras.mkdir(parents=True)
            folder=base/'config';folder.mkdir();config,tree=source_tree(folder)
            for path,text in tree.items():path.write_text(text)
            refs=Path(__file__).parent/'reference'
            (extras/'m300_menu.py').write_bytes((refs/'r155_menu.py').read_bytes())
            original={p:p.read_bytes() for p in tree}
            moonraker=folder/'moonraker.conf'
            moonraker.write_text('[server]\nport: 7125\n[update_manager fluidd]\ntype: web\nrepo: fluidd-core/fluidd\n')
            original[moonraker]=moonraker.read_bytes()
            with patch.object(install,'check_api',return_value=None):
                changes=install.plan(root,config,organize_config=True)
                receipt=install.apply(root,config,changes)
                self.assertEqual(install.plan(root,config,organize_config=True), [])
                self.assertEqual(install.plan(root,config), [])
                self.assertEqual(profile.split_saved(config.read_text())[1], SAVED)
                self.assertNotIn('[update_manager fluidd]',moonraker.read_text())
                install.rollback(receipt,root,config)
            for path,data in original.items():self.assertEqual(path.read_bytes(),data)
            self.assertFalse((folder/profile.THERMAL_TABLES).exists())
            self.assertFalse((folder/profile.SERVICE_CONFIG).exists())
