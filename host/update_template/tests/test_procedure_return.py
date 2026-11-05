"""Procedure navigation borrows the OLED without restoring control or consent."""
from types import SimpleNamespace as NS
import unittest

import test_display
from payload.m300_ui_m11_state import require_rows
from test_settings_information import session


def motion(h):
    status=dict(state='IDLE',busy=False,ready=True,installed=True,normal_control=True,
                session_token=0,operation=None,phase_id=0,phase='IDLE')
    owner=NS(operator_homing=None,get_status=lambda now:dict(status))
    h.objects['m300_motion']=owner
    def update(state='HOMING',operation='HOME_XY',token=1,phase='HOME_Y'):
        owner.operator_homing=operation
        status.update(state=state,busy=state=='HOMING',operation=operation,
                      session_token=token,phase_id=status['phase_id']+1,phase=phase)
        h.p._tick(h.now)
    return status,update


class ProcedureReturnTests(unittest.TestCase):
    def test_fluidd_homing_returns_to_the_native_status_for_each_axis_selection(self):
        for operation in ('HOME_X','HOME_Y','HOME_XY','HOME_Z','HOME_ALL'):
            with self.subTest(operation=operation),session() as h:
                h.oled._show_status();status,update=motion(h)
                update(operation=operation)
                self.assertEqual((h.menu.page,h.oled.page),('procedure','m04'))
                update('COMPLETE',operation)
                self.assertEqual((h.menu.page,h.oled.page),('main','status'))
                self.assertFalse(any('action:prompt_' in line for line in h.lines))

    def test_settings_page_cursor_and_back_history_are_restored(self):
        with session() as h:
            h.menu.page='setting_led_brightness';h.oled.selection=11
            h.nvm.set_setting('led_brightness',11)
            h.ui.history.stack[:]=['main','zortrax','settings']
            history=list(h.ui.history.stack);epoch=h.oled._input_epoch
            status,update=motion(h);update();update('COMPLETE')
            self.assertEqual((h.menu.page,h.oled.page,h.oled.selection),('setting_led_brightness','m04',11))
            self.assertEqual(h.ui.history.stack,history)
            self.assertGreater(h.oled._input_epoch,epoch)
            self.assertIsNone(h.oled._presented_actions)
            update(token=2)
            h.nvm.set_setting('led_brightness',4)
            update('COMPLETE',token=2)
            self.assertEqual(h.oled.selection,4)
            self.assertEqual(h.nvm.get_setting('led_brightness'),4)

    def test_oled_macro_keeps_the_clicked_row_before_the_dispatcher_resets_cursor(self):
        with session() as h:
            status,update=motion(h)
            h.gcode.register_command('ZORTRAX_HOME_XY',None)
            h.gcode.register_command('ZORTRAX_HOME_XY',lambda cmd:update())
            h.menu.page='maintenance'
            rows=h.menu.rows(h.now)[1]
            selected=next(i for i,row in enumerate(rows) if row[0]=='Homing XY')
            h.oled.selection=selected
            before=len(h.callbacks)
            h.oled._select(h.now)
            self.assertEqual(h.oled.selection,0)
            h.callbacks.pop(before)(h.now)
            self.assertEqual(h.menu.page,'procedure')
            update('COMPLETE')
            self.assertEqual((h.menu.page,h.oled.selection),('maintenance',selected))

    def test_a_different_session_cannot_consume_the_saved_origin(self):
        with session() as h:
            h.oled._show_status();status,update=motion(h);update()
            self.assertFalse(h.menu.return_from_procedure('m300_motion','HOME_XY',99))
            self.assertEqual(h.menu.page,'procedure')
            update('COMPLETE')
            self.assertEqual(h.oled.page,'status')

    def test_manual_navigation_survives_later_phases_and_completion(self):
        with session() as h:
            h.oled._show_status();status,update=motion(h);update()
            h.menu._navigate('setting_oled_brightness');h.oled.selection=9
            h.nvm.set_setting('oled_brightness',9)
            update(phase='HOME_X');update('COMPLETE')
            self.assertEqual((h.menu.page,h.oled.selection),('setting_oled_brightness',9))
            update(token=2);update('COMPLETE',token=2)
            self.assertEqual((h.menu.page,h.oled.selection),('setting_oled_brightness',9))

    def test_explicit_return_to_status_dismisses_further_automatic_takeover(self):
        with session() as h:
            status,update=motion(h);update()
            h.oled._show_status();update(phase='HOME_X')
            self.assertEqual(h.oled.page,'status')
            update('COMPLETE')
            self.assertEqual(h.oled.page,'status')

    def test_fault_is_left_visible_until_operator_acknowledges_it(self):
        with session() as h:
            h.oled._show_status();status,update=motion(h);update()
            update('FAULT')
            self.assertEqual((h.menu.page,h.oled.page),('procedure','m04'))
            h.menu.return_from_procedure('m300_motion','HOME_XY',1,explicit=True)
            self.assertEqual(h.oled.page,'status')

    def test_a_rejected_oled_command_does_not_leave_a_launch_hint(self):
        with session() as h:
            status,update=motion(h)
            def refuse(cmd):raise h.printer.command_error('test rejection')
            h.gcode.register_command('ZORTRAX_HOME_XY',None)
            h.gcode.register_command('ZORTRAX_HOME_XY',refuse)
            h.menu._native_script('ZORTRAX_HOME_XY')
            h.callbacks.pop()(h.now)
            self.assertIsNone(h.menu._procedure_launch)
            h.oled.selection=3;update();update('COMPLETE')
            self.assertEqual(h.oled.selection,3)

    def test_back_from_temporary_settings_after_completion_restores_status(self):
        with session() as h:
            h.oled._show_status();status,update=motion(h);update()
            h.ui.leveling_settings=True
            h.menu._navigate('settings',remember=False);h.oled.selection=0
            update('COMPLETE')
            _,rows=h.menu.rows(h.now)
            self.assertEqual(rows[0][1],('procedure_return','m300_motion',1))
            self.assertTrue(require_rows(rows))
            h.oled._select(h.now)
            self.assertEqual(h.oled.page,'status')

    def test_native_service_completions_from_fluidd_return_to_status(self):
        for command,name,waiting in (('ZORTRAX_HEAT','m','WAIT_CONFIRM'),
                                    ('ZORTRAX_LOAD','f','WAIT_INSERT'),
                                    ('ZORTRAX_UNLOAD','f','WAIT_UNLOAD')):
            with self.subTest(command=command),session() as h:
                h.oled._show_status();h.run(command);h.p._tick(h.now)
                service=getattr(h,name);h.heat(service,waiting)
                h.action('CONFIRM');h.until(service,'COMPLETE');h.p._tick(h.now)
                self.assertEqual(h.oled.page,'status')
                self.assertEqual(h.hotend.target,0.)
        with session() as h:
            h.oled._show_status();h.run('ZORTRAX_FAN_TEST_START');h.p._tick(h.now)
            self.assertEqual(h.menu.page,'fan_test')
            h.action('BACK');h.p._tick(h.now)
            self.assertEqual(h.oled.page,'status')

    def test_restart_invalidates_navigation_context_and_action_receipts(self):
        with session() as h:
            status,update=motion(h);update()
            h.menu.invalidate('klippy:disconnect')
            self.assertIsNone(h.menu._procedure_return)
            self.assertIsNone(h.menu._procedure_launch)
            self.assertIsNone(h.menu._procedure_dismissed)
            self.assertEqual(h.ui.history.stack,[])

    def test_phase_changes_do_not_overwrite_origin_or_add_history_entries(self):
        with session() as h:
            h.menu.page='information';h.oled.selection=2
            h.ui.history.stack[:]=['main','zortrax']
            status,update=motion(h);update()
            origin=h.menu._procedure_return['origin']
            for phase in ('HOME_X','Z_PREHEAT','HOME_Z_NATIVE_PROBE','Z_FINAL_CLEARANCE'):
                update(phase=phase)
                self.assertIs(h.menu._procedure_return['origin'],origin)
                self.assertNotIn('procedure',h.ui.history.stack)
            update('CANCELLED')
            self.assertEqual((h.menu.page,h.oled.selection),('information',2))
            self.assertEqual(h.ui.history.stack,['main','zortrax'])


if __name__=='__main__':unittest.main()
