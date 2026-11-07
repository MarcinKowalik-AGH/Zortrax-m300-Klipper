"""Full Settings/Information sessions, durable settings and real browser paths."""
import copy
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_display
from test_native_maintenance_contract import FanHarness
from test_native_oem_services import physical_panel
from test_macro_dispatch import templates, ENV
from payload.m300_oem_graphics import OEMGraphics, STOCK_SHA256, choose_icon
from payload.m300_leveling_oem import width
from payload.m300_nvm import M300NVM, HostNVM
from payload.m300_settings import M300Settings, PAGES, PROJECT_URL, history_totals
from payload.m300_browser import M300Browser
from payload.m300_browser_state import Catalog, BrowserError
from payload.m300_menu import sort_entries
from payload.m300_display import M300Display
from payload.m300_settings_ui import SPRITE_LABEL_PIXELS, brightness_frame, menu_frame
from payload.m300_ui_m11_state import fit_label, require_rows


@contextmanager
def session(serial=None):
    with tempfile.TemporaryDirectory() as tmp:
        h=FanHarness();h.tmp=Path(tmp);h.files=h.tmp/'gcodes';h.files.mkdir()
        options=dict(path=str(h.tmp/'settings.json'),machine_id='HOST-IDENTITY-NOT-SERIAL',
                     mechanics_id='TEST',serial_number=serial)
        h.config.get=lambda name,default=None:options.get(name,default)
        h.config.getint=lambda name,default,**kw:default
        h.config.has_section=lambda name:True
        h.allocations=[]
        def allocate(name):
            h.allocations.append(name)
            return NS(submit=lambda fn,*a,**k:fn(*a,**k))
        h.objects['aio_executor']=NS(allocate_executor=allocate)
        h.nvm=M300NVM(h.config);h.objects['m300_nvm']=h.nvm
        h.settings=M300Settings(h.config);h.objects['m300_settings']=h.settings;h.settings._ready()
        mcu=h.board.get_mcu();mcu.get_status=lambda now:dict(mcu_version='0.13.14.5-FACTORY-Z-UART8')
        h.board.get_mcu=lambda:mcu
        h.board.hardware=NS(get_status=lambda:dict(hardware_label='HW05',effective_z_steps_per_mm=400))
        h.pins={}
        for key in ('m300_led_r','m300_led_g','m300_led_b','m300_buzzer'):
            h.objects['output_pin '+key]=NS(gcrq=NS(send_async_request=lambda value,key=key:h.pins.__setitem__(key,value)))
        o,menu,ui,display,packet=physical_panel(h);menu.nvm=h.nvm;menu._last_file=None
        h.oled,h.menu,h.ui=o,menu,ui
        h.panel_display = display
        for name,body in templates().items():
            if name in ('ZORTRAX_SETTINGS','ZORTRAX_BUZZER','ZORTRAX_SLEEP_MODE','ZORTRAX_LANGUAGE',
                        'ZORTRAX_MODELS_SORT','ZORTRAX_INFORMATION','ZORTRAX_HELP','ZORTRAX_LIGHT'):
                template=ENV.from_string(body)
                h.gcode.register_command(name,lambda cmd,t=template:h.gcode.run_script_from_command(
                    t.render(params=cmd.get_command_parameters())))
        yield h


def attach_display(h):
    p=test_display.Printer();p.objects['m300_nvm']=h.nvm
    p.objects['print_stats']=NS(get_status=lambda now:dict(state=h.print_state))
    d=M300Display(test_display.Config(p));d._ready();h.objects['m300_display']=d
    h.handlers['m300:setting_changed'].append(d._setting_changed)
    return p,d


def browser(h):
    def select(path):
        p=h.files/path
        h.job.sd.selected=NS(filename=path,identity='checked:'+path,sha256='a'*64,size=p.stat().st_size,
            targets=dict(hotend=0.,bed=0.),closed=False)
        return h.job.sd.selected
    def cancel():
        if h.job.sd.selected:h.job.sd.selected.closed=True
        h.job.sd.selected=None
    h.job.sd.root=str(h.files);h.job.sd.v_sd=NS(executor=NS(submit=lambda f,*a,**k:f(*a,**k)))
    h.job.sd.selected=None;h.job.sd.select=select;h.job.sd.cancel=cancel
    b=M300Browser(h.config);h.objects['m300_browser']=b;b._ready();return b


class SettingsTreeTests(unittest.TestCase):
    def test_oled_menus_share_oem_font_and_keep_the_back_marker_visible(self):
        with session() as h:
            frame_type = test_display.renderer.Frame
            for page in ('main', 'zortrax', 'maintenance', 'material', 'settings'):
                with self.subTest(page=page):
                    h.menu.page = page
                    _, rows = h.oled._rows(h.now)
                    labels = tuple(label for label, _ in rows)
                    sprite = h.ui.get_oem_sprite('m04', rows, 0, h.now)
                    h.oled.selection = 0
                    h.oled._render(h.now)
                    wire = h.oled._render_wire
                    self.assertEqual(wire, menu_frame(labels, (), 0, frame_type, sprite))
                    self.assertEqual(wire[7*128+2] & 15, 15)  # Back tip, x=5.
                    self.assertEqual(wire[7*128+5] & 15, 0)   # x=11 is dark.
                    h.oled.selection = len(labels)-1
                    h.oled._render(h.now)
                    for row in range(12):
                        start = row*128+8
                        self.assertEqual(h.oled._render_wire[start:start+22],
                                         wire[start:start+22])
            label = 'WWWWWWWWWWWWWWWWWWWWWWWWWW.gcode'
            for offset in (0, 10, 25):
                self.assertLessEqual(width(fit_label(label, SPRITE_LABEL_PIXELS, offset)),
                                     SPRITE_LABEL_PIXELS)
            self.assertNotEqual(fit_label(label, SPRITE_LABEL_PIXELS),
                                fit_label(label, SPRITE_LABEL_PIXELS, 25))

    def test_exact_requested_tree_and_english_only_language(self):
        with session() as h:
            expected={'settings':['Back','Light','Buzzer','Sleep mode','Language','Models sorting',
                                  'OLED brightness','LED brightness'],
                'setting_light_mode':['Back','Dynamic','White','Disabled'],
                'setting_sound':['Back','Enabled','Disabled'],
                'setting_sleep_mode':['Back','Enabled','Disabled'],
                'setting_language':['Back','English'],
                'setting_sort_mode':['Back','Date','Name','Case-sensitive name','File size'],
                'setting_oled_brightness':['Back'] + list(map(str, range(1, 17))),
                'setting_led_brightness':['Back'] + list(map(str, range(1, 17))),
                'information':['Back','Firmware version','Printer information','Help']}
            for page,labels in expected.items():
                h.menu.page=page;title,rows=h.menu.rows(h.now)
                self.assertEqual([r[0] for r in rows],labels);self.assertTrue(require_rows(rows))
                self.assertEqual(len(menu_frame(tuple(labels),h.settings.active_rows(page),0,test_display.renderer.Frame)),8192)

    def test_all_information_and_settings_pages_render_without_actuation(self):
        with session() as h:
            before=h.position[:];target=h.hotend.target
            for page in sorted(PAGES):
                h.menu.page=page
                title,rows=h.menu.rows(h.now);self.assertTrue(require_rows(rows))
                for index in range(len(rows)):
                    h.oled.selection=index;h.oled._render(h.now)
                    self.assertEqual(len(h.oled._render_wire),8192)
            self.assertEqual(h.position,before);self.assertEqual(h.hotend.target,target)
            self.assertNotIn('m300-information',h.allocations)

    def test_oled_routes_keep_setting_cursor_and_navigate_every_information_page(self):
        with session() as h:
            visited = set()

            def press(label):
                _, rows = h.menu.rows(h.now)
                index = [row[0] for row in rows].index(label)
                h.oled.selection = index
                h.oled._render(h.now)
                h.oled._select(h.now, tuple(action for _, action in rows))
                self.assertFalse(h.menu.reason)
                self.assertIsNone(h.oled.message)
                if rows[index][1][0] == 'set':
                    self.assertEqual(h.oled.selection, index)
                    self.assertIn(index, h.settings.active_rows(h.menu.page))
                visited.add(h.menu.page)

            h.menu.page = 'zortrax'
            press('Settings')
            for page, choices in (
                    ('Light', ('White', 'Disabled', 'Dynamic')),
                    ('Buzzer', ('Disabled', 'Enabled')),
                    ('Sleep mode', ('Disabled', 'Enabled')),
                    ('Language', ('English',)),
                    ('Models sorting', ('Date', 'Case-sensitive name', 'File size', 'Name')),
                    ('OLED brightness', ('1', '16')),
                    ('LED brightness', ('8', '16'))):
                press(page)
                for choice in choices:
                    press(choice)
                press('Back')
            press('Back')
            press('Information')
            press('Firmware version')
            press('Back')
            press('Printer information')
            self.assertEqual([action for _, action in h.menu.rows(h.now)[1]],
                             [('page', 'information'), None, None, None, None])
            press('Back')
            press('Help')
            press('Back')
            press('Back')
            # Error catalogue navigation is exercised with its real service
            # in test_oem_errors; this older fixture has no MCU error owner.
            self.assertEqual(visited, (set(PAGES) - {'errors', 'error_catalog'}) | {'zortrax'})
            self.assertEqual(h.menu.page, 'zortrax')
            self.assertEqual(h.hotend.target, 0.)

    def test_saved_settings_survive_restart_and_leave_identity_counters_and_observation_untouched(self):
        with session() as h:
            before=h.nvm.snapshot()
            for key,value in (('light_mode','WHITE'),('sound',False),('sleep_mode','OFF'),('sort_mode','NAME_CASE')):
                h.settings.set_option(key,value)
            store=HostNVM(str(h.tmp/'settings.json'),'HOST-IDENTITY-NOT-SERIAL','TEST')
            for key,value in (('light_mode','WHITE'),('sound',False),('sleep_mode','OFF'),('sort_mode','NAME_CASE')):
                self.assertEqual(store.snapshot()['settings'][key],value)
            for key in ('identity','counters','calibration'):self.assertEqual(store.snapshot()[key],before[key])

    def test_noop_choice_does_not_write_or_reset_sleep_profile(self):
        with session() as h:
            h.nvm.store.update(lambda data:data['settings'].__setitem__('sleep_mode','30MIN'))
            with patch.object(h.nvm.store,'update',side_effect=AssertionError('unexpected storage write')):
                h.settings.set_option('light_mode','DYNAMIC');h.settings.set_option('sleep_mode','15MIN')
            self.assertEqual(h.nvm.get_setting('sleep_mode'),'30MIN')

    def test_failed_storage_does_not_publish_setting_event_or_change_runtime(self):
        with session() as h:
            p,d=attach_display(h)
            with patch.object(h.nvm.store,'update',side_effect=OSError('disk write failed')):
                with self.assertRaisesRegex(h.printer.command_error,'disk write failed'):
                    h.settings.set_option('sleep_mode','OFF')
            self.assertTrue(d.sleep_enabled);self.assertEqual(h.nvm.get_setting('sleep_mode'),'15MIN')

    def test_cli_macro_bindings_reach_same_settings(self):
        with session() as h:
            for cmd,key,value in (('ZORTRAX_LIGHT MODE=DISABLED','light_mode','DISABLE'),
                    ('ZORTRAX_BUZZER STATE=DISABLED','sound',False),
                    ('ZORTRAX_SLEEP_MODE STATE=DISABLED','sleep_mode','OFF'),
                    ('ZORTRAX_MODELS_SORT MODE=NAME_CASE','sort_mode','NAME_CASE'),
                    ('ZORTRAX_LANGUAGE','language','EN')):
                h.run(cmd);self.assertEqual(h.nvm.get_setting(key),value)
                self.assertEqual((h.oled.page, h.menu.page), ('m04', 'setting_' + key))

    def test_closed_choice_macros_open_buttons_without_editing_the_current_choice(self):
        cases = (
            ('ZORTRAX_LIGHT', ['Dynamic', 'White', 'Disabled']),
            ('ZORTRAX_BUZZER', ['Enabled', 'Disabled']),
            ('ZORTRAX_SLEEP_MODE', ['Enabled', 'Disabled']),
            ('ZORTRAX_LANGUAGE', ['English']),
            ('ZORTRAX_MODELS_SORT', ['Date', 'Name', 'Case-sensitive name', 'File size']),
        )
        with session() as h:
            original = h.nvm.ui_snapshot()
            for macro, choices in cases:
                self.assertNotRegex(templates()[macro], r'params\.\w+')
                h.lines.clear()
                h.run(macro)
                labels = [line.split('prompt_button ', 1)[1].split('|', 1)[0].removesuffix(' <')
                          for line in h.lines if 'action:prompt_button ' in line]
                self.assertEqual(labels, ['Back'] + choices)
                self.assertEqual(h.nvm.ui_snapshot(), original)
            h.run('ZORTRAX_LIGHT')
            button = next(line.split('|')[1] for line in h.lines
                          if 'action:prompt_button White|' in line)
            h.run(button)
            self.assertEqual(h.nvm.get_setting('light_mode'), 'WHITE')

    def test_stale_or_duplicate_fluidd_buttons_cannot_repeat_a_write(self):
        with session() as h:
            h.settings.show('setting_light_mode');token=h.settings._view_id()
            h.settings.action(token,2);self.assertEqual(h.nvm.get_setting('light_mode'),'WHITE')
            revision=h.nvm.store._published['revision']
            with self.assertRaisesRegex(h.printer.command_error,'Expired'):
                h.settings.action(token,1)
            self.assertEqual(h.nvm.store._published['revision'],revision)

    def test_fluidd_and_oled_use_same_choice_text_and_checked_state(self):
        with session() as h:
            h.settings.set_option('light_mode','WHITE')
            for page in ('setting_light_mode', 'setting_sound', 'setting_sleep_mode',
                         'setting_language', 'setting_sort_mode', 'setting_oled_brightness',
                         'setting_led_brightness'):
                h.settings.show(page);title,rows=h.settings.rows(page,h.now)
                active=h.settings.active_rows(page)
                for index,(label,action) in enumerate(rows):
                    rendered=label+(' <' if index in active else '')
                    self.assertTrue(any('prompt_button '+rendered+'|' in line for line in h.lines))

    def test_cosmetic_settings_apply_during_procedure_and_save_afterwards(self):
        with session() as h:
            h.run('ZORTRAX_LOAD')
            before = h.nvm.store._published['revision']
            h.settings.set_option('led_brightness', 8)
            h.settings.set_option('light_mode', 'WHITE')
            self.assertEqual(h.pins['m300_led_r'], .5)
            self.assertEqual(h.nvm.store._published['revision'], before)
            with self.assertRaisesRegex(h.printer.command_error, 'blocked by'):
                h.settings.set_option('sort_mode', 'SIZE')
            h.p._tick(h.now)
            self.assertFalse(any('M300_BRIGHTNESS' in line for line in h.lines))
            context = h.oled._input_context()
            h.lines.clear()
            h.settings.show('settings')
            self.assertFalse(any('prompt_begin' in line for line in h.lines))
            self.assertEqual(h.oled._input_context(), context)
            self.assertEqual(h.hotend.target, 240.)
            h.f.cancel('test')
            h.until(h.f, 'CANCELLED')
            h.nvm._save_deferred_settings(h.now)
            self.assertEqual(h.nvm.store._published['settings']['led_brightness'], 8)
            h.lines.clear()
            h.settings.show('setting_led_brightness')
            self.assertIn('// action:prompt_text M300_BRIGHTNESS led_brightness 8', h.lines)

    def test_web_settings_bypass_busy_gcode_for_one_cosmetic_command_only(self):
        with session() as h, h.gcode.get_mutex():
            h.objects['m300_motion'] = NS(get_status=lambda now: dict(state='HOMING', busy=True))
            self.assertTrue(h.settings.try_web_script('ZORTRAX_SETTINGS'))
            command = 'ZORTRAX_UI_SETTING NAME=led_brightness VALUE=7'
            self.assertTrue(h.settings.try_web_script(command))
            self.assertEqual(h.nvm.get_setting('led_brightness'), 7)
            self.assertFalse(h.settings.try_web_script(command + '\nG28'))
            self.assertFalse(h.settings.try_web_script('ZORTRAX_UI_SETTING NAME=sleep_mode VALUE=DISABLED'))
            self.assertFalse(h.settings.try_web_script('G1 Z10'))

    def test_brightness_oled_uses_a_sixteen_segment_bar(self):
        with session() as h:
            h.menu.page = 'setting_led_brightness'
            h.oled.selection = 8
            h.oled._render(h.now)
            frame = h.oled._render_wire
            sprite=h.ui.oem_sprites.get('activity:led_brightness')
            self.assertEqual(frame, brightness_frame('LED brightness', 8, False, test_display.renderer.Frame,sprite))
            for segment in range(16):
                x = 16 + 10 * segment + 4
                self.assertEqual(frame[57 * 128 + x // 2] & 15, 15 if segment < 8 else 0)

    def test_fluidd_slider_save_keeps_back_valid_and_updates_the_open_oled_cursor(self):
        for key in ('oled_brightness', 'led_brightness'):
            with self.subTest(key=key), session() as h:
                h.settings.show('setting_' + key)
                token = h.settings._view_id()
                h.run('ZORTRAX_UI_SETTING NAME=%s VALUE=7' % key)
                self.assertEqual(h.oled.selection, 7)
                self.assertEqual(h.settings.brightness_levels()[key], 7)
                self.assertEqual(h.settings._view_id(), token)
                self.assertEqual(h.nvm.get_setting(key), 7)
                h.settings.action(token, 0)
                self.assertEqual((h.settings.page, h.menu.page), ('settings', 'settings'))
                with self.assertRaisesRegex(h.printer.command_error, 'Expired'):
                    h.settings.action(token, 0)

    def test_oled_draft_is_published_without_storage_uart_or_prompt_operations(self):
        with session() as h:
            h.settings.show('setting_led_brightness')
            h.oled.selection = 6
            revision = h.nvm.ui_snapshot()['revision']
            lines, events = list(h.lines), list(h.events)
            for _ in range(10):
                status = h.settings.get_status(h.now)
                self.assertEqual(status['brightness']['led_brightness'], 6)
                self.assertEqual(status['settings']['led_brightness'], 16)
                self.assertEqual(status['brightness']['oled_brightness'], 16)
            self.assertEqual(h.nvm.ui_snapshot()['revision'], revision)
            self.assertEqual((h.lines, h.events), (lines, events))
            h.menu._navigate('settings')
            self.assertEqual(h.settings.brightness_levels()['led_brightness'], 16)

    def test_remote_save_invalidates_old_oled_draft_receipts_and_can_save_its_current_preview(self):
        with session() as h:
            h.settings.show('setting_oled_brightness')
            h.oled.selection = 11
            h.oled._render(h.now)
            context = h.oled._input_context()
            h.run('ZORTRAX_UI_SETTING NAME=oled_brightness VALUE=4')
            self.assertNotEqual(h.oled._input_context(), context)
            self.assertIsNone(h.oled._presented_actions)
            self.assertEqual((h.oled.selection, h.settings.brightness_levels()['oled_brightness']), (4, 4))
            h.oled.selection = 9
            h.oled._render(h.now)
            h.oled._select(h.now, h.oled._presented_actions)
            self.assertIsNone(h.oled.message)
            self.assertEqual(h.nvm.get_setting('oled_brightness'), 9)
            self.assertEqual(h.settings.brightness_levels()['oled_brightness'], 9)

    def test_encoder_rotation_then_acknowledged_click_saves_the_synchronized_preview(self):
        with session() as h:
            h.settings.show('setting_led_brightness')
            h.oled.menu_reverse = True
            def packet(sequence, nav, shorts=0):
                h.now += .1
                before = len(h.callbacks)
                h.oled._panel(dict(sequence=sequence, position=nav*4, nav_position=nav*4,
                    invalid=0, pressed=False, presses=shorts, releases=shorts, shorts=shorts,
                    longs=0, **{'#receive_time':h.now}))
                h.callbacks.pop(before)(h.now)
            h.oled._render(h.now);h.panel_display.pump()
            packet(1, 0)
            packet(2, 3)
            self.assertEqual(h.oled.selection, 13)
            self.assertEqual(h.settings.get_status(h.now)['brightness']['led_brightness'], 13)
            self.assertEqual(h.nvm.get_setting('led_brightness'), 16)
            h.oled._render(h.now);h.panel_display.pump()
            packet(3, 3, shorts=1)
            self.assertIsNone(h.oled.message)
            self.assertEqual(h.nvm.get_setting('led_brightness'), 13)
            self.assertEqual(h.oled.selection, 13)

    def test_cosmetic_deferred_save_and_noop_save_keep_web_navigation_and_remote_value(self):
        with session() as h:
            h.settings.show('setting_led_brightness')
            token = h.settings._view_id()
            h.run('ZORTRAX_LOAD')
            h.menu._navigate('setting_led_brightness')
            h.oled.selection = 12
            h.run('ZORTRAX_UI_SETTING NAME=led_brightness VALUE=5')
            self.assertEqual(h.oled.selection, 5)
            self.assertEqual(h.settings._view_id(), token)
            self.assertEqual(h.nvm.get_setting('led_brightness'), 5)
            self.assertEqual(h.nvm.store._published['settings'].get('led_brightness',16), 16)
            h.oled.selection = 9
            h.run('ZORTRAX_UI_SETTING NAME=led_brightness VALUE=5')
            self.assertEqual(h.oled.selection, 5)
            h.f.cancel('test');h.until(h.f, 'CANCELLED')
            h.nvm._save_deferred_settings(h.now)
            h.run('ZORTRAX_UI_SETTING NAME=led_brightness VALUE=5')
            self.assertEqual(h.oled.selection, 5)
            self.assertEqual(h.nvm.store._published['settings']['led_brightness'], 5)

    def test_non_english_languages_and_old_interval_choices_are_not_ui_actions(self):
        with session() as h:
            for key,value in (('language','PL'),('language','DE'),('sleep_mode','60MIN')):
                with self.assertRaises(h.printer.command_error):h.settings.set_option(key,value)
            self.assertEqual(h.nvm.get_setting('language'),'EN')

    def test_existing_calibration_instruction_is_not_dropped_by_menu_adapter(self):
        with session() as h:
            h.menu.page='procedure'
            h.objects['m300_procedures']=NS(rows=lambda now:('Calibration',[('Tighten all three knobs',None),('Continue',('procedure_action','view','CONFIRM'))]))
            self.assertEqual(h.menu.rows(h.now)[1][0][0],'Tighten all three knobs')


class IndicatorAndSleepTests(unittest.TestCase):
    def test_light_modes_use_existing_outputs_and_dynamic_native_print_state(self):
        with session() as h:
            h.run('ZORTRAX_LIGHT MODE=WHITE')
            self.assertEqual([h.pins['m300_led_'+c] for c in 'rgb'],[1.,1.,1.])
            h.run('ZORTRAX_LIGHT MODE=DISABLED')
            self.assertEqual([h.pins['m300_led_'+c] for c in 'rgb'],[0.,0.,0.])
            h.run('ZORTRAX_LIGHT MODE=DYNAMIC')
            h.print_state='printing';h.m._indicators(h.now)
            self.assertEqual([h.pins['m300_led_'+c] for c in 'rgb'],[1.,1.,1.])
            h.print_state='paused';h.m._indicators(h.now)
            self.assertEqual([h.pins['m300_led_'+c] for c in 'rgb'],[1.,0.,1.])
            h.print_state='error';h.m._indicators(h.now)
            self.assertEqual([h.pins['m300_led_'+c] for c in 'rgb'],[1.,0.,0.])

    def test_independent_brightness_choices_apply_and_persist(self):
        with session() as h:
            _, display = attach_display(h)
            self.assertEqual(h.nvm.get_setting('oled_brightness'), 16)
            self.assertEqual(h.nvm.get_setting('led_brightness'), 16)
            h.settings.set_option('oled_brightness', 4)
            h.settings.set_option('led_brightness', 8)
            h.settings.set_option('light_mode', 'WHITE')
            self.assertEqual(display.stream._local['normal'], 40)
            self.assertEqual(display.stream._local['dim'], 8)
            self.assertEqual([h.pins['m300_led_'+c] for c in 'rgb'], [.5, .5, .5])
            store = HostNVM(str(h.tmp/'settings.json'), 'HOST-IDENTITY-NOT-SERIAL', 'TEST')
            settings = store.snapshot()['settings']
            self.assertEqual((settings['oled_brightness'], settings['led_brightness']), (4, 8))
            self.assertEqual(h.settings.active_rows('setting_led_brightness'), (8,))

    def test_buzzer_disable_stops_active_pulse_and_suppresses_future_clicks(self):
        with session() as h:
            h.m.click();self.assertEqual(h.pins['m300_buzzer'],1.)
            h.run('ZORTRAX_BUZZER STATE=DISABLED')
            self.assertEqual(h.pins['m300_buzzer'],0.);self.assertEqual(h.m._beep_until,0.)
            h.m.click();self.assertEqual(h.pins['m300_buzzer'],0.)
            h.run('ZORTRAX_BUZZER STATE=ENABLED');h.m.click()
            self.assertEqual(h.pins['m300_buzzer'],1.)

    def test_sleep_disable_uses_existing_wake_path_and_preserves_timeout_contrast_and_notice(self):
        with session() as h:
            p,d=attach_display(h);saved=(d.timeout,d.normal,d.dim,d.notice_seconds)
            p.reactor.now=301.;d._tick(301.);self.assertEqual(d.phase,'ENTERING_SLEEP')
            h.run('ZORTRAX_SLEEP_MODE STATE=DISABLED')
            self.assertEqual(d.phase,test_display.AWAKE);self.assertTrue(d._presentation_wait)
            p.reactor.now=10000.;d._tick(10000.)
            self.assertEqual(d.phase,test_display.AWAKE);self.assertEqual(saved,(d.timeout,d.normal,d.dim,d.notice_seconds))
            self.assertEqual(h.position,[150.,158.,5.,17.]);self.assertEqual(h.hotend.target,0.)

    def test_disabled_sleep_is_restored_on_start_and_enabled_reuses_same_timer(self):
        with session() as h:
            h.run('ZORTRAX_SLEEP_MODE STATE=DISABLED');p,d=attach_display(h)
            self.assertFalse(d.sleep_enabled);p.reactor.now=1000.;d._tick(1000.)
            self.assertEqual(d.phase,test_display.AWAKE)
            h.run('ZORTRAX_SLEEP_MODE STATE=ENABLED')
            p.reactor.now=1300.;d._tick(1300.);self.assertEqual(d.phase,'ENTERING_SLEEP')
            self.assertEqual(d.timeout,300.)

    def test_disabled_sleep_does_not_dim_active_print_or_change_its_state(self):
        with session() as h:
            p,d=attach_display(h);h.print_state='printing'
            h.run('ZORTRAX_SLEEP_MODE STATE=DISABLED');p.reactor.now=1000.;d._tick(1000.)
            self.assertEqual(d.phase,test_display.AWAKE);self.assertEqual(h.print_state,'printing')
            self.assertEqual(h.hotend.target,0.)

    def test_ownership_and_menu_reads_do_not_copy_large_nvm_observation(self):
        with session() as h:
            h.nvm.store._published['calibration']={'large':list(range(10000))}
            with patch.object(h.nvm,'snapshot',side_effect=AssertionError('full ledger copied')):
                h.nvm.ui_snapshot();h.nvm.get_ownership_status(h.now)
                h.menu.page='setting_sort_mode';h.menu.rows(h.now);h.m._dynamic_lights(h.now)
                h.job.m04_service_busy();h.fans._peers_idle()


class InformationTests(unittest.TestCase):
    def test_fluidd_back_opens_parent_menus_until_the_dashboard(self):
        with session() as h:
            def click(label):
                prefix = '// action:prompt_button ' + label + '|'
                line = next(line for line in reversed(h.lines) if line.startswith(prefix))
                command = line.split('|')[1]
                h.lines.clear()
                h.run(command)
                return command

            def assert_page(page, title):
                self.assertIn('// action:prompt_begin ZORTRAX M300 - ' + title, h.lines)
                self.assertEqual(h.lines[-1], '// action:prompt_show')
                self.assertEqual((h.settings.page, h.menu.page, h.oled.page), (page, page, 'm04'))

            h.run('ZORTRAX_LIGHT')
            assert_page('setting_light_mode', 'Light')
            click('Back')
            assert_page('settings', 'Settings')
            click('Back')
            assert_page('zortrax', 'Menu')
            click('Information')
            assert_page('information', 'Information')
            click('Back')
            assert_page('zortrax', 'Menu')
            click('Back')
            assert_page('main', 'Main menu')
            click('Klipper')
            assert_page('klipper', 'Klipper')
            self.assertIn('// action:prompt_text Print state: Standby', h.lines)
            click('Back')
            assert_page('main', 'Main menu')
            click('Zortrax M300')
            assert_page('zortrax', 'Menu')
            click('Back')
            assert_page('main', 'Main menu')
            close = click('Back')
            self.assertEqual(h.lines, ['// action:prompt_end'])
            self.assertEqual(h.oled.page, 'status')
            with self.assertRaisesRegex(h.printer.command_error, 'Expired Settings view'):
                h.run(close)
            self.assertEqual(h.position, [150., 158., 5., 17.])
            self.assertEqual(h.hotend.target, 0.)

    def test_back_reaches_the_status_screen_after_opening_a_fluidd_macro(self):
        with session() as h:
            for command, route in (
                    ('ZORTRAX_HELP', ('help', 'information', 'zortrax', 'main')),
                    ('ZORTRAX_MODELS_SORT', ('setting_sort_mode', 'settings', 'zortrax', 'main'))):
                with self.subTest(command=command):
                    h.run(command)
                    for page in route:
                        self.assertEqual((h.oled.page, h.menu.page), ('m04', page))
                        h.oled._render(h.now)
                        self.assertEqual(h.oled._rows(h.now)[1][0][0], 'Back')
                        h.oled._select(h.now, h.oled._presented_actions)
                        self.assertIsNone(h.oled.message)
                    self.assertEqual(h.oled.page, 'status')
                    self.assertFalse(h.ui.history.stack)

    def test_fluidd_navigation_invalidates_previous_panel_view_and_keeps_print_context(self):
        with session() as h:
            previous = h.oled._input_context()
            h.run('ZORTRAX_INFORMATION REFRESH=0')
            self.assertEqual((h.oled.page, h.menu.page), ('m04', 'information'))
            self.assertNotEqual(h.oled._input_context(), previous)
            self.assertNotIn('m300-information', h.allocations)
            h.settings.action(h.settings._view_id(), 2)
            self.assertEqual(h.menu.page, 'info_printer')
            h.settings.action(h.settings._view_id(), 0)
            self.assertEqual(h.menu.page, 'information')
            h.settings.action(h.settings._view_id(), 0)
            self.assertEqual(h.menu.page, 'zortrax')
            h.run('ZORTRAX_SETTINGS')
            self.assertEqual(h.menu.page, 'settings')
            h.objects['m300_print_ui'] = NS(view=lambda now: ('PRINTING', None))
            h.run('ZORTRAX_HELP')
            self.assertEqual(h.menu.page, 'settings')

    def test_printer_information_uses_four_shared_rows_in_stock_order(self):
        with session('Z300-123456') as h:
            h.board.hardware.get_status = lambda: dict(
                hardware_label='HW05', serial_number='Z12345678', factory_print_minutes=120)
            h.nvm.record_completed_job(1800.)
            h.settings.history_seconds = 9000.  # Already overlaps the host counter.
            h.run('ZORTRAX_UI_SHOW PAGE=info_time')
            self.assertEqual(h.menu.page, 'info_printer')
            _, rows = h.menu.rows(h.now)
            expected = ['Model: Zortrax M300 Classic', 'Hardware version: HW05',
                        'Serial number: Z12345678', 'Total printing time: 2 h 30 min']
            self.assertEqual(rows, [('Back', ('page', 'information'))]
                             + [(line, None) for line in expected])
            for line in expected:
                self.assertIn('// action:prompt_text ' + line, h.lines)
                self.assertLessEqual(width(line), h.ui.row_pixels)
            h.oled._render(h.now)
            self.assertEqual(h.oled._render_wire, menu_frame(tuple(label for label, _ in rows),
                             (), 0, test_display.renderer.Frame,h.ui.oem_sprites.get('0x0801dc08')))
            self.assertIsNone(choose_icon(menu_page='info_printer'))

    def test_real_available_fields_and_no_inferred_serial_or_lifetime(self):
        with session() as h:
            info=h.settings.information(h.now)
            self.assertEqual(info['host_version'],'R16.12');self.assertEqual(info['hardware_version'],'HW05')
            self.assertIsNone(info['serial_number']);self.assertIsNone(info['total_print_seconds'])
            self.assertEqual(info['total_printing_time'],'Unavailable')
            self.assertIn('0.13.14.5',info['mcu_version'])
            self.assertNotEqual(info['serial_number'],h.nvm.store.identity['machine_id'])

    def test_explicit_printer_serial_is_labelled_with_its_configured_source(self):
        with session('Z300-123456') as h:
            info=h.settings.information(h.now)
            self.assertEqual(info['serial_number'],'Z300-123456');self.assertEqual(info['serial_source'],'Configured printer serial')

    def test_history_refresh_is_on_demand_cached_and_lifecycle_bound(self):
        with session() as h:
            self.assertNotIn('m300-information',h.allocations)
            with patch('payload.m300_settings.history_totals',return_value=7200.) as fetch:
                h.settings.request_refresh();h.settings.request_refresh()
                self.assertEqual(len(h.callbacks),1);self.assertTrue(h.settings.reading)
                h.callbacks.pop()(h.now);self.assertEqual(fetch.call_count,1)
                self.assertEqual(h.settings.information(h.now)['history_print_seconds'],7200.)
                for _ in range(100):h.settings.information(h.now);h.settings.get_status(h.now)
                self.assertEqual(fetch.call_count,1)
                h.now+=6.;h.settings.request_refresh();h.settings.invalidate();h.callbacks.pop()(h.now)
                self.assertEqual(fetch.call_count,1)

    def test_failed_history_read_keeps_last_known_total_and_marks_cached(self):
        with session() as h:
            h.settings.history_seconds=9000.
            with patch('payload.m300_settings.history_totals',side_effect=OSError('not ready')):
                h.settings.request_refresh();h.callbacks.pop()(h.now)
            info=h.settings.information(h.now)
            self.assertEqual(info['history_print_seconds'],9000.)
            self.assertIsNone(info['total_print_seconds'])
            self.assertIn('unavailable',info['history_error'])

    def test_http_totals_are_bounded_and_validate_numeric_values(self):
        for value in (False,-1.,float('nan'),float('inf'),'100',1.e16):
            body=json.dumps({'result':{'job_totals':{'total_print_time':value}}}).encode()
            response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock();response.read=Mock(return_value=body)
            with patch('payload.m300_settings.urllib.request.urlopen',return_value=response):
                with self.assertRaises(ValueError):history_totals('http://127.0.0.1:7125')
        body=json.dumps({'result':{'job_totals':{'total_print_time':0.}}}).encode()
        response.read.return_value=body
        with patch('payload.m300_settings.urllib.request.urlopen',return_value=response) as request:
            self.assertEqual(history_totals('http://127.0.0.1:7125'),0.)
            self.assertEqual(request.call_args.args[0].full_url,'http://127.0.0.1:7125/server/history/totals')
        response.read.return_value=b'x'*65537
        with patch('payload.m300_settings.urllib.request.urlopen',return_value=response):
            with self.assertRaisesRegex(ValueError,'64 KiB'):history_totals('http://127.0.0.1:7125')

    def test_help_targets_only_the_project_github_on_both_surfaces(self):
        with session() as h:
            h.run('ZORTRAX_HELP')
            self.assertTrue(any(PROJECT_URL in line for line in h.lines))
            self.assertEqual((h.oled.page, h.menu.page), ('m04', 'help'))
            lines = [label for label,action in h.menu.rows(h.now)[1] if action is None]
            joined=''.join(lines[:3])
            self.assertEqual('https://'+joined,PROJECT_URL)
            self.assertFalse(any('zortrax.com' in line for line in h.lines))


class BrowserMenuTests(unittest.TestCase):
    def populate(self,h):
        for name,size,stamp in (('A.gcode',2,10),('a.gcode',3,30),('z.gcode',1,20)):
            p=h.files/name;p.write_text('x'*size);os.utime(p,(stamp,stamp))
        (h.files/'folder').mkdir()

    def test_all_four_sort_modes_work_and_keep_directories_first(self):
        with session() as h:
            self.populate(h);b=browser(h)
            expected={'NAME':['folder','A.gcode','a.gcode','z.gcode'],
                'NAME_CASE':['folder','A.gcode','a.gcode','z.gcode'],
                'DATE':['folder','a.gcode','z.gcode','A.gcode'],
                'SIZE':['folder','a.gcode','A.gcode','z.gcode']}
            for mode,names in expected.items():
                h.settings.set_option('sort_mode',mode)
                listing=b.list_files('host','',checkpoint=lambda:None)
                self.assertEqual([r['name'] for r in listing['files']],names)
            rows=[dict(name=n,path=n,is_dir=False,size=1,mtime=0) for n in ('z.gcode','A.gcode','a.gcode','Z.gcode')]
            self.assertNotEqual([r['name'] for r in sort_entries(rows,'NAME')],[r['name'] for r in sort_entries(rows,'NAME_CASE')])

    def test_actual_menu_browse_checkpoint_preview_and_validation_are_connected(self):
        with session() as h:
            self.populate(h);b=browser(h)
            h.menu.page='models';h.menu._last_file=None
            h.menu.select(('browse','host',''),h.now)
            self.assertEqual(h.menu.page,'browser');self.assertFalse(h.menu.reason)
            index=next(i for i,e in enumerate(b.catalog.entries) if e.name=='A.gcode')
            entry=b.catalog.entries[index]
            h.menu.select(('file','host',entry.path,h.menu.generation),h.now)
            self.assertEqual(h.menu.page,'preview');self.assertTrue(b.validate_preview(h.job.sd.selected))
            self.assertIn(('OEM print workflow is disabled',None),h.menu.rows(h.now)[1])
            self.assertFalse(any(r[1] and r[1][0]=='confirm_print' for r in h.menu.rows(h.now)[1]))
            self.assertEqual(h.position,[150.,158.,5.,17.]);self.assertEqual(h.hotend.target,0.)

    def test_sort_changes_expire_the_visible_browser_selection(self):
        with session() as h:
            self.populate(h);b=browser(h);old=b.list_files()['generation']
            h.settings.set_option('sort_mode','DATE')
            with self.assertRaisesRegex(BrowserError,'expired'):b.preview_file(old,1)

    def test_navigation_or_restart_during_io_cannot_publish_an_old_listing(self):
        with session() as h:
            self.populate(h);b=browser(h)
            def checkpoint():b.invalidate()
            with self.assertRaises(BrowserError):b.list_files(checkpoint=checkpoint)
            self.assertEqual(b.catalog.entries,());self.assertFalse(b.io_busy)

    def test_source_file_changes_revoke_checked_preview(self):
        with session() as h:
            self.populate(h);b=browser(h);generation=b.list_files()['generation']
            index=next(i for i,e in enumerate(b.catalog.entries) if e.name=='A.gcode')
            b.preview_file(generation,index);(h.files/'A.gcode').write_text('new content')
            with self.assertRaisesRegex(BrowserError,'changed'):b.validate_preview(h.job.sd.selected)

    def test_host_case_sensitive_names_are_valid_but_sd_case_collisions_are_rejected(self):
        entries=[dict(name=n,path=n,is_dir=False,size=1,mtime=0) for n in ('A.gcode','a.gcode')]
        catalog=Catalog();catalog.publish('host','',entries)
        with self.assertRaisesRegex(BrowserError,'duplicate'):catalog.publish('sd','',entries)


if __name__=='__main__':unittest.main()


class StockSettingsTests(unittest.TestCase):
    def test_recovered_firmware_frame_hashes_and_icon_bindings(self):
        evidence = json.loads((Path(__file__).parent / 'reference/firmware131_settings.json').read_text())
        self.assertEqual(evidence['source_sha256'], STOCK_SHA256)
        sprites = OEMGraphics()
        for frame in evidence['frames']:
            icon = choose_icon(menu_page=frame['page'])
            self.assertEqual(icon, frame['icon'])
            wire = menu_frame(tuple(frame['labels']), tuple(frame['active']),
                              frame['selected'], test_display.renderer.Frame, sprites.get(icon))
            self.assertEqual(hashlib.sha256(wire).hexdigest(), frame['sha256'])
