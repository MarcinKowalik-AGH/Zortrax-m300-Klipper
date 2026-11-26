# Marcin Kowalik <mkowalik@agh.edu.pl>
# test_rc1_contracts.py - Sprawdza zgodność publicznych makr, interfejsu i chronionych źródeł z wymaganiami wydania.
"""RC1 publication, UI coverage and no-motion-change contracts. No printer I/O."""
from historical_source import source_bytes
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
VERSION=json.loads((ROOT/'PORT.json').read_text())['distribution_version']


class Rc1Contracts(unittest.TestCase):
    def test_release_identity_and_real_mcu_identity_are_separate(self):
        meta=json.loads((ROOT/'PORT.json').read_text())
        self.assertEqual(meta['distribution_version'],VERSION)
        self.assertEqual(meta['public_host_version'],VERSION[1:])
        self.assertEqual(meta['menu_revision'],VERSION[1:])
        self.assertEqual(meta['mcu_release'],'1.0.9')
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
        oled = 'host/klippy/extras/m300_oled.py'
        native_service = 'host/klippy/extras/m300_native_service.py'
        # Reviewed startup, print lighting, pause/end and 1.0.0 preflight updates.
        updated_runtime = {
            # One exact optional internal ADC owner; external wiring guards remain intact.
            'host/klippy/extras/m300_resources.py': (
                '1ee2d29895bd3f1cc104baa0733cf6b6fdb60e0cca81806d527b189491024180',
                '6c8fab36e0e1255f790ab580b9a46453aefec943b13f57f4ac52d3a2f07389bd'),
            # RC34 updates the macro keys used to select the same OLED artwork.
            'host/klippy/extras/m300_oem_graphics.py': (
                'a86e6483e2f96e82f91183f3a1f4e8e6a14bd7438466b9c831f5cebe074e45d1',
                'a362428135beaa70d7366902fba0da52c9d631531b26336b1229868c4b446028'),
            # RC31 exposes direction-specific material settings in the menu and profile.
            'host/config/m300_classic_services.cfg': (
                'f199715dd59536b5c701e145a0c5c2b1adf6ef4936f9f05a2454e7eee26461f4',
                '541a4b8434cfa784ab07172d630f93ad18b57d147b6adf75c9ca4dabbe867505'),
            'host/klippy/extras/m300_menu.py': (
                '36d87ea55349a74610d1dd978cb1eb69f5420bcf0a6dbd09d0b6c0a370b11320',
                'f8b550fc3064404efba210b2fdb86a3a3bdae9eaa40fae3d2a41ac980540e743'),
            'host/klippy/extras/m300_calibration.py': (
                '922ec1342dd30c5e7dd6284001dfcaf3d203fb1f618e1ab1e25418e27e7b9fcf',
                '7a7c6557c2b8b4861fdc693eaab8d878e7443ab5e58d95e804a38b33a498b735'),
            # Optional temperature includes are comments; hardware values are unchanged.
            'host/config/m300_classic_base.cfg': (
                '1e073f111a228e0c8bb1521382004c69633d670ad7df9ea2a3960f100080b57a',
                '92f573e8dc418851544f8bc66f6a9638afe960c6c893c4e371168737c2a8eddf'),
            'host/klippy/extras/m300_settings_ui.py': (
                '27985dd4e51f7a688e060ad37adb278dd26ca50c085ca18f3487bcd484c21bcb',
                'cad2ac3c9fea594a5e8701f35936681857ec0f6e341697768940cba6a8d3dafd'),
            'host/klippy/extras/m300_print_control.py': (
                'd8ac4c4aaea27dd233b8b96648f5765b048c5ce799f50ed0b7376b5dbd7ac933',
                'e35f0fe91c187a9c220a98ec81fe0b17b83927377cd3dd4d7d5d4771748fd3ba'),
            # R16.16 also resolves the preceding contact notice after verified Z homing.
            'host/klippy/extras/m300_native_motion.py': (
                '8c524623956d66ef407b2d89d7ddba033f04d761bd42861cc18aa6914c17f72e',
                'c31cfb46deab896ed74315202a94735caef0f98f23e44d8f422e58611bb6c9cc'),
            'host/klippy/extras/m300_pad_mesh.py': (
                'd7b5c68bf490d8dc2f8c53c9b45e3ae45c2420a9446d94acf9ad771e8304c836',
                '7855182de6cfce67a462b9145e7ba299d3ed1106513221c9ac12df0755c11816'),
        }
        for path, expected in report['protected_sha256'].items():
            with self.subTest(path=path):
                data = source_bytes(ROOT/path)
                if path in updated_runtime:
                    historical, current = updated_runtime[path]
                    self.assertEqual(expected, historical)
                    expected = current
                if path == oled:
                    # RC9 removes the development RLE command. The repository
                    # AST contract separately checks the production OLED methods.
                    # RC23 also preserves the invoking menu row after Back.
                    self.assertEqual(expected, 'e4575a52869ad6cf2937da8ba19f9a09c83338e0bff4326900c0c84a03c0bb9a')
                    expected = 'a77e63b610b5bf73955959ff94d4caf1796103e3038230acb4e807aaf2aee666'
                if path == native_service:
                    # RC13 allows active native Bed Mesh for E-only filament moves.
                    # Preserve the RC6 reference and pin the reviewed RC13 code.
                    self.assertEqual(expected, '40f12fab2334dfef5e99cdfe1dffc09c4392c143b4bf3454867144237c908b15')
                    expected = '5910e3bf4a9a990419e7244c2832d59b2598738887d561d144721dc40fc4117a'
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected)

    def test_regression_suite_not_replaced_with_ui_only_tests(self):
        meta=json.loads((ROOT/'PORT.json').read_text())
        self.assertEqual(meta['self_contained_host_tests'],1038)
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
        self.assertEqual(len(names),44)
        self.assertEqual(len(names),len(set(names)))
        self.assertFalse(any(n.startswith('TEST_') for n in names))
        for name in ('M300_OLED_BRIGHTNESS','M300_LED_BRIGHTNESS',
                     'M300_PROCEDURE','M300_DIAGNOSTICS'):
            self.assertIn(name,names)
        catalog=json.loads((ROOT/'docs/reports/MACRO_MANIFEST.json').read_text())
        self.assertEqual({x['name'] for x in catalog['macros']},set(names))
        for name in names:
            self.assertIn('`'+name+'`',(ROOT/'docs/pl/MACRO_REFERENCE.md').read_text())

    def test_all_settings_have_shared_dispatch_and_public_documentation(self):
        source=(ROOT/'host/config/m300_operations.cfg').read_text()
        settings={'light_mode':'M300_LIGHT','buzzer':'M300_BUZZER',
                  'sleep':'M300_SLEEP_MODE','sort':'M300_MODELS_SORT',
                  'language':'M300_LANGUAGE','full_platform_preheat':'M300_FULL_PLATFORM_PREHEAT',
                  'oled_brightness':'M300_OLED_BRIGHTNESS','led_brightness':'M300_LED_BRIGHTNESS'}
        blocks=dict(re.findall(r'\[gcode_macro ([^\]]+)\]\n(.*?)(?=\n\[|\Z)',source,re.S))
        for key,name in settings.items():
            self.assertIn('ZORTRAX_UI_SETTING NAME='+key,blocks[name])
            self.assertIn(name,(ROOT/'docs/pl/RC1_UI.md').read_text())
        for name in ('M300_OLED_BRIGHTNESS','M300_LED_BRIGHTNESS'):
            self.assertIn('params.LEVEL',blocks[name])
            self.assertNotIn('|int',blocks[name])

    def test_native_root_has_no_test_entry_and_preserves_fan_service(self):
        source=(ROOT/'host/klippy/extras/m300_menu.py').read_text()
        self.assertNotIn("('Service / Tests', ('page', 'tests'))",source)
        self.assertNotIn("if native and self.page == 'tests':",source)
        self.assertIn('M300_FAN_TEST_START',source)
        self.assertIn("('native_gcode', 'M300_PROCEDURE')",source)
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
            self.assertIn('1.0.8',text)

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
        self.assertIn('name: M300 build and verification', build.splitlines())
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
