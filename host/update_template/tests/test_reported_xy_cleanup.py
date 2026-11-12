"""Exact macro supplied by the operator on 2026-11-12. No macro is executed."""
import json
from pathlib import Path
import unittest
import install
import m300_profile as profile
import m300_rc_ui
import test_install as helpers
from setup_fluidd import merge_groups

ROOT = Path(__file__).resolve().parents[1]
REPORTED = (ROOT/'tests/reference/reported_xy_200_20261112.cfg').read_text()
NAME = 'TEST_ZORTRAX_XY'
DIGEST = '53be4a2ac5933a02df7321ed45f99ef9fe82d82b59faead042f1c472ecf3580f'

class ReportedXYTests(unittest.TestCase):
    def harness(self):
        h=helpers.InstallerTests(methodName='runTest')
        h.setUp();self.addCleanup(h.tearDown)
        h.config.write_text("[mcu]\nserial: /dev/ttyS1\n[m300_mcu]\nnative_control: True\n")
        return h

    def test_rc1_release_module_upgrades_and_unknown_module_is_refused(self):
        h=self.harness();target=h.root/'klippy/extras/m300_release.py'
        previous=(ROOT/'tests/reference/rc1_m300_release.txt').read_bytes()
        target.write_bytes(previous)
        receipt=install.apply(h.root,h.config,install.plan(h.root,h.config))
        self.assertEqual(target.read_bytes(),(ROOT/'payload/m300_release.py').read_bytes())
        self.assertEqual(install.plan(h.root,h.config),[])
        install.rollback(receipt,h.root,h.config)
        self.assertEqual(target.read_bytes(),previous)
        target.write_bytes(previous+b'\n# Unknown operator modification\n')
        with self.assertRaisesRegex(ValueError,'unknown M300 runtime module'):
            install.plan(h.root,h.config)
        self.assertEqual(target.read_bytes(),previous+b'\n# Unknown operator modification\n')

    def test_exact_operator_body_is_allowlisted(self):
        self.assertEqual(m300_rc_ui.command_hash(REPORTED),DIGEST)
        bases=json.loads((ROOT/'RC_UI_BASELINES.json').read_text())
        self.assertIn(DIGEST,bases[NAME])
        self.assertIn('default(200)',REPORTED)
        self.assertIn('NAME=TEST_M300_XY_STATE',REPORTED)

    def test_known_body_removed_from_root_on_first_pass(self):
        for organized in (False,True):
            with self.subTest(organized=organized):
                h=self.harness()
                h.config.write_text(h.config.read_text()+REPORTED)
                original=h.config.read_bytes()
                receipt=install.apply(h.root,h.config,install.plan(h.root,h.config,organize_config=organized))
                self.assertNotIn('[gcode_macro '+NAME+']',h.config.read_text())
                self.assertEqual(install.plan(h.root,h.config,organize_config=organized),[])
                install.rollback(receipt,h.root,h.config)
                self.assertEqual(h.config.read_bytes(),original)

    def test_reported_body_in_include_removed_with_exact_rollback(self):
        h=self.harness();path=h.config.parent/'m300_tests.cfg'
        oldroot=h.config.read_text()+'[include m300_tests.cfg]\n'
        h.config.write_text(oldroot);path.write_text(REPORTED)
        receipt=install.apply(h.root,h.config,install.plan(h.root,h.config))
        self.assertNotIn(NAME,path.read_text())
        self.assertNotIn('[include m300_tests.cfg]',h.config.read_text())
        self.assertEqual(install.plan(h.root,h.config),[])
        install.rollback(receipt,h.root,h.config)
        self.assertEqual(path.read_text(),REPORTED)
        self.assertEqual(h.config.read_text(),oldroot)

    def test_equals_tab_crlf_format_keeps_exact_command_identity(self):
        for body in (REPORTED.replace('gcode:', 'gcode ='),
                     REPORTED.replace('    ', '\t').replace('\n','\r\n')):
            with self.subTest(body=body[:80]):
                h=self.harness();h.config.write_text(h.config.read_text()+body)
                install.apply(h.root,h.config,install.plan(h.root,h.config))
                self.assertNotIn('[gcode_macro '+NAME+']',h.config.read_text())
                self.assertEqual(install.plan(h.root,h.config),[])

    def test_custom_body_or_options_preserved(self):
        for text in (REPORTED.replace('default(200)','default(201)'),
                     REPORTED+'    M118 Keep operator modification\n',
                     REPORTED.replace('gcode:', 'variable_owner: 1\ngcode:')):
            with self.subTest(custom=text[-90:]):
                h=self.harness();h.config.write_text(h.config.read_text()+text)
                install.apply(h.root,h.config,install.plan(h.root,h.config))
                self.assertIn(text,h.config.read_text())

    def test_neighbors_saved_state_and_fluidd_cleanup_preserved(self):
        h=self.harness()
        custom='[gcode_macro MY_DIAGNOSTIC]\ngcode:\n    M118 Keep me\n'
        saved='#*# <---------------------- SAVE_CONFIG ---------------------->\n#*# [bed_mesh m300_pads]\n#*# version = 1\n'
        h.config.write_text(h.config.read_text()+REPORTED+custom+saved)
        install.apply(h.root,h.config,install.plan(h.root,h.config))
        self.assertIn(custom,h.config.read_text())
        self.assertEqual(profile.split_saved(h.config.read_text())[1],saved)
        old={'categories':[], 'stored':[{'name':NAME,'categoryId':'0','visible':False},
                                       {'name':'MY_DIAGNOSTIC','categoryId':'0','visible':True}]}
        merged,_=merge_groups(old,['MY_DIAGNOSTIC'])
        self.assertNotIn(NAME,[m['name'] for m in merged['stored']])
        self.assertTrue(next(m for m in merged['stored'] if m['name']=='MY_DIAGNOSTIC')['visible'])

if __name__=='__main__':unittest.main()
