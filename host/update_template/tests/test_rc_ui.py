"""RC1 production UI parity and exact-value migration, with no printer I/O."""
import configparser
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import test_display
from test_macro_dispatch import templates, ENV
from test_settings_information import session
from test_native_menu import fixture
import test_install as install_tests
import install
import m300_profile as profile
from setup_fluidd import merge_groups, hidden_test
from payload.m300_release import VERSION, display_mcu_version

ROOT=Path(__file__).resolve().parents[1]
SETTINGS={
    'light_mode': ('ZORTRAX_LIGHT','MODE','WHITE'),
    'sound': ('ZORTRAX_BUZZER','STATE','DISABLED'),
    'sleep_mode': ('ZORTRAX_SLEEP_MODE','STATE','DISABLED'),
    'language': ('ZORTRAX_LANGUAGE',None,None),
    'sort_mode': ('ZORTRAX_MODELS_SORT','MODE','NAME'),
    'full_platform_preheat': ('ZORTRAX_FULL_PLATFORM_PREHEAT','STATE','ENABLED'),
    'oled_brightness': ('ZORTRAX_OLED_BRIGHTNESS','LEVEL','8'),
    'led_brightness': ('ZORTRAX_LED_BRIGHTNESS','LEVEL','12'),
}


def register(h,name):
    t=ENV.from_string(templates()[name])
    h.gcode.register_command(name,None)
    h.gcode.register_command(name,lambda cmd:h.gcode.run_script_from_command(
        t.render(params=cmd.get_command_parameters())))


class PublicSettingsTests(unittest.TestCase):
    def test_every_oled_setting_has_a_public_macro(self):
        from payload.m300_settings import SETTINGS as definitions
        self.assertEqual({k for k,_,_ in definitions},set(SETTINGS))
        self.assertTrue(all(name in templates() for name,_,_ in SETTINGS.values()))

    def test_bare_macros_open_same_oled_page_without_changing_preferences(self):
        with session() as h:
            before=h.nvm.ui_snapshot()
            for key,(name,param,value) in SETTINGS.items():
                register(h,name);h.run(name)
                self.assertEqual(h.menu.page,'setting_'+key)
                self.assertEqual(h.nvm.ui_snapshot(),before)

    def test_explicit_brightness_reaches_shared_persistent_owner(self):
        with session() as h:
            for key in ('oled_brightness','led_brightness'):
                name,_,_=SETTINGS[key];register(h,name)
                for level in (1,8,16):
                    h.run(name+' LEVEL='+str(level))
                    self.assertEqual(h.nvm.get_setting(key),level)
                    self.assertEqual(h.settings.brightness_levels()[key],level)
                    self.assertEqual(h.menu.page,'setting_'+key)

    def test_invalid_brightness_does_not_round_or_mutate(self):
        with session() as h:
            for name in ('ZORTRAX_OLED_BRIGHTNESS','ZORTRAX_LED_BRIGHTNESS'):
                register(h,name)
                for raw in ('0','17','-1','2.5','NaN','bad'):
                    before=h.nvm.ui_snapshot()
                    with self.subTest(name=name,value=raw),self.assertRaises(Exception):
                        h.run(name+' LEVEL='+raw)
                    self.assertEqual(h.nvm.ui_snapshot(),before)

    def test_parameters_are_discoverable_by_fluidd(self):
        for key,(name,param,value) in SETTINGS.items():
            if param:self.assertIn('params.'+param,templates()[name],name)

    def test_brightness_change_does_not_move_or_heat(self):
        with session() as h:
            initial=h.position[:];target=h.hotend.target
            for name in ('ZORTRAX_OLED_BRIGHTNESS','ZORTRAX_LED_BRIGHTNESS'):
                register(h,name);h.run(name+' LEVEL=4')
            self.assertEqual(h.position,initial);self.assertEqual(h.hotend.target,target)

    def test_root_has_no_lab_route_and_cached_navigation_redirects(self):
        menu,_=fixture();menu.page='main'
        self.assertEqual([r[0] for r in menu.rows(1)[1]],['Klipper','Zortrax M300'])
        menu._navigate('tests');self.assertEqual(menu.page,'main')
        menu.page='tests'
        self.assertFalse(any(a and 'TEST_' in str(a) for _,a in menu.rows(1)[1]))

    def test_maintenance_keeps_useful_fan_and_current_procedure_actions(self):
        menu,_=fixture();menu.page='maintenance';rows=menu.rows(1)[1]
        self.assertIn(('Fan test',('native_gcode','ZORTRAX_FAN_TEST_START')),rows)
        self.assertIn(('Current procedure',('native_gcode','ZORTRAX_PROCEDURE')),rows)
        self.assertFalse(hidden_test('ZORTRAX_FAN_TEST_START'))
        self.assertFalse(hidden_test('ZORTRAX_PROCEDURE'))
        menu.page='klipper'
        self.assertIn(('Diagnostics',('page','diagnostics')),menu.rows(1)[1])

    def test_public_firmware_label_is_clean_but_unknown_identity_not_faked(self):
        self.assertEqual(VERSION,'1.0.0-rc.1')
        self.assertEqual(display_mcu_version('0.13.14.19-TONED-OLED-UART8'),'0.13.14.19')
        self.assertEqual(display_mcu_version('foreign MCU'),'foreign MCU')
        self.assertEqual(display_mcu_version(None),'Unavailable')


class RcMigrationTests(unittest.TestCase):
    def setup_install(self):
        h=install_tests.InstallerTests(methodName='runTest');h.setUp();self.addCleanup(h.tearDown)
        return h

    def test_new_install_plan_never_adds_lab_cfg_or_macros(self):
        h=self.setup_install();changes=install.plan(h.root,h.config)
        self.assertNotIn('m300_tests.cfg',[p.name for p,_,_ in changes])
        cfg='\n'.join(data.decode() for p,_,data in changes if p.suffix=='.cfg')
        self.assertNotIn('[gcode_macro TEST_',cfg)
        self.assertIn('[gcode_macro ZORTRAX_OLED_BRIGHTNESS]',cfg)

    def test_stock_laboratory_macros_removed_backup_preserved_and_rollback_exact(self):
        h=self.setup_install();p=h.config.parent/'m300_tests.cfg'
        before=(ROOT/'legacy/m300_tests.cfg').read_text();p.write_text(before)
        h.config.write_text('[mcu]\nserial: /dev/ttyS1\n[include m300_tests.cfg]\n')
        oldroot=h.config.read_text()
        receipt=install.apply(h.root,h.config,install.plan(h.root,h.config))
        self.assertNotIn('[gcode_macro TEST_',p.read_text())
        self.assertNotIn('[include m300_tests.cfg]',h.config.read_text())
        self.assertEqual(install.plan(h.root,h.config),[])
        install.rollback(receipt,h.root,h.config)
        self.assertEqual(p.read_text(),before);self.assertEqual(h.config.read_text(),oldroot)

    def test_equals_style_stock_macro_is_removed_on_the_first_organized_pass(self):
        h=self.setup_install()
        text=('[mcu]\nserial: /dev/ttyS1\n[m300_mcu]\nnative_control: True\n'
    '[gcode_macro ZORTRAX_OLED_PERF]\ndescription = Reset OLED samples\n'
    'gcode = \n\tZORTRAX_OLED_PERF_RESET\n')
        h.config.write_text(text)
        receipt=install.apply(h.root,h.config,install.plan(h.root,h.config,organize_config=True))
        self.assertNotIn('[gcode_macro ZORTRAX_OLED_PERF]',h.config.read_text())
        self.assertEqual(install.plan(h.root,h.config,organize_config=True),[])
        install.rollback(receipt,h.root,h.config)
        self.assertEqual(h.config.read_text(),text)

    def test_custom_test_body_and_include_are_retained(self):
        h=self.setup_install();p=h.config.parent/'m300_tests.cfg'
        custom='[gcode_macro TEST_ZORTRAX_XY]\ngcode:\n    M118 Operator-owned diagnostic\n'
        p.write_text(custom);h.config.write_text('[mcu]\nserial: /dev/ttyS1\n[include m300_tests.cfg]\n')
        install.apply(h.root,h.config,install.plan(h.root,h.config))
        self.assertEqual(p.read_text(),custom)
        self.assertIn('[include m300_tests.cfg]',h.config.read_text())

    def test_retired_wrapper_with_extra_commands_is_not_removed(self):
        h=self.setup_install();text='[gcode_macro ZORTRAX_OLED_PERF]\ngcode:\n    ZORTRAX_OLED_PERF_RESET\n    M118 Keep me\n'
        h.config.write_text(h.config.read_text()+text)
        install.apply(h.root,h.config,install.plan(h.root,h.config))
        self.assertIn(text,h.config.read_text())

    def test_recognized_perf_and_old_print_wrappers_retired(self):
        h=self.setup_install();p=h.config.parent/'old.cfg'
        p.write_text('[gcode_macro ZORTRAX_OLED_PERF]\ngcode:\n    ZORTRAX_OLED_PERF_RESET\n')
        h.config.write_text('[mcu]\nserial: /dev/ttyS1\n[include old.cfg]\n')
        install.apply(h.root,h.config,install.plan(h.root,h.config))
        self.assertNotIn('[gcode_macro ZORTRAX_OLED_PERF]',p.read_text())

    def test_ui_cleanup_does_not_change_qualified_z_mesh_or_pid(self):
        from test_first_print_z import QualifiedConfigurationTests
        h=self.setup_install();cfg=QualifiedConfigurationTests.CONFIG.replace('position_min: 0','position_min: -0.5').replace('approach_distance: 6.0','approach_distance: 6.5').replace('z_contact_clearance: 5','z_contact_clearance: 2')
        h.config.write_text(cfg)
        install.apply(h.root,h.config,install.plan(h.root,h.config))
        text=h.config.read_text()
        for line in ('position_min: -0.5','approach_distance: 6.5','z_contact_clearance: 2','safe_z: 5','baud: 1500000','position_max: 305','purge_height: 0.28'):
            self.assertIn(line,text)
        self.assertEqual(profile.split_saved(cfg)[1],profile.split_saved(text)[1])

    def test_fluidd_clears_empty_test_category_and_hides_custom_lab_macro(self):
        old={'categories':[{'id':'t','name':'TEST M300'}], 'stored':[
            {'name':'ZORTRAX_PROCEDURE','categoryId':'t','visible':True},
            {'name':'TEST_ZORTRAX_XY','categoryId':'t','visible':True,'color':'red'},
            {'name':'ZORTRAX_OLED_PERF','categoryId':'t','visible':True}]}
        names=['ZORTRAX_PROCEDURE','TEST_ZORTRAX_XY','ZORTRAX_OLED_BRIGHTNESS']
        result,_=merge_groups(old,names)
        self.assertNotIn('TEST M300',[c['name'] for c in result['categories']])
        rows={m['name']:m for m in result['stored']}
        self.assertNotIn('ZORTRAX_OLED_PERF',rows)
        self.assertFalse(rows['TEST_ZORTRAX_XY']['visible'])
        self.assertEqual(rows['TEST_ZORTRAX_XY']['color'],'red')
        self.assertEqual(merge_groups(result,names)[0],result)
        self.assertTrue(old['stored'][1]['visible'])

    def test_category_with_unrelated_custom_macro_not_deleted(self):
        old={'categories':[{'id':'t','name':'TEST M300'}], 'stored':[{'name':'MY_MACRO','categoryId':'t','visible':True}]}
        result,_=merge_groups(old,['MY_MACRO'])
        self.assertEqual(result,old)

    def test_duplicate_lab_preferences_refused(self):
        with self.assertRaises(ValueError):
            merge_groups({'stored':[{'name':'TEST_ZORTRAX_XY'}, {'name':'test_zortrax_xy'}]},['TEST_ZORTRAX_XY'])

if __name__=='__main__':unittest.main()
