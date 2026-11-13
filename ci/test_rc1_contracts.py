"""RC1 publication, UI coverage and no-motion-change contracts. No printer I/O."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
VERSION='v1.0.0-rc.7'


class Rc1Contracts(unittest.TestCase):
    def test_release_identity_and_real_mcu_identity_are_separate(self):
        meta=json.loads((ROOT/'PORT.json').read_text())
        self.assertEqual(meta['distribution_version'],VERSION)
        self.assertEqual(meta['public_host_version'],VERSION[1:])
        self.assertEqual(meta['menu_revision'],VERSION[1:])
        self.assertEqual(meta['mcu_release'],'1.0.3')
        self.assertIn('m300_release.py',meta['host_update_files'])
        source=(ROOT/'host/klippy/extras/m300_settings.py').read_text()
        self.assertIn('display_mcu_version',source)
        self.assertIn('mcu_release=',source)  # genuine machine identity still returned
        labels=(ROOT/'host/klippy/extras/m300_ui_labels.py').read_text()
        self.assertIn("'Etap: P01 LAB': 'Host '+VERSION",labels)
        self.assertIn("'M10 OLED link': 'OLED link'",labels)
        self.assertIn("'LAB: hardware still unqualified': 'Hardware acceptance pending'",labels)
        self.assertNotIn("'Host UI: R7 Fans'",labels)

    def test_rc6_protected_motion_thermal_mesh_and_pixel_sources_unchanged(self):
        report=json.loads((ROOT/'docs/reports/RC6_REVIEW.json').read_text())
        self.assertFalse(report['physical_tests_performed'])
        self.assertGreaterEqual(len(report['protected_sha256']),14)
        controller = 'host/klippy/extras/m300_print_control.py'
        drain_observer = (
            "        nvm = self.printer.lookup_object('m300_nvm', None)\n"
            "        if nvm is not None:\n"
            "            nvm.runtime_drained(self.reactor.monotonic())\n"
        ).encode()
        end_observer = (
            "            models = self.printer.lookup_object('m300_models', None)\n"
            "            if models is not None:\n"
            "                models.runtime_end()\n"
        ).encode()
        for path, expected in report['protected_sha256'].items():
            with self.subTest(path=path):
                data = (ROOT/path).read_bytes()
                if path == controller:
                    for observer, count in ((drain_observer, 2), (end_observer, 1)):
                        self.assertEqual(data.count(observer), count)
                        data = data.replace(observer, b'')
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected)

    def test_regression_suite_not_replaced_with_ui_only_tests(self):
        meta=json.loads((ROOT/'PORT.json').read_text())
        self.assertEqual(meta['self_contained_host_tests'],896)
        check=(ROOT/'ci/run_checks.py').read_text()
        for name in ('native_heater_checks','real_installer_migration','qualified_first_print_migration',
                     'host_tests','native_klippy_process'):
            # Check actual test names, not an artificially reduced suite.
            if name=='qualified_first_print_migration':
                self.assertIn('qualified_first_print',check)
            elif name=='native_klippy_process':
                self.assertIn('validate_native_process.py',check)
            else:self.assertIn(name,check)
        legacy=(ROOT/'host/update_template/legacy/m300_tests.cfg').read_text()
        self.assertIn('TEST_ZORTRAX_XY',legacy)
        self.assertIn('legacy/m300_tests.cfg',(ROOT/'ci/validate_native_process.py').read_text())

    def test_production_macro_catalogue_has_no_laboratory_definitions(self):
        names=[]
        for path in (ROOT/'host/config').glob('*.cfg'):
            names += re.findall(r'^\[gcode_macro ([^\]]+)\]',path.read_text(),re.M)
        self.assertEqual(len(names),41)
        self.assertEqual(len(names),len(set(names)))
        self.assertFalse(any(n.startswith('TEST_') for n in names))
        for name in ('ZORTRAX_OLED_BRIGHTNESS','ZORTRAX_LED_BRIGHTNESS',
                     'ZORTRAX_PROCEDURE','ZORTRAX_DIAGNOSTICS'):
            self.assertIn(name,names)
        catalog=json.loads((ROOT/'docs/reports/MACRO_MANIFEST.json').read_text())
        self.assertEqual({x['name'] for x in catalog['macros']},set(names))
        for name in names:
            self.assertIn('`'+name+'`',(ROOT/'docs/pl/MACRO_REFERENCE.md').read_text())

    def test_all_settings_have_shared_dispatch_and_public_documentation(self):
        source=(ROOT/'host/config/m300_operations.cfg').read_text()
        settings={'light_mode':'ZORTRAX_LIGHT','buzzer':'ZORTRAX_BUZZER',
                  'sleep':'ZORTRAX_SLEEP_MODE','sort':'ZORTRAX_MODELS_SORT',
                  'language':'ZORTRAX_LANGUAGE','full_platform_preheat':'ZORTRAX_FULL_PLATFORM_PREHEAT',
                  'oled_brightness':'ZORTRAX_OLED_BRIGHTNESS','led_brightness':'ZORTRAX_LED_BRIGHTNESS'}
        blocks=dict(re.findall(r'\[gcode_macro ([^\]]+)\]\n(.*?)(?=\n\[|\Z)',source,re.S))
        for key,name in settings.items():
            self.assertIn('ZORTRAX_UI_SETTING NAME='+key,blocks[name])
            self.assertIn(name,(ROOT/'docs/pl/RC1_UI.md').read_text())
        for name in ('ZORTRAX_OLED_BRIGHTNESS','ZORTRAX_LED_BRIGHTNESS'):
            self.assertIn('params.LEVEL',blocks[name])
            self.assertNotIn('|int',blocks[name])

    def test_native_root_has_no_test_entry_and_preserves_fan_service(self):
        source=(ROOT/'host/klippy/extras/m300_menu.py').read_text()
        self.assertNotIn("('Service / Tests', ('page', 'tests'))",source)
        self.assertNotIn("if native and self.page == 'tests':",source)
        self.assertIn('ZORTRAX_FAN_TEST_START',source)
        self.assertIn("('native_gcode', 'ZORTRAX_PROCEDURE')",source)
        self.assertIn("('Diagnostics', ('page', 'diagnostics'))",source)

    def test_frontend_filters_stale_test_preferences_not_only_new_categories(self):
        source=(ROOT/'frontend/fluidd/rc/m300-macro-category.ts').read_text()
        self.assertIn('m300MacroHidden',source)
        self.assertIn('M300_CLASSIC',source)
        patch=(ROOT/'frontend/fluidd/m300-leveling.patch').read_text()
        self.assertIn('macro.visible = false',patch)
        self.assertIn('m300MacroHidden',patch)
        self.assertIn('frontend/fluidd/rc/', (ROOT/'ci/build_fluidd.sh').read_text())

    def test_package_names_and_installer_paths_agree(self):
        for path in ('ci/package_release.py','ci/package_git_deploy.py','ci/install_fresh.py',
                     'ci/install_orange_pi.py'):
            text=(ROOT/path).read_text()
            self.assertNotIn('M300_HOST_R16_12_NORMAL_UI',text,path)
            self.assertNotIn('M300_FLUIDD_1_37_7_R16_12.zip',text,path)
            self.assertIn('M300_HOST',text,path)
        for path in ('ci/package_release.py','ci/package_git_deploy.py'):
            self.assertIn('M300_SD.zip',(ROOT/path).read_text())
        for lang in ('pl','en'):
            text=(ROOT/'docs'/lang/('RELEASE_'+VERSION+'.md')).read_text()
            self.assertIn('--port 4480',text)
            self.assertIn('1.0.3',text)

    def test_obsolete_generators_and_duplicate_publish_workflow_removed(self):
        for path in ('tools/build_305105.py','tools/m300_thermal_config.py','tools/test_thermal_305105.py',
                     '.github/workflows/publish-m300-r16-12.yml','.github/workflows/thermal-305105.yml',
                     '.github/workflows/publish-beta.yml','ci/publish_beta_release.sh'):
            self.assertFalse((ROOT/path).exists(),path)
        self.assertTrue((ROOT/'host/klippy/extras/m300_temperature_policy.py').is_file())
        self.assertTrue((ROOT/'host/update_template/m300_thermal_config.py').is_file())

    def test_release_and_retry_watch_same_build_and_only_successful_publication(self):
        build=(ROOT/'.github/workflows/build-m300.yml').read_text()
        publish=(ROOT/'.github/workflows/publish-release.yml').read_text()
        retry=(ROOT/'.github/workflows/retry-transient.yml').read_text()
        self.assertTrue(build.startswith('name: M300 build and verification'))
        self.assertIn("['M300 build and verification']",publish)
        self.assertIn("'M300 build and verification', 'Publish M300 release'",retry)
        self.assertIn("conclusion == 'success'",publish)
        self.assertIn('needs: build',build)
        self.assertIn('name: M300_ORANGE_PI',build)
        self.assertIn('ci/publish_release.sh',publish)
        self.assertIn('publish-release.yml',(ROOT/'ci/retry_failed_workflow.py').read_text())
        self.assertNotIn('continue-on-error',build+publish)

    def test_release_tag_policy_accepts_rc_without_republishing_beta(self):
        script=(ROOT/'ci/publish_release.sh').read_text()
        self.assertIn('(beta|rc)',script)
        self.assertIn('leaving its tag and assets unchanged',script)
        self.assertIn('--prerelease',script)
        self.assertIn('.head_sha == $sha',script)
        self.assertIn('--name M300_ORANGE_PI',script)
        self.assertEqual(subprocess.run(['bash','-n',str(ROOT/'ci/publish_release.sh')]).returncode,0)

    def test_historical_images_and_hardware_scope_explicit(self):
        for name in ('OLED_FUNCTIONS.md','OLED_MENU_REFERENCE.md'):
            text=(ROOT/'docs/pl'/name).read_text()
            self.assertIn('RC1',text);self.assertIn('beta.20',text)
        text=(ROOT/'docs/pl/CODE_REVIEW_RC1.md').read_text()
        self.assertIn('794',text)
        self.assertTrue((ROOT/'docs/evidence/M300_FIRST_PRINT_USER_REPORT_2026-11-11.md').is_file())


if __name__=='__main__':unittest.main(verbosity=2)
