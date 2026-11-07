"""Meaning, animation lifecycle and non-overlapping native OLED composition."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

from payload.m300_activity_graphics import ActivityGraphics, fault_symbol, menu_symbol, procedure_symbol
from payload.m300_oem_graphics import OEMGraphics
from payload.m300_settings_ui import brightness_frame
from payload.m300_settings import PAGES
from test_display import renderer
from test_settings_information import session
from test_print_context import printing, pause, acknowledged


def pixel(wire, x, y):
    return (wire[y*128+x//2] >> (0 if x%2 else 4)) & 15


def right_icon(wire):
    return bytes((pixel(wire, 200+x, 7+y)<<4) | pixel(wire, 201+x, 7+y)
                 for y in range(50) for x in range(0, 50, 2))


class ActivityGraphicsTests(unittest.TestCase):
    def test_project_marks_animate_at_existing_cadence_without_control_io(self):
        with session() as h:
            h.menu.page='main'
            _,rows=h.menu.rows(h.now)
            for index,key in ((0,'project-klipper'),(1,'project-zortrax')):
                frames=[h.ui.get_oem_sprite('m04',rows,index,frame*.5) for frame in range(4)]
                self.assertEqual(h.ui.last_sprite,key)
                self.assertEqual({(w,height,len(raw)) for w,height,raw in frames},{(50,50,1250)})
                self.assertEqual(len({raw for _,_,raw in frames}),4)
                self.assertLessEqual(set(b''.join(raw for _,_,raw in frames)),{0,15,240,255})
                self.assertEqual(h.ui.get_oem_sprite('m04',rows,index,2.),frames[0])
            self.assertFalse(any(event[0] in ('heat','move','fan') for event in h.events))

    def test_all_native_frames_decode_and_cache_stays_bounded(self):
        graphics=ActivityGraphics()
        for name in graphics.spec['symbols']:
            frames=[graphics.get('activity:'+name, n*.5)[2] for n in range(4)]
            self.assertEqual(len(set(frames)),4,name)
            self.assertEqual(graphics.get('activity:'+name, 2.)[2],frames[0])
        self.assertLessEqual(graphics._frame.cache_info().currsize,32)
        self.assertEqual(graphics.get('activity:unknown'),None)

    def test_corrupt_runtime_frame_is_rejected(self):
        spec=copy.deepcopy(ActivityGraphics().spec)
        spec['symbols']['heat_bed']['frames'][0]['sha256']='0'*64
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sprites.json';path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError,'integrity'):
                ActivityGraphics(path).get('activity:heat_bed')

    def test_menu_command_previews_match_operations_and_are_static(self):
        cases={'ZORTRAX_HEAT':'heat_nozzle','M109 S240':'heat_nozzle',
               'M190 S60':'heat_bed','TURN_OFF_HEATERS':'cooling',
               'ZORTRAX_BED_MESH':'bed_mesh','ZORTRAX_FAN_LOWER':'fan_lower',
               'ZORTRAX_FAN_TEST_START':'fan_upper','SAVE_CONFIG':'firmware_update'}
        for command, name in cases.items():
            choice=menu_symbol('klipper','m04',[('',('native_gcode',command))])
            self.assertEqual((choice.key,choice.animated),('activity:'+name,False))

    def test_fault_icons_explain_reported_failures_without_creating_a_fault(self):
        cases={'filament jam':'filament_jam','filament runout':'filament_runout',
               'heater_bed overtemperature':'bed_overheat','hotend overtemperature':'hotend_overheat',
               'temperature sensor fault':'sensor_fault','heating timed out':'heating_failed',
               'No trigger on probe after full movement':'probe_contact_fault',
               'platform connector fault':'platform_connector','M112 emergency stop':'emergency_stop',
               'MCU disconnected':'connection_lost'}
        for reason, name in cases.items():
            status=dict(state='FAULT',reason=reason)
            before=dict(status)
            self.assertEqual(fault_symbol(status).key,'activity:'+name)
            self.assertEqual(status,before)
        self.assertIsNone(fault_symbol(dict(state='IDLE',reason='filament jam',filament_runout=True)))
        self.assertIsNone(fault_symbol(dict(state='FAULT',reason='nozzle temperature changed')))
        self.assertIsNone(fault_symbol(dict(state='FAULT',reason='resource busy',filament_runout=None)))

    def test_procedure_heating_cleaning_and_terminal_states_are_distinct(self):
        self.assertEqual(procedure_symbol('m300_maintenance',dict(state='HEATING',operation='HOTEND')).key,'activity:heat_nozzle')
        self.assertEqual(procedure_symbol('m300_thermal',dict(state='HEATING',heater='heater_bed')).key,'activity:heat_bed')
        self.assertEqual(procedure_symbol('m300_job',dict(state='WAIT_CLEAN',can_confirm_resume_clean=True)).key,'activity:clean_nozzle')
        self.assertEqual(procedure_symbol('m300_thermal',dict(state='COOLING')).key,'activity:cooling')
        self.assertIsNone(procedure_symbol('m300_maintenance',dict(state='COMPLETE',operation='HOTEND')))
        self.assertEqual(procedure_symbol('m300_thermal',dict(state='FAULT',reason='unclassified failure')),
                         ('0x0801be48',False))

    def test_all_settings_and_information_pages_have_a_rendered_icon(self):
        with session() as h:
            for page in PAGES:
                with self.subTest(page=page):
                    h.menu.page=page
                    _,rows=h.menu.rows(h.now)
                    icon=h.ui.get_oem_sprite('m04',rows,0,h.now)
                    self.assertIsNotNone(icon)
                    self.assertEqual(icon[1],50)
                    h.oled.selection=0;h.oled._render(h.now)
                    expected=icon[2][:43*25]+bytes(7*25) if page in (
                        'setting_oled_brightness','setting_led_brightness') else icon[2]
                    self.assertEqual(right_icon(h.oled._render_wire),expected)

    def test_brightness_keeps_sixteen_segments_and_clear_space_before_the_icon(self):
        sprite=OEMGraphics().get('activity:oled_brightness')
        for level in range(1,17):
            wire=brightness_frame('OLED brightness',level,False,renderer.Frame,sprite)
            for segment in range(16):
                self.assertEqual(pixel(wire,20+segment*10,57),15 if segment<level else 0)
            self.assertTrue(all(pixel(wire,x,y)==0 for x in range(174,200) for y in range(55,64)))
            self.assertEqual(right_icon(wire),sprite[2][:43*25]+bytes(7*25))

    def test_fan_only_animates_for_the_selected_enabled_channel(self):
        with session() as h:
            h.run('ZORTRAX_FAN_TEST_START');h.p._tick(h.now)
            h.oled.selection=1
            h.oled._render(h.now);before=h.oled._render_wire
            h.oled._render(h.now+.5)
            self.assertEqual(before,h.oled._render_wire)
            h.action('TOGGLE_UPPER');h.p._tick(h.now)
            h.oled._render(h.now);before=h.oled._render_wire
            h.oled._render(h.now+.5)
            self.assertNotEqual(before,h.oled._render_wire)
            self.assertEqual(h.ui.last_sprite,'activity:fan_upper')
            self.assertEqual(right_icon(h.oled._render_wire),h.ui.oem_sprites.get('activity:fan_upper',h.now+.5)[2])
            h.oled.selection=2;h.oled._render(h.now)
            self.assertEqual(h.ui.last_sprite,'activity:fan_lower')

    def test_mesh_menu_uses_the_existing_macro_and_busy_snapshot(self):
        with session() as h:
            status=dict(state='IDLE',busy=False,result=None)
            h.objects['m300_pad_mesh']=NS(get_status=lambda now:dict(status))
            h.menu.page='klipper'
            self.assertIn(('Bed mesh (25 points)',('page','bed_mesh')),h.menu.rows(h.now)[1])
            h.menu.page='bed_mesh';_,rows=h.menu.rows(h.now)
            self.assertIn(('Measure 25 pad points',('native_gcode','ZORTRAX_BED_MESH')),rows)
            status.update(state='PROBING',busy=True)
            _,rows=h.menu.rows(h.now)
            self.assertFalse(any(action and action[0]=='native_gcode' for _,action in rows))
            self.assertNotEqual(h.ui.get_oem_sprite('m04',rows,0,h.now),h.ui.get_oem_sprite('m04',rows,0,h.now+.5))
            self.assertEqual(status['state'],'PROBING')

    def test_file_work_only_animates_while_its_owner_is_busy(self):
        self.assertFalse(menu_symbol('browser','m04',browser=dict(source='sd',busy=False)).animated)
        self.assertEqual(menu_symbol('preview','m04',browser=dict(busy=True)).key,'activity:file_convert')
        self.assertTrue(menu_symbol('browser','m04',sd=dict(busy=True)).animated)

    def test_native_completed_print_uses_check_and_pause_keeps_information_symbol(self):
        with printing() as h:
            pause(h);acknowledged(h)
            self.assertEqual(right_icon(h.oled._render_wire),h.ui.oem_sprites.get('0x0801dc08')[2])
            h.sd.print_stats.state='complete';h.sd.current_file=None;h.sd.work_timer=None
            h.objects['toolhead'].check_busy=lambda now:(0,1,True)
            acknowledged(h)
            self.assertEqual(right_icon(h.oled._render_wire),h.ui.oem_sprites.get('0x0801c024')[2])

    def test_probe_error_notice_keeps_its_own_graphic_and_text_area(self):
        with session() as h:
            h.oled.message=('Probe error','No trigger on probe after full movement')
            h.oled._render(h.now)
            self.assertEqual(h.ui.last_sprite,'activity:probe_contact_fault')
            self.assertEqual(right_icon(h.oled._render_wire),h.ui.oem_sprites.get(h.ui.last_sprite,h.now)[2])


if __name__=='__main__':
    unittest.main()
