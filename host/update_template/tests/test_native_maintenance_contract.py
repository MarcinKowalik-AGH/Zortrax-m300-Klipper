"""OEM Maintenance traces, native thermostat ownership and actual OLED dispatch."""
import base64
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch
import zlib

import test_display
from test_native_oem_services import Harness, physical_panel
from test_native_menu import fixture as menu_fixture
from test_macro_dispatch import ENV, templates
from tests.reference import native_gcode
from payload.m300_native_fans import M300NativeFans, OEM_DUTY
from payload.m300_maintenance_ui import fan_frame
from payload.m300_ui_m11_state import require_rows
from setup_fluidd import category

# Only the physical fan constructor is replaced. The thermostat callback is
# the exact pinned heater_fan source, not a reimplementation of its decisions.
with patch.dict(sys.modules, {'tests.reference.fan':ModuleType('tests.reference.fan')}):
    from tests.reference.native_heater_fan import PrinterHeaterFan

REFERENCE=json.loads((Path(__file__).parent/'reference/firmware131_maintenance.json').read_text())


class ElectricalFan:
    def __init__(self,h,channel):
        self.h,self.channel,self.speed=h,channel,0.
        self.gcrq=NS(rqueue=[])
    def set_speed(self,value,print_time=None):
        self.speed=value;self.h.events.append(('fan',self.channel,value))
    def set_speed_from_command(self,value):self.set_speed(value)
    def get_status(self,now):return dict(speed=self.speed,rpm=None)


class FanHarness(Harness):
    def __init__(self):
        super().__init__()
        self.board_reads=0
        self.cooling=dict(status_fresh=True,forced_cooling=False,
            local_cooling=dict(status_fresh=True,mode_code=1,sample_valid=True))
        def board_status(now):
            self.board_reads+=1
            return self.cooling
        self.board.get_status=board_status
        self.board.get_mcu=lambda:NS(is_fileoutput=self.board.mcu.is_fileoutput,
            get_constants=lambda:dict(M300_FAN_POLICY=3,M300_LOCAL_COOLING_ABI=1))
        self.toolhead.check_busy=lambda now:(self.busy_until,now,now>=self.busy_until)
        self.lower,self.upper=ElectricalFan(self,'LOWER'),ElectricalFan(self,'UPPER')
        self.thermostat=PrinterHeaterFan.__new__(PrinterHeaterFan)
        self.thermostat.heaters=[self.hotend];self.thermostat.heater_temp=50.
        self.thermostat.fan_speed=1.;self.thermostat.last_speed=0.
        self.thermostat.fan=self.upper
        self.objects.update(fan=NS(fan=self.lower),**{'heater_fan hotend':self.thermostat})
        self.gcode.register_command('M106',lambda cmd:self.lower.set_speed_from_command(cmd.get_float('S',255.)/255.))
        self.gcode.register_command('M107',lambda cmd:self.lower.set_speed_from_command(0.))
        self.fans=M300NativeFans(self.config);self.objects['m300_fans']=self.fans
        self.fans._ready()
        self.job.m04_service_busy=lambda:any(self.objects[n].get_status(self.now)['busy']
            for n in ('m300_maintenance','m300_fans'))
        for name,body in templates().items():
            if name.startswith('ZORTRAX_FAN_'):
                template=ENV.from_string(body)
                self.gcode.register_command(name,lambda cmd,t=template:self.gcode.run_script_from_command(
                    t.render(params=cmd.get_command_parameters())))
        self.native_commands=dict(self.gcode.ready_gcode_handlers)
        self.lower_native=self.lower.set_speed;self.upper_native=self.upper.set_speed
        self.events.clear()
    def step(self,dt=.1):
        super().step(dt);self.fans._tick(self.now)
    def assert_restored(self,test):
        super().assert_restored(test)
        test.assertEqual(self.lower.set_speed,self.lower_native)
        test.assertEqual(self.upper.set_speed,self.upper_native)
    def action(self,verb):
        view=self.p.view(self.now);self.p.action(view['view_id'],verb)


class NativeFanContractTests(unittest.TestCase):
    def test_native_thermal_telemetry_does_not_claim_the_fan_test_lease(self):
        from payload.m300_thermal import M300Thermal

        h = FanHarness()
        thermal = M300Thermal(h.config)
        thermal.board = h.board
        thermal.heaters = {'extruder': h.hotend, 'heater_bed': h.bed}
        thermal._ready()
        h.objects['m300_thermal'] = thermal
        self.assertEqual(thermal.get_status(h.now)['state'], 'NATIVE')
        thermal.active = True
        thermal.state = 'PID_RUNNING'
        with self.assertRaisesRegex(native_gcode.CommandError, 'm300_thermal owns resources'):
            h.run('ZORTRAX_FAN_TEST_START')
        thermal.active = False
        thermal.state = 'IDLE'
        h.run('ZORTRAX_FAN_TEST_START')
        h.run('ZORTRAX_FAN_LOWER')
        self.assertEqual(h.lower.speed, OEM_DUTY)
        h.run('ZORTRAX_FAN_TEST_END')
        h.assert_restored(self)

    def test_original_save_off_toggle_150_and_restore_traces(self):
        for original in REFERENCE['fans']:
            h=FanHarness();initial=original['initial']
            h.lower.speed=initial[0]/255.
            # Upper state belongs to CURRENT thermostat, not an old OFF/PWM.
            h.run('ZORTRAX_FAN_TEST_START')
            observed=[[round(h.lower.speed*255),round(h.upper.speed*255)]]
            for command in ('UPPER','LOWER','UPPER','LOWER'):
                h.run('ZORTRAX_FAN_'+command)
                observed.append([round(h.lower.speed*255),round(h.upper.speed*255)])
            self.assertEqual(observed,[e['requests'] for e in original['events'][:-1]])
            h.run('ZORTRAX_FAN_TEST_END')
            self.assertAlmostEqual(h.lower.speed,initial[0]/255.)
            self.assertEqual(h.upper.speed,0.);h.assert_restored(self)
            self.assertIsNone(h.upper.get_status(h.now)['rpm'])

    def test_individual_macro_starts_the_same_shared_session(self):
        for command,which in (('ZORTRAX_FAN_UPPER','upper'),('ZORTRAX_FAN_LOWER','lower')):
            h=FanHarness();h.run(command)
            self.assertTrue(h.fans.test[which]);self.assertEqual(h.fans.state,'FAN_TEST')
            self.assertEqual(h.p.view(h.now)['owner'],'m300_fans')
            self.assertEqual(getattr(h,which).speed,OEM_DUTY)

    def test_fan_start_distinguishes_active_homing_from_released_fault_and_reopens(self):
        h = FanHarness()
        motion = dict(state='HOMING', busy=True, normal_control=True, ready=True)
        h.objects['m300_motion'] = NS(get_status=lambda now: motion)
        with self.assertRaisesRegex(native_gcode.CommandError, 'm300_motion owns resources'):
            h.run('ZORTRAX_FAN_TEST_START')
        self.assertIsNone(h.fans.test)
        motion.update(state='FAULT', busy=False)
        h.run('ZORTRAX_FAN_TEST_START')
        h.run('ZORTRAX_FAN_LOWER')
        h.p._tick(h.now)
        token = h.fans.token
        h.lines.clear()
        h.run('ZORTRAX_FAN_TEST_START')
        h.p._tick(h.now)
        self.assertTrue(any('prompt_begin ZORTRAX M300 - Fan test' in line for line in h.lines))
        self.assertEqual(h.fans.token, token)
        self.assertEqual(h.lower.speed, OEM_DUTY)
        h.run('ZORTRAX_FAN_TEST_END')
        h.p._tick(h.now)
        self.assertIsNone(h.fans.test)
        self.assertEqual(h.lower.speed, 0.)
        self.assertEqual(h.lines[-1], '// action:prompt_end')
        h.assert_restored(self)

    def test_native_hotend_thermostat_is_a_floor_at_entry_and_every_toggle(self):
        for measured,target in ((51.,0.),(25.,230.),(float('nan'),0.),(0.,0.)):
            h=FanHarness();h.hotend.temperature=measured;h.hotend.target=target
            h.run('ZORTRAX_FAN_TEST_START')
            self.assertEqual(h.upper.speed,1.)
            for _ in range(2):
                h.action('TOGGLE_UPPER');self.assertEqual(h.upper.speed,1.)
            view=h.p.view(h.now)
            self.assertIn('(Cooling)',view['message'])
            self.assertIn('Automatic upper-fan cooling',view['message'])
            h.run('ZORTRAX_FAN_TEST_END');h.assert_restored(self)

    def test_automatic_callbacks_cannot_lower_an_enabled_cold_test(self):
        h=FanHarness();h.run('ZORTRAX_FAN_UPPER')
        for _ in range(3):
            h.thermostat.last_speed=-1.;h.thermostat.callback(h.now)
            self.assertEqual(h.upper.speed,OEM_DUTY)
        h.hotend.temperature=55.;h.thermostat.callback(h.now)
        self.assertEqual(h.upper.speed,1.)
        h.hotend.temperature=25.;h.thermostat.callback(h.now)
        self.assertEqual(h.upper.speed,OEM_DUTY)

    def test_back_restores_current_thermostat_after_a_temperature_change(self):
        h=FanHarness();h.run('ZORTRAX_FAN_TEST_START');h.hotend.temperature=60.
        h.action('BACK');self.assertEqual(h.upper.speed,1.);h.assert_restored(self)

    def test_stale_and_duplicate_shared_clicks_cannot_toggle_a_new_phase(self):
        h=FanHarness();h.run('ZORTRAX_FAN_TEST_START');old=h.p.view(h.now)['view_id']
        h.p.action(old,'TOGGLE_UPPER')
        with self.assertRaisesRegex(native_gcode.CommandError,'expired'):
            h.p.action(old,'TOGGLE_UPPER')
        self.assertEqual(h.upper.speed,OEM_DUTY)
        h.action('BACK')
        with self.assertRaisesRegex(native_gcode.CommandError,'expired'):
            h.p.action(old,'TOGGLE_LOWER')
        h.assert_restored(self)

    def test_native_external_fan_heating_motion_and_resume_commands_are_locked_only_during_test(self):
        h=FanHarness();h.run('ZORTRAX_FAN_TEST_START')
        for cmd in ('M106 S120','M107','G1 E1','G28','RESUME','G92 Z0'):
            with self.subTest(cmd=cmd),self.assertRaisesRegex(native_gcode.CommandError,'owns'):
                h.run(cmd)
        with self.assertRaisesRegex(native_gcode.CommandError,'owns heaters'):h.hotend.set_temp(240.)
        h.action('BACK');h.assert_restored(self);h.run('M106 S100')
        self.assertAlmostEqual(h.lower.speed,100/255.)

    def test_other_service_start_is_refused_before_any_heating_or_movement(self):
        h=FanHarness();h.run('ZORTRAX_FAN_TEST_START')
        for cmd in ('ZORTRAX_HEAT','ZORTRAX_LOAD','ZORTRAX_PLATFORM_UP'):
            with self.assertRaisesRegex(native_gcode.CommandError,'owns'):
                h.run(cmd)
        self.assertEqual(h.hotend.target,0.);self.assertEqual(h.position,[150.,158.,5.,17.])

    def test_printing_paused_busy_queue_and_fileoutput_cannot_start_fan_test(self):
        for condition in ('printing','paused','queue','FILEOUTPUT','pending_fan'):
            h=FanHarness()
            if condition in ('printing','paused'):h.print_state=condition
            elif condition=='queue':h.busy_until=h.now+1.
            elif condition=='FILEOUTPUT':h.board.mcu.is_fileoutput=lambda:True
            else:h.lower.gcrq.rqueue.append((h.now+1.,.2))
            with self.assertRaises(native_gcode.CommandError):h.run('ZORTRAX_FAN_TEST_START')
            self.assertIsNone(h.fans.test);h.assert_restored(self)
            self.assertFalse(any(e[0]=='fan' for e in h.events))

    def test_no_restore_after_stale_or_protective_mcu_status(self):
        for condition in ('stale','forced','local'):
            h=FanHarness();h.lower.speed=.3;h.run('ZORTRAX_FAN_LOWER');h.events.clear()
            if condition=='stale':h.cooling['status_fresh']=False
            elif condition=='forced':h.cooling['forced_cooling']=True
            else:h.cooling['local_cooling']['mode_code']=2
            h.fans._tick(h.now)
            self.assertEqual(h.fans.state,'FAULT');h.assert_restored(self)
            self.assertFalse(any(e[0]=='fan' for e in h.events))

    def test_deadline_exit_is_bounded_and_restores_native_owners(self):
        h=FanHarness();h.run('ZORTRAX_FAN_LOWER');h.now+=h.m.timeout+1.
        h.fans._tick(h.now)
        self.assertEqual(h.fans.state,'CANCELLED');self.assertEqual(h.lower.speed,0.)
        h.assert_restored(self)

    def test_restart_revokes_session_without_replaying_saved_fan_duty(self):
        h=FanHarness();h.lower.speed=.3;h.run('ZORTRAX_FAN_LOWER');h.events.clear()
        h.fans.invalidate()
        self.assertFalse(h.fans.ready);self.assertIsNone(h.fans.test);h.assert_restored(self)
        self.assertTrue(all(e[2]==1. for e in h.events if e[0]=='fan'))

    def test_external_heater_off_exits_the_test_without_rearming_heat(self):
        h=FanHarness();h.run('ZORTRAX_FAN_TEST_START');h.hotend.set_temp(0.)
        self.assertEqual(h.fans.state,'CANCELLED');self.assertEqual(h.hotend.target,0.)
        h.assert_restored(self)

    def test_one_mcu_snapshot_per_status_and_no_idle_timer_work(self):
        h=FanHarness();h.board_reads=0
        status=h.fans.get_status(h.now)
        self.assertEqual(h.board_reads,1)
        self.assertFalse(status['busy']);self.assertEqual(h.fans._tick(h.now),h.reactor.NEVER)
        self.assertEqual(h.board_reads,1)

    def test_faulting_native_output_releases_locks_and_requests_shutdown(self):
        h=FanHarness();h.run('ZORTRAX_FAN_TEST_START')
        def fail(value):raise native_gcode.CommandError('physical queue failure')
        h.fans._print_async=fail
        with self.assertRaisesRegex(native_gcode.CommandError,'physical queue failure'):h.action('TOGGLE_LOWER')
        self.assertTrue(h.shutdown);h.assert_restored(self)

    def test_actual_fan_failure_reason_survives_lifecycle_and_is_shown_in_both_views(self):
        h=FanHarness();h.run('ZORTRAX_FAN_TEST_START')
        h.fans._failed('queue failure');h.fans.invalidate();h.p.invalidate()
        view=h.p.view(h.now,owner_override='m300_fans')
        self.assertEqual(view['state'],'FAULT');self.assertIn('queue failure',view['message'])
        self.assertEqual(view['actions'],[])
        self.assertTrue(any('prompt_text Fan output failure: queue failure' in line for line in h.lines))
        self.assertIn('queue failure',' '.join(label for label,_ in h.p.rows(h.now)[1]))

    def test_actual_maintenance_fault_reason_survives_shutdown_notification(self):
        h=FanHarness();h.run('ZORTRAX_HEAT');h.m._fault('heater feedback failed')
        h.m._stop_lifecycle();h.p.invalidate()
        self.assertEqual(h.m.reason,'heater feedback failed')
        self.assertTrue(any('heater feedback failed' in line for line in h.lines))


class MaintenancePresentationTests(unittest.TestCase):
    def test_all_original_fan_menu_frames_and_selected_actions_match(self):
        for record in REFERENCE['frames']:
            wire=fan_frame('(Enabled)' if record['upper'] else '(Disabled)',
                '(Enabled)' if record['lower'] else '(Disabled)','',record['selected'],test_display.renderer.Frame)
            self.assertEqual(wire,zlib.decompress(base64.b64decode(record['wire_zlib_b64'])))
            self.assertEqual(hashlib.sha256(wire).hexdigest(),record['sha256'])

    def test_cold_fan_menu_labels_and_fluidd_buttons_are_identical(self):
        h=FanHarness();h.run('ZORTRAX_FAN_TEST_START')
        for verb in ('TOGGLE_UPPER','TOGGLE_LOWER','TOGGLE_UPPER','TOGGLE_LOWER'):
            h.action(verb);view=h.p.view(h.now);title,rows=h.p.rows(h.now)
            self.assertEqual(title,'Fan test');self.assertTrue(require_rows(rows))
            h.lines.clear();h.p._prompt(view)
            for label,_ in rows:self.assertTrue(any('prompt_button '+label+'|' in line for line in h.lines))
            self.assertEqual(view['message'],'\n'.join(label for label,_ in rows))

    def test_real_oled_fan_menu_renders_and_clicks_current_acknowledged_row(self):
        h=FanHarness();o,menu,ui,display,packet=physical_panel(h)
        h.run('ZORTRAX_FAN_TEST_START');h.p._tick(h.now)
        self.assertEqual(menu.page,'fan_test');o.selection=1;o._render(h.now);display.pump()
        packet(False);packet(False,1,1,1)
        self.assertEqual(h.upper.speed,OEM_DUTY);self.assertFalse(h.fans.test['lower'])
        h.p._tick(h.now);o._render(h.now);display.pump()
        self.assertEqual(o._render_wire,fan_frame('(Enabled)','(Disabled)','',1,test_display.renderer.Frame))
        o.selection=0;o._render(h.now);display.pump();packet(False,2,2,2)
        h.p._tick(h.now);self.assertEqual(menu.page,'maintenance');h.assert_restored(self)

    def test_leaving_fan_page_and_home_restore_requests(self):
        for destination in ('material','home'):
            h=FanHarness();o,menu,ui,display,packet=physical_panel(h)
            h.run('ZORTRAX_FAN_LOWER');h.p._tick(h.now)
            if destination=='home':menu.home()
            else:menu._navigate(destination)
            self.assertIsNone(h.fans.test);self.assertEqual(h.lower.speed,0.);h.assert_restored(self)

    def test_macro_platform_messages_match_maintenance_row_without_breaking_hold(self):
        for direction in ('UP','DOWN'):
            h=FanHarness();h.homed='z';o,menu,ui,display,packet=physical_panel(h)
            h.objects['m300_settings'] = NS(brightness_prompt=lambda keys:['M300_BRIGHTNESS led_brightness 14'])
            h.run('ZORTRAX_PLATFORM_'+direction);h.p._tick(h.now)
            view=h.p.view(h.now);label='Move the platform '+direction.lower()
            self.assertEqual(view['message'],label);self.assertEqual(menu.page,'maintenance')
            self.assertIn('// action:prompt_text '+label,h.lines)
            self.assertFalse(any('M300_BRIGHTNESS' in line for line in h.lines))
            self.assertIn(label,[row[0] for row in menu.rows(h.now)[1]])
            h.until(h.m,'COMPLETE');h.assert_restored(self)

    def test_heat_threshold_confirmation_cancel_and_return_match_original_traces(self):
        h=FanHarness();o,menu,ui,display,packet=physical_panel(h)
        original=next(r for r in REFERENCE['heat'] if r['accept'])
        h.run('ZORTRAX_HEAT');self.assertEqual(h.hotend.target,original['events'][0]['target'])
        h.hotend.temperature=257.9;h.step();self.assertEqual(h.m.state,'HEATING')
        h.hotend.temperature=258.;h.step();self.assertEqual(h.m.state,'WAIT_CONFIRM')
        view=h.p.view(h.now);self.assertEqual(view['message'],view['leveling_screen']['text'])
        h.action('CONFIRM');h.p._tick(h.now)
        self.assertEqual(h.hotend.target,0.);self.assertEqual(menu.page,'maintenance')
        h.assert_restored(self)

    def test_maintenance_fan_macros_belong_to_the_normal_zortrax_group(self):
        for name in ('ZORTRAX_FAN_TEST_START','ZORTRAX_FAN_UPPER','ZORTRAX_FAN_LOWER','ZORTRAX_FAN_TEST_END'):
            self.assertEqual(category(name),'ZORTRAX M300')
        menu,_=menu_fixture();menu.page='maintenance'
        self.assertIn(('Fan test',('native_gcode','ZORTRAX_FAN_TEST_START')),menu.rows(1.)[1])

    def test_original_hold_only_dispatches_up_down_while_pressed_in_maintenance(self):
        active=[c for c in REFERENCE['platform'] if c['motor_calls']]
        self.assertEqual([(c['selected'],c['motor_calls']) for c in active],
            [(4,['0x8015354']),(5,['0x8015324'])])
        self.assertTrue(all(c['pressed'] and c['menu']=='0x20000680' for c in active))


if __name__=='__main__':unittest.main()
