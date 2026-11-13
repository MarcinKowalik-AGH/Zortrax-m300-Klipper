"""Native temperature-editor pixels, real encoder/ACK path and guarded heater application on explicit confirmation."""
import unittest
from unittest.mock import patch

import test_display
from test_settings_information import session
from payload.m300_settings_ui import temperature_frame
from payload.m300_ui_m11_state import require_rows
from payload.m300_oem_graphics import OEMGraphics
from payload.m300_leveling_oem import width
from tests.reference import native_heaters
from types import SimpleNamespace as NS
import threading


Frame = test_display.renderer.Frame


def limits(h):
    h.hotend.min_temp = h.bed.min_temp = 5.
    h.hotend.max_temp, h.bed.max_temp = 310., 120.
    h.hotend.m300_target_max, h.bed.m300_target_max = 305., 105.


def bind_native_heaters(h):
    if getattr(h, '_native_heater_bound', False):
        return
    h._native_heater_bound = True
    # The shared menu fixture normally uses RuntimeError; use production's
    # native command-error contract for asynchronously executed commands.
    from payload.m300_menu import M300Menu
    h.menu._error = M300Menu._error.__get__(h.menu, M300Menu)
    manager = native_heaters.PrinterHeaters.__new__(native_heaters.PrinterHeaters)
    manager.printer = h.printer
    h.objects['heaters'] = manager
    for name, heater in (('extruder', h.hotend), ('heater_bed', h.bed)):
        heater.printer = h.printer
        h.gcode.register_mux_command('SET_HEATER_TEMPERATURE', 'HEATER', name,
            lambda cmd, obj=heater: native_heaters.Heater.cmd_SET_HEATER_TEMPERATURE(obj, cmd))


def apply_pending(h):
    # The explicit click appends one nonblocking native command callback.
    h.callbacks.pop()(h.now)


def enter(h, kind):
    bind_native_heaters(h)
    limits(h)
    h.menu.page = 'klipper'
    rows = h.menu.rows(h.now)[1]
    index = next(i for i, (_, a) in enumerate(rows)
                 if a == ('temperatures', kind, 'klipper'))
    h.oled.selection = index
    h.oled._render(h.now)
    h.panel_display.pump()
    h.oled._select(h.now, h.oled._presented_actions)
    h.oled._render(h.now)
    h.panel_display.pump()
    return index


def event(h, sequence, nav=0, shorts=0, longs=0):
    h.now += .1
    at = len(h.callbacks)
    h.oled._panel(dict(sequence=sequence, position=nav*4, nav_position=nav*4,
        invalid=0, pressed=False, presses=shorts+longs, releases=shorts+longs,
        shorts=shorts, longs=longs, **{'#receive_time': h.now}))
    h.callbacks.pop(at)(h.now)


def pixel(wire, x, y):
    byte = wire[y*128+x//2]
    return byte & 15 if x % 2 else byte >> 4


class TemperatureEditorTests(unittest.TestCase):
    def test_all_one_degree_values_respect_native_and_policy_limits(self):
        with session() as h:
            limits(h)
            for kind, low, high in (('HOTEND',170,305),('BED',40,105)):
                h.menu.page='temperature_'+kind;h.menu._return_page='klipper'
                rows=h.menu.rows(h.now)[1]
                self.assertTrue(require_rows(rows))
                self.assertEqual([a[2] for _,a in rows[1:]],list(range(low,high+1)))
                self.assertLessEqual(len(rows),256)
            h.hotend.max_temp=260.9;h.bed.m300_target_max=84.7
            self.assertEqual(h.menu.temperature_range('HOTEND'),(170,260))
            self.assertEqual(h.menu.temperature_range('BED'),(40,84))
            h.bed.min_temp=50.1
            self.assertEqual(h.menu.temperature_range('BED'),(51,84))

    def test_menu_entry_prefers_actual_target_then_last_choice_when_off(self):
        with session() as h:
            limits(h);h.menu.page='temperature_HOTEND'
            h.hotend.target=215.;h.menu._temperature['HOTEND']=207
            self.assertEqual(h.menu.temperature_selection(),46)
            h.menu._temperature['HOTEND']=None
            self.assertEqual(h.menu.temperature_selection(),46)
            h.hotend.target=0.
            self.assertEqual(h.menu.temperature_selection(),1)
            h.hotend.target=float('nan')
            self.assertEqual(h.menu.temperature_selection(),1)
            self.assertIsNone(h.menu._temperature['HOTEND'])
            h.menu.page='klipper'
            self.assertIsNone(h.menu.temperature_selection())

    def test_no_valid_range_leaves_back_only(self):
        with session() as h:
            limits(h);h.hotend.max_temp=160.
            h.menu.page='temperature_HOTEND';h.menu._return_page='klipper'
            self.assertEqual(h.menu.rows(h.now)[1],[('Back',('page','klipper'))])
            self.assertIsNone(h.menu.temperature_selection())
            h.oled.selection=0;h.oled._render(h.now);h.panel_display.pump()
            self.assertEqual(len(h.oled._render_wire),8192)
            event(h,1);event(h,2,shorts=1)
            self.assertEqual(h.menu.page,'klipper')
            self.assertEqual(h.hotend.target,0.)

    def test_bad_limits_are_not_converted_into_heater_choices(self):
        with session() as h:
            limits(h)
            for value in (float('nan'),float('inf'),False):
                h.hotend.max_temp=value
                self.assertIsNone(h.menu.temperature_range('HOTEND'))
            self.assertIsNone(h.menu.temperature_range('UNKNOWN'))

    def test_both_editors_render_all_temperatures_without_heat_motion_or_nvm_writes(self):
        with session() as h:
            limits(h);before=(h.hotend.target,h.bed.target,list(h.position))
            stored=dict(h.menu._temperature);settings=dict(h.nvm.store._published['settings'])
            for kind in ('HOTEND','BED'):
                enter(h,kind)
                rows=h.menu.rows(h.now)[1]
                for index in range(len(rows)):
                    h.oled.selection=index;h.oled._render(h.now)
                    self.assertEqual(len(h.oled._render_wire),8192)
                    self.assertEqual(h.ui.last_sprite,'activity:heat_nozzle' if kind=='HOTEND' else 'activity:heat_bed')
                self.assertEqual(h.menu._temperature,stored)
            self.assertEqual((h.hotend.target,h.bed.target,list(h.position)),before)
            self.assertEqual(h.nvm.store._published['settings'],settings)

    def test_icons_match_approved_native_pixels_without_resizing_or_thresholding(self):
        sprites=OEMGraphics()
        for symbol in ('heat_nozzle','heat_bed'):
            sprite=sprites.get('activity:'+symbol,0.)
            wire=temperature_frame('Hotend TEMP',205,170,305,False,Frame,sprite)
            raw=sprite[2]
            for y in range(50):
                for x in range(50):
                    b=raw[y*25+x//2]
                    self.assertEqual(pixel(wire,200+x,y),b&15 if x%2 else b>>4)
            self.assertLessEqual(width('305°C'),50)
            self.assertTrue(any(pixel(wire,x,y) for x in range(200,250) for y in range(51,64)))
            self.assertTrue(all(pixel(wire,x,50)==0 for x in range(200,250)))

    def test_bar_matches_brightness_geometry_and_has_distinct_minimum_and_maximum(self):
        minimum=temperature_frame('Hotend TEMP',170,170,305,False,Frame)
        maximum=temperature_frame('Hotend TEMP',305,170,305,False,Frame)
        for segment in range(16):
            self.assertEqual(pixel(minimum,17+10*segment,58),0)
            self.assertEqual(pixel(maximum,17+10*segment,58),15)
            self.assertEqual(pixel(minimum,16+10*segment,58),5)
        self.assertEqual(temperature_frame('Bed TEMP',70,70,70,False,Frame),
                         temperature_frame('Bed TEMP',70,70,70,False,Frame))
        with self.assertRaises(ValueError):temperature_frame('Bed TEMP',106,40,105,False,Frame)

    def test_first_open_selects_current_choice_and_back_restores_parent_cursor(self):
        with session() as h:
            index=enter(h,'HOTEND')
            self.assertEqual((h.menu.page,h.oled.selection),('temperature_HOTEND',31))
            h.oled.selection=0;h.oled._render(h.now);h.panel_display.pump()
            h.oled._select(h.now,h.oled._presented_actions)
            self.assertEqual((h.menu.page,h.oled.selection),('klipper',index))
            self.assertEqual(h.menu._temperature['HOTEND'],200.)

    def test_rotation_is_draft_and_acknowledged_click_applies_native_target(self):
        for kind,initial in (('HOTEND',200),('BED',60)):
            with self.subTest(kind=kind),session() as h:
                parent=enter(h,kind);h.oled.menu_reverse=True
                event(h,1);event(h,2,nav=-3)
                self.assertEqual(h.menu._temperature[kind],initial)
                h.oled._render(h.now);h.panel_display.pump()
                event(h,3,nav=-3,shorts=1)
                self.assertEqual((h.hotend.target,h.bed.target),(0.,0.))
                apply_pending(h)
                self.assertEqual(h.menu._temperature[kind],initial+3)
                self.assertEqual((h.menu.page,h.oled.selection),('klipper',parent))
                self.assertEqual(h.hotend.target if kind=='HOTEND' else h.bed.target,initial+3)
                self.assertEqual(h.bed.target if kind=='HOTEND' else h.hotend.target,0.)

    def test_coalesced_turn_and_press_never_confirms_unseen_temperature(self):
        with session() as h:
            enter(h,'HOTEND');h.oled.menu_reverse=True
            event(h,1);event(h,2,nav=-4,shorts=1)
            self.assertEqual(h.menu.page,'temperature_HOTEND')
            self.assertEqual(h.menu._temperature['HOTEND'],200.)
            h.oled._render(h.now);h.panel_display.pump()
            event(h,3,nav=-4,shorts=2)
            apply_pending(h)
            self.assertEqual(h.menu._temperature['HOTEND'],204)

    def test_unacknowledged_draft_is_not_accepted(self):
        with session() as h:
            enter(h,'BED');h.oled.menu_reverse=True
            event(h,1);event(h,2,nav=-2)
            h.oled._render(h.now)  # Deliberately do not acknowledge the new wire.
            event(h,3,nav=-2,shorts=1)
            self.assertEqual((h.menu.page,h.menu._temperature['BED']),('temperature_BED',60.))
            h.panel_display.pump()
            event(h,4,nav=-2,shorts=2)
            apply_pending(h)
            self.assertEqual(h.menu._temperature['BED'],62)

    def test_long_press_cancels_draft_and_restores_parent_cursor(self):
        with session() as h:
            parent=enter(h,'BED');h.oled.menu_reverse=True
            event(h,1);event(h,2,nav=-5)
            h.oled._render(h.now);h.panel_display.pump()
            event(h,3,nav=-5,longs=1)
            self.assertEqual((h.menu.page,h.oled.selection),('klipper',parent))
            self.assertEqual(h.menu._temperature['BED'],60.)
            self.assertEqual(h.bed.target,0.)

    def test_rotation_clamps_at_range_ends_and_back_not_wrap(self):
        with session() as h:
            enter(h,'HOTEND');h.oled.menu_reverse=True
            event(h,1)
            for n in range(1,6):event(h,n+1,nav=-32*n)
            self.assertEqual(h.oled.selection,136)
            h.oled._render(h.now);h.panel_display.pump()
            for n in range(1,6):event(h,n+6,nav=-160+32*n)
            self.assertEqual(h.oled.selection,0)
            self.assertEqual(h.menu._temperature['HOTEND'],200.)

    def test_changed_target_limit_between_render_and_click_is_rejected(self):
        with session() as h:
            enter(h,'HOTEND');h.oled.selection=136
            h.oled._render(h.now);h.panel_display.pump()
            actions=h.oled._presented_actions
            h.hotend.m300_target_max=280.
            h.oled._select(h.now,actions)
            self.assertIsNotNone(h.oled.message)
            self.assertEqual(h.menu._temperature['HOTEND'],200.)
            self.assertEqual(h.hotend.target,0.)

    def test_direct_stale_or_invalid_choice_has_no_side_effect(self):
        for action in (('temp','HOTEND',306,'klipper'),('temp','HOTEND',True,'klipper'),
                       ('temp','HOTEND',200.5,'klipper'),('temp','BED',60,'klipper')):
            with session() as h:
                enter(h,'HOTEND')
                before=dict(h.menu._temperature)
                h.menu.select(action,h.now)
                self.assertTrue(h.menu.reason)
                self.assertEqual(h.menu._temperature,before)
                self.assertEqual((h.hotend.target,h.bed.target),(0.,0.))

    def test_stale_input_after_leaving_view_cannot_select_new_temperature(self):
        with session() as h:
            enter(h,'HOTEND');event(h,1)
            h.now+=.1;at=len(h.callbacks)
            h.oled._panel(dict(sequence=2,position=0,nav_position=0,invalid=0,
                pressed=False,presses=1,releases=1,shorts=1,longs=0,**{'#receive_time':h.now}))
            h.menu._navigate('klipper')
            h.callbacks.pop(at)(h.now)
            self.assertEqual(h.menu.page,'klipper')
            self.assertEqual(h.menu._temperature['HOTEND'],200.)

    def test_blank_or_disconnected_panel_cannot_confirm(self):
        with session() as h:
            enter(h,'HOTEND');event(h,1)
            h.oled.stream.ready=False
            event(h,2,shorts=1)
            self.assertEqual(h.menu.page,'temperature_HOTEND')
            self.assertEqual(h.menu._temperature['HOTEND'],200.)
            h.oled.connected=False
            event(h,3,shorts=2)
            self.assertEqual(h.menu._temperature['HOTEND'],200.)

    def test_existing_heat_action_remains_compatible_after_applied_selection(self):
        with session() as h:
            enter(h,'HOTEND')
            h.menu.select(('temp','HOTEND',213,'klipper'),h.now)
            apply_pending(h)
            self.assertEqual(h.hotend.target,213.)
            with patch.object(h.menu,'_native_script') as start:
                h.menu.select(('service','HOTEND'),h.now)
                start.assert_called_once_with('SET_HEATER_TEMPERATURE HEATER=extruder TARGET=213')
            self.assertEqual(h.menu._temperature['BED'],60.)

    def test_changed_limits_in_gcode_queue_refuse_without_false_acceptance(self):
        with session() as h:
            enter(h,'HOTEND')
            h.menu.select(('temp','HOTEND',300,'klipper'),h.now)
            h.hotend.m300_target_max=250.
            apply_pending(h)
            self.assertEqual(h.hotend.target,0.)
            self.assertEqual(h.menu._temperature['HOTEND'],200.)
            self.assertIn('limits changed',h.menu.reason)
            self.assertIsNotNone(h.oled.message)

    def test_new_external_target_is_not_overwritten_by_a_queued_click(self):
        with session() as h:
            enter(h,'BED')
            h.menu.select(('temp','BED',70,'klipper'),h.now)
            h.run('SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=55')
            apply_pending(h)
            self.assertEqual(h.bed.target,55.)
            self.assertIn('target changed',h.menu.reason)
            self.assertEqual(h.menu._temperature['BED'],60.)

    def test_navigation_or_shutdown_cancels_queued_target(self):
        for change in ('navigation','shutdown'):
            with self.subTest(change=change),session() as h:
                enter(h,'HOTEND')
                h.menu.select(('temp','HOTEND',220,'klipper'),h.now)
                if change=='navigation':h.menu._navigate('maintenance')
                else:h.shutdown=True
                apply_pending(h)
                self.assertEqual(h.hotend.target,0.)
                self.assertEqual(h.menu._temperature['HOTEND'],200.)

    def test_disconnected_panel_cannot_apply_a_pending_target(self):
        with session() as h:
            enter(h,'BED')
            h.menu.select(('temp','BED',80,'klipper'),h.now)
            h.oled.connected=False
            apply_pending(h)
            self.assertEqual(h.bed.target,0.)
            self.assertIn('disconnected',h.menu.reason)

    def test_service_heater_ownership_is_not_bypassed_by_oled(self):
        with session() as h:
            enter(h,'HOTEND')
            h.menu.select(('temp','HOTEND',220,'klipper'),h.now)
            from payload.m300_native_service import NativeServiceLease
            owner=NS(printer=h.printer,gcode=h.gcode)
            lease=NativeServiceLease(owner,lambda:1,lambda:None,lambda why:None)
            lease.acquire(h.toolhead,h.gmove,[h.hotend,h.bed])
            try:
                apply_pending(h)
                self.assertEqual(h.hotend.target,0.)
                self.assertEqual(h.menu._temperature['HOTEND'],200.)
                self.assertIn('owns heaters',h.menu.reason)
                self.assertIsNotNone(h.oled.message)
            finally:lease.release()

    def test_parent_labels_follow_live_native_targets_including_off(self):
        with session() as h:
            enter(h,'HOTEND')
            self.assertEqual(h.menu._temperature_label('HOTEND'),'OFF')
            h.run('SET_HEATER_TEMPERATURE HEATER=extruder TARGET=225')
            self.assertEqual(h.menu._temperature_label('HOTEND'),'225°C')
            h.run('SET_HEATER_TEMPERATURE HEATER=extruder TARGET=0')
            self.assertEqual(h.menu._temperature_label('HOTEND'),'OFF')

    def test_real_native_heater_status_exposes_target_after_physical_click(self):
        # Actual pinned Heater.set_temp/get_status and native G-code dispatcher;
        # the physical encoder/OLED ACK path is modelled, not bypassed.
        with session() as h:
            heater=native_heaters.Heater.__new__(native_heaters.Heater)
            heater.printer=h.printer;heater.lock=threading.Lock()
            heater.target_temp=0.;heater.smoothed_temp=25.;heater.last_pwm_value=0.
            h.hotend=h.job.hotend=heater
            enter(h,'HOTEND');h.oled.menu_reverse=True
            event(h,1);event(h,2,nav=-10)
            h.oled._render(h.now);h.panel_display.pump()
            event(h,3,nav=-10,shorts=1)
            self.assertEqual(heater.get_status(h.now)['target'],0.)
            apply_pending(h)
            self.assertEqual(heater.get_status(h.now)['target'],210.)
            self.assertEqual(h.menu._temperature_label('HOTEND'),'210°C')
            h.menu.page='temperature_HOTEND'
            self.assertEqual(h.menu.temperature_selection(),41)

    def test_apply_changes_no_motion_nvm_or_other_heater(self):
        with session() as h:
            enter(h,'BED')
            initial=list(h.position);nvm=h.nvm.ui_snapshot()
            h.menu.select(('temp','BED',72,'klipper'),h.now)
            apply_pending(h)
            self.assertEqual(h.bed.target,72.)
            self.assertEqual(h.hotend.target,0.)
            self.assertEqual(h.position,initial)
            self.assertEqual(h.nvm.ui_snapshot(),nvm)

    def test_handler_that_does_not_set_target_reports_failure(self):
        with session() as h:
            enter(h,'BED')
            h.menu.select(('temp','BED',72,'klipper'),h.now)
            with patch.object(h.gcode,'run_script_from_command',return_value=None):
                apply_pending(h)
            self.assertEqual(h.bed.target,0.)
            self.assertEqual(h.menu._temperature['BED'],60.)
            self.assertIn('did not accept',h.menu.reason)


if __name__ == '__main__':
    unittest.main()
