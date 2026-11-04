"""Full OEM manual sessions with the pinned native dispatcher and GCodeMove.

Only the heater, clock and physical move/drain boundaries are modeled. These
tests do not claim a physical extrusion length or a hardware panel acceptance.
"""
import copy
from collections import defaultdict, deque
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

import test_display
from tests.reference import native_gcode, native_gcode_move
from tests.reference.native_pause_resume import PauseResume
from test_macro_dispatch import templates, ENV
from test_native_menu import fixture as menu_fixture
from test_normal_operations import motion_fixture
from payload.m300_filament import M300Filament
from payload.m300_native_maintenance import M300NativeMaintenance
from payload.m300_procedures import M300Procedures
from payload.m300_menu_ui import M300MenuUI
from payload.m300_oled import M300OLED
from payload.m300_oem_graphics import OEMGraphics, choose_icon
from payload.m300_leveling_oem import render
from payload.m300_ui_m11_state import require_rows, MenuHistory
from setup_fluidd import merge_groups
import m300_profile


class Mutex:
    def __init__(self):self.depth=0
    def test(self):return bool(self.depth)
    def __enter__(self):self.depth+=1
    def __exit__(self,*args):self.depth-=1


class Heater:
    min_temp,min_extrude_temp,max_temp=0.,170.,300.
    def __init__(self):self.target,self.temperature=0.,25.
    @property
    def can_extrude(self):return self.temperature>=self.min_extrude_temp
    def set_temp(self,value):self.target=value
    def get_temp(self,now):return self.temperature,self.target


class Harness:
    def __init__(self):
        self.now,self.shutdown=1.,False
        self.events,self.callbacks,self.lines=[],[],[]
        self.handlers=defaultdict(list)
        self.objects={}
        self.position=[150.,158.,5.,17.]
        self.homed=''
        self.busy_until=0.
        self.print_state='standby'
        self.file_position=123
        self.language='EN'
        self.reactor=NS(monotonic=lambda:self.now,NOW=0.,NEVER=1.e30,
            register_timer=lambda cb:cb,update_timer=lambda *args:self.events.append(('timer',args)),
            register_callback=self.callbacks.append,register_async_callback=self.callbacks.append,
            mutex=Mutex)
        self.printer=NS(get_reactor=lambda:self.reactor,get_start_args=lambda:{},
            register_event_handler=lambda event,cb:self.handlers[event].append(cb),
            lookup_object=lambda name,default=None:self.objects.get(name,default),
            load_object=lambda config,name:self.objects[name],
            command_error=native_gcode.CommandError,config_error=RuntimeError,
            is_shutdown=lambda:self.shutdown,send_event=self.emit,
            invoke_async_shutdown=self.stop,invoke_shutdown=self.stop)
        self.config=NS(get_printer=lambda:self.printer,error=RuntimeError,
            getboolean=lambda name,default=False:True if name in ('qualified','filament_qualified') else default,
            getfloat=lambda name,default,**kw:default)
        self.gcode=native_gcode.GCodeDispatch(self.printer)
        self.gcode.register_output_handler(self.lines.append)
        for name in ('G28','M109','G4','M400','SET_STEPPER_ENABLE'):
            self.gcode.register_command(name,lambda cmd:None)
        self.hotend,self.bed=Heater(),Heater()
        self.board=NS(native_control=True,require_motion=lambda:None,require_heating=lambda:None,
            mcu=NS(is_fileoutput=lambda:False),get_mcu=lambda:NS(register_config_callback=lambda cb:None))
        self.hold_rail_offset = [0., 0., 0.]
        self.rails = [NS(get_name=lambda axis=axis: 'stepper_' + axis,
                         get_commanded_position=lambda i=i: self.position[i] + self.hold_rail_offset[i],
                         get_step_dist=lambda: .0025)
                      for i, axis in enumerate('xyz')]
        kin=NS(max_z_velocity=25.,get_status=lambda now:dict(
            homed_axes=self.homed,axis_minimum=[0.,0.,0.],axis_maximum=[305.,305.,315.]),
            get_steppers=lambda:self.rails,
            calc_position=lambda positions:[positions['stepper_' + axis] for axis in 'xyz'])
        self.toolhead=NS(get_position=lambda:self.position[:],move=self.move,
            manual_move=self.manual_move,drip_move=lambda *args:None,
            set_position=lambda position:setattr(self,'position',list(position)),
            flush_step_generation=lambda:None,
            get_kinematics=lambda:kin,get_extruder=lambda:NS(max_e_dist=50.),
            register_lookahead_callback=lambda cb:cb(self.now),get_last_move_time=lambda:self.busy_until,
            get_max_velocity=lambda:(300.,1000.),check_busy=lambda now:(self.busy_until,now,True))
        self.idle=NS(idle_timeout=600.)
        self.job=NS(board=self.board,toolhead=self.toolhead,hotend=self.hotend,bed=self.bed,
            idle=self.idle,fan=None,workflow_qualified=False,
            machine=NS(state='IDLE',active=False,token=1),
            _ops=[],_waiting=None,_executing=False,_cleanup_pending=False,_resume_checking=False,
            sd=NS(is_preparing=False,is_session_active=lambda:False),
            _bind_resources=lambda:None,_queue_drained=lambda now:now>=self.busy_until,
            _set_idle=lambda value:setattr(self.idle,'idle_timeout',value),
            _axis_bounds=lambda:([0.,0.,0.],[305.,305.,315.]),
            _homed=lambda:set(self.homed)>=set('xyz'),
            _temperatures=lambda now:dict(hotend=self.hotend.get_temp(now),bed=self.bed.get_temp(now)),
            _temperature=lambda name,heater,now:heater.get_temp(now),
            m04_service_busy=lambda:any(self.objects[name].is_busy() for name in ('m300_maintenance',)
                                       if name in self.objects),
            get_status=lambda now:dict(state='IDLE',busy=False))
        self.objects.update(gcode=self.gcode,toolhead=self.toolhead,m300_job=self.job,
            m300_mcu=self.board,print_stats=NS(get_status=lambda now:dict(state=self.print_state,filename='fixture.gcode')),
            webhooks=NS(register_endpoint=lambda *args:None),
            virtual_sdcard=NS(is_active=lambda:self.print_state=='printing',
                get_status=lambda now:dict(file_path='fixture.gcode',file_position=self.file_position),
                do_pause=lambda:self.native_print_state('paused'),
                do_resume=lambda:self.native_print_state('printing'),
                do_cancel=lambda:self.native_print_state('cancelled')),
            m300_menu_ui=NS(language=lambda:self.language))
        self.gmove=native_gcode_move.GCodeMove(self.config)
        self.job.gcode_move=self.gmove
        self.objects['gcode_move']=self.gmove
        self.pause=PauseResume(self.config)
        self.objects['pause_resume']=self.pause
        self.f=M300Filament(self.config)
        self.objects['m300_filament']=self.f
        self.m=M300NativeMaintenance(self.config)
        self.hold_actions = []
        self.hold_sample = None
        self.objects['m300_maintenance']=self.m
        self.p=M300Procedures(self.config)
        self.objects['m300_procedures']=self.p
        for name,body in templates().items():
            if name in ('ZORTRAX_LEVEL','ZORTRAX_HEAT','ZORTRAX_HOME_XY','ZORTRAX_HOME_ALL','ZORTRAX_PLATFORM_UP',
                        'ZORTRAX_PLATFORM_DOWN','ZORTRAX_LOAD','ZORTRAX_UNLOAD','ZORTRAX_CHANGE'):
                template=ENV.from_string(body)
                self.gcode.register_command(name,lambda cmd,t=template:self.gcode.run_script_from_command(
                    t.render(params=cmd.get_command_parameters())))
        self.emit('klippy:connect');self.emit('klippy:ready')
        self.m.panel_release = NS(arm_cmd=True,
            get_steppers=lambda:[self.rails[2]],
            stop=lambda:self.hold_actions.append('stop'), move=self.model_hold_move)
        self.native_move=self.toolhead.move
        self.native_heat=self.hotend.set_temp
        self.native_commands=dict(self.gcode.ready_gcode_handlers)
        self.events.clear();self.lines.clear()

    def model_hold_move(self, printer, toolhead, target, speed, press_id):
        self.hold_actions.append((tuple(target), speed, press_id))
        halt = [s.get_commanded_position() for s in self.rails] + target[3:]
        step = self.rails[2].get_step_dist()
        halt[2] += round((target[2] - halt[2]) / step) * step
        toolhead.drip_move(target, speed, None)
        if self.hold_sample is not None:
            halt[2] = self.hold_sample()
        toolhead.set_position(halt)

    def start_hold_worker(self):
        self.callbacks.pop(0)(self.now)

    def emit(self,event,*args):
        for cb in self.handlers[event]:cb(*args)
    def native_print_state(self,state):
        self.print_state=state
        self.events.append(('native_print',state))
    def stop(self,reason):
        self.shutdown=True
        self.events.append(('shutdown',reason))
    def move(self,position,speed):
        if not 0.<=position[2]<=315.:raise native_gcode.CommandError('native Z limit')
        if position[2]!=self.position[2] and 'z' not in self.homed:
            raise native_gcode.CommandError('Must home Z first')
        if position[3]!=self.position[3] and not self.hotend.can_extrude:
            raise native_gcode.CommandError('Extrude below minimum temp')
        duration=max(abs(a-b) for a,b in zip(position,self.position))/speed
        self.busy_until=max(self.now,self.busy_until)+duration
        self.position=list(position)
        self.events.append(('move',tuple(position),speed))
    def manual_move(self,position,speed):
        self.toolhead.move([old if new is None else new for new,old in zip(position,self.position)],speed)
        self.emit('toolhead:manual_move')
    def step(self,dt=.1):
        self.now+=dt
        self.f._watchdog(self.now);self.f._tick(self.now);self.m._tick(self.now)
        if not self.shutdown:self.p._tick(self.now)
    def until(self,obj,state,maximum=2000):
        for _ in range(maximum):
            if (obj.machine.state if obj is self.f else obj.state)==state:return
            if self.shutdown:break
            self.step()
        raise AssertionError((state,self.f.machine.state,self.m.state,self.events[-4:]))
    def heat(self,obj,state):
        self.hotend.temperature=self.hotend.target
        self.until(obj,state)
    def run(self,script):self.gcode.run_script_from_command(script)
    def assert_restored(self,test):
        test.assertEqual(self.toolhead.move,self.native_move)
        test.assertEqual(self.hotend.set_temp,self.native_heat)
        test.assertEqual(self.gmove.move_with_transform,self.native_move)
        for name,handler in self.native_commands.items():
            test.assertIs(self.gcode.ready_gcode_handlers[name],handler,name)
        test.assertEqual(self.idle.idle_timeout,600.)


class NativeMaterialTests(unittest.TestCase):
    def test_idle_uses_unchanged_native_bindings_and_needs_no_m02_qualification(self):
        h=Harness();h.assert_restored(self)
        self.assertFalse(h.job.workflow_qualified)
        self.assertTrue(h.f.ready and h.f.installed and h.m.ready)
        self.assertEqual(h.homed,'')

    def test_load_macro_heats_then_waits_for_insert_and_finishes_without_extra_purge(self):
        h=Harness();h.run('G91\nM83\nG92 E3\nM220 S87\nM221 S92')
        before=copy.deepcopy(h.gmove.get_status(h.now))
        h.run('ZORTRAX_LOAD')
        self.assertEqual(h.hotend.target,240.)
        h.heat(h.f,'WAIT_INSERT')
        self.assertFalse(any(e[0]=='move' for e in h.events))
        view=h.p.view(h.now);h.p.action(view['view_id'],'CONFIRM')
        h.until(h.f,'COMPLETE')
        self.assertEqual(h.position,[150.,158.,5.,147.])
        self.assertEqual(h.homed,'')
        self.assertEqual(h.hotend.target,0.)
        self.assertAlmostEqual(h.gmove._get_gcode_position()[3],before['gcode_position'].e)
        self.assertFalse(h.gmove.absolute_coord)
        self.assertFalse(h.gmove.allow_absolute_extrude)
        self.assertEqual(h.gmove.speed_factor,87/6000.)
        self.assertEqual(h.gmove.extrude_factor,.92)
        self.assertNotIn('M300_M03_SERVICE',h.gmove.saved_states)
        self.assertNotIn('WAIT_PURGE',[e['to'] for e in h.f.machine.snapshot()['history']][-2:])
        h.assert_restored(self)

    def test_unload_confirms_before_retracting_then_turns_heat_off(self):
        h=Harness();h.run('ZORTRAX_UNLOAD');h.heat(h.f,'WAIT_UNLOAD')
        self.assertEqual(h.position,[150.,158.,5.,17.])
        self.assertFalse(any(e[0]=='move' for e in h.events))
        self.assertEqual(h.hotend.target,240.)
        self.assertTrue(h.f.get_status(h.now)['can_confirm'])
        view=h.p.view(h.now);h.p.action(view['view_id'],'CONFIRM');h.until(h.f,'COMPLETE')
        self.assertEqual(h.position,[150.,158.,5.,-93.])
        self.assertEqual(h.hotend.target,0.)
        h.assert_restored(self)

    def test_native_printing_or_paused_rejects_material_and_maintenance_before_heat(self):
        for state in ('printing','paused'):
            for command in ('ZORTRAX_LOAD','ZORTRAX_UNLOAD','ZORTRAX_HEAT','ZORTRAX_PLATFORM_UP'):
                h=Harness();h.print_state=state;h.homed='z'
                with self.assertRaisesRegex(native_gcode.CommandError,'idle native print'):
                    h.run(command)
                self.assertEqual(h.hotend.target,0.)
                self.assertEqual(h.position,[150.,158.,5.,17.])
                h.assert_restored(self)

    def test_cancel_waits_for_native_queue_drain_and_never_issues_another_segment(self):
        h=Harness();h.run('ZORTRAX_LOAD');h.heat(h.f,'WAIT_INSERT')
        h.f.confirm(h.f.machine.token,h.f.machine.phase_id);h.step()
        self.assertEqual(h.position[3],22.)
        h.f.cancel();self.assertEqual(h.hotend.target,0.)
        h.step();self.assertEqual(h.f.machine.state,'CANCELLING')
        h.until(h.f,'CANCELLED')
        self.assertEqual(h.position[3],22.);h.assert_restored(self)

    def test_native_commands_and_direct_motion_cannot_bypass_material_owner(self):
        h=Harness();h.run('ZORTRAX_LOAD')
        for command in ('G28','G1 X1','G92 E0','RESTORE_GCODE_STATE NAME=foo',
                        'SET_GCODE_OFFSET Z=1','M109 S250'):
            with self.assertRaisesRegex(native_gcode.CommandError,'owns resources'):
                h.run(command)
        with self.assertRaisesRegex(native_gcode.CommandError,'external move'):
            h.toolhead.move([150.,158.,4.,17.],1.)
        with self.assertRaisesRegex(native_gcode.CommandError,'owns heaters'):
            h.hotend.set_temp(250.)
        h.f.cancel();h.until(h.f,'CANCELLED');h.assert_restored(self)
        h.run('SET_GCODE_OFFSET Z=1\nSAVE_GCODE_STATE NAME=after')
        self.assertEqual(h.gmove.homing_position[2],1.)

    def test_temperature_loss_faults_before_next_e_segment_and_cuts_heat(self):
        h=Harness();h.run('ZORTRAX_LOAD');h.heat(h.f,'WAIT_INSERT')
        h.f.confirm(h.f.machine.token,h.f.machine.phase_id)
        h.hotend.temperature=160.;h.step()
        self.assertTrue(h.shutdown);self.assertEqual(h.f.machine.state,'FAULT')
        self.assertEqual(h.hotend.target,0.)
        self.assertEqual(h.position[3],17.)

    def test_stale_shared_confirmation_cannot_advance_new_material_phase(self):
        h=Harness();h.run('ZORTRAX_LOAD');old=h.p.view(h.now)['view_id']
        h.heat(h.f,'WAIT_INSERT')
        with self.assertRaisesRegex(native_gcode.CommandError,'expired'):
            h.p.action(old,'CONFIRM')
        view=h.p.view(h.now);h.p.action(view['view_id'],'CONFIRM')
        with self.assertRaisesRegex(native_gcode.CommandError,'expired'):
            h.p.action(view['view_id'],'CONFIRM')
        h.until(h.f,'COMPLETE')

    def test_two_material_sessions_restore_exact_native_extended_handlers(self):
        h=Harness()
        for operation in ('LOAD','UNLOAD'):
            h.run('ZORTRAX_'+operation)
            h.heat(h.f,'WAIT_INSERT' if operation=='LOAD' else 'WAIT_UNLOAD')
            h.f.confirm(h.f.machine.token,h.f.machine.phase_id)
            h.until(h.f,'COMPLETE');h.assert_restored(self)
        self.assertEqual(h.position[3],37.)
        self.assertEqual(h.gmove._get_gcode_position()[3],17.)


class NativeMaintenanceTests(unittest.TestCase):
    def test_heat_macro_uses_original_260_258_boundary_and_confirmation_turns_off(self):
        h=Harness();h.run('ZORTRAX_HEAT')
        h.hotend.temperature=257.9;h.step();self.assertEqual(h.m.state,'HEATING')
        h.hotend.temperature=258.;h.step();self.assertEqual(h.m.state,'WAIT_CONFIRM')
        self.assertEqual(h.hotend.target,260.)
        view=h.p.view(h.now);h.p.action(view['view_id'],'CONFIRM')
        self.assertEqual(h.m.state,'COMPLETE');self.assertEqual(h.hotend.target,0.)
        self.assertEqual(h.position,[150.,158.,5.,17.]);h.assert_restored(self)

    def test_platform_macros_use_native_z_only_with_correct_up_down_sign(self):
        h=Harness();h.homed='z';h.run('G91\nM83\nG92 Z2')
        h.run('ZORTRAX_PLATFORM_UP DISTANCE=2');h.until(h.m,'COMPLETE')
        self.assertEqual(h.position,[150.,158.,3.,17.])
        h.run('ZORTRAX_PLATFORM_DOWN DISTANCE=3');h.until(h.m,'COMPLETE')
        self.assertEqual(h.position,[150.,158.,6.,17.])
        self.assertFalse(h.gmove.absolute_coord);self.assertFalse(h.gmove.allow_absolute_extrude)
        self.assertEqual(h.gmove.base_position[2],3.)
        h.assert_restored(self)

    def test_platform_move_within_native_range_drains_one_segment_at_a_time(self):
        for distance in (20, 100):
            with self.subTest(distance=distance):
                h = Harness()
                h.homed = 'z'
                h.position[2] = 7.
                h.m.timeout = 2.
                h.run('ZORTRAX_PLATFORM_DOWN DISTANCE=%d' % distance)
                h.until(h.m, 'COMPLETE')
                moves = [event[1] for event in h.events if event[0] == 'move']
                self.assertEqual(moves, [(150., 158., float(z), 17.)
                                         for z in range(8, 8 + distance)])
                h.assert_restored(self)

    def test_cancel_platform_move_stops_after_the_current_segment(self):
        h = Harness()
        h.homed = 'z'
        h.position[2] = 7.
        h.run('ZORTRAX_PLATFORM_DOWN DISTANCE=20')
        h.step()
        view = h.p.view(h.now)
        h.p.action(view['view_id'], 'CANCEL')
        h.until(h.m, 'CANCELLED')
        moves = [event[1] for event in h.events if event[0] == 'move']
        self.assertEqual(moves, [(150., 158., 8., 17.)])
        h.assert_restored(self)

    def test_platform_refuses_unhomed_and_out_of_bounds_before_acquiring_lease(self):
        for homed,z,command in (('',5.,'ZORTRAX_PLATFORM_UP'),
                                ('z',0.,'ZORTRAX_PLATFORM_UP'),
                                ('z',315.,'ZORTRAX_PLATFORM_DOWN'),
                                ('z',300.,'ZORTRAX_PLATFORM_DOWN DISTANCE=20'),
                                ('z',5.,'ZORTRAX_PLATFORM_DOWN DISTANCE=311')):
            h=Harness();h.homed=homed;h.position[2]=z
            with self.assertRaises(native_gcode.CommandError):h.run(command)
            self.assertFalse(any(e[0]=='move' for e in h.events));h.assert_restored(self)

    def test_stale_panel_and_lost_view_stop_before_the_hold_worker_runs(self):
        for kind in ('stale', 'lost_view'):
            h = Harness()
            h.homed = 'z'
            visible = [True]
            h.m.hold(1, 'view', h.now, lambda: visible[0], 1)
            h.step()
            if kind == 'stale':
                h.now += .8
            else:
                visible[0] = False
            h.start_hold_worker()
            h.until(h.m, 'CANCELLED')
            self.assertEqual(h.hold_actions, [])
            self.assertEqual(h.position[2], 5.)
            h.assert_restored(self)

    def test_held_moves_clip_to_native_speed_and_travel_limits(self):
        for direction, limit in ((-1, 0.), (1, 315.)):
            with self.subTest(direction=direction):
                h = Harness()
                h.homed = 'z'
                h.position[2] = limit - direction * .25
                h.toolhead.get_kinematics().max_z_velocity = .5
                h.m.hold(direction, 'view', h.now, lambda: True, 8)
                h.step()
                h.start_hold_worker()
                self.assertAlmostEqual(h.position[2], limit)
                self.assertEqual(h.hold_actions, [((150., 158., limit, 17.), .5, 8)])
                h.assert_restored(self)

    def test_held_moves_use_rail_phase_at_both_limits_and_preserve_logical_xy(self):
        for direction, limit, step in ((-1, 0., .0025), (1, 315., .0025),
                                       (-1, 0., .00125), (1, 315., .00125)):
            with self.subTest(direction=direction, step=step):
                h = Harness()
                h.homed = 'xyz'
                h.position = [170., 161.43, limit - direction * 2. * step, 17.]
                h.hold_rail_offset = [-.0005, .000625, direction * .32 * step]
                h.rails[2].get_step_dist = lambda: step
                h.m.hold(direction, 'view', h.now, lambda: True, 8)
                h.step()
                h.start_hold_worker()
                self.assertFalse(h.shutdown)
                self.assertEqual(h.m.state, 'CANCELLED')
                self.assertEqual(h.position[:2], [170., 161.43])
                self.assertEqual(h.position[3], 17.)
                self.assertAlmostEqual(h.position[2], limit - direction * .68 * step)
                self.assertEqual(h.hold_actions[0][1], 10.)
                h.assert_restored(self)

    def test_release_during_initial_step_flush_cannot_start_motion(self):
        h = Harness()
        h.homed = 'z'
        h.toolhead.flush_step_generation = lambda: h.m.cancel('panel released')
        h.m.hold(1, 'view', h.now, lambda: True, 8)
        h.step()
        h.start_hold_worker()
        h.until(h.m, 'CANCELLED')
        self.assertEqual(h.hold_actions, ['stop'])
        self.assertEqual(h.position[2], 5.)
        h.assert_restored(self)

    def test_held_move_refuses_halt_outside_the_planned_step_range(self):
        h = Harness()
        h.homed = 'xyz'
        h.hold_sample = lambda: 315.0025
        h.m.hold(1, 'view', h.now, lambda: True, 8)
        h.step()
        h.start_hold_worker()
        self.assertTrue(h.shutdown)
        self.assertEqual(h.m.state, 'FAULT')
        self.assertIn(('shutdown', 'M300 maintenance: native probe returned an invalid position'), h.events)

    def test_old_mcu_has_no_unprotected_panel_move_fallback(self):
        h = Harness()
        h.homed = 'z'
        h.m.panel_release.arm_cmd = None
        with self.assertRaisesRegex(native_gcode.CommandError, 'local panel release'):
            h.m.hold(1, 'view', h.now, lambda: True, 1)
        self.assertEqual(h.position[2], 5.)
        h.assert_restored(self)

    def test_extended_handlers_restore_after_calibration_using_real_native_dispatcher(self):
        from test_native_leveling import Harness as LevelHarness
        h=Harness();cal=LevelHarness().c
        cal.gcode=h.gcode;cal.printer.command_error=native_gcode.CommandError
        cal._install_ownership()
        with self.assertRaisesRegex(native_gcode.CommandError,'owns resources'):
            h.run('SET_GCODE_OFFSET Z=1')
        cal._release_ownership()
        for name,handler in h.native_commands.items():
            self.assertIs(h.gcode.ready_gcode_handlers[name],handler,name)
        h.run('SET_GCODE_OFFSET Z=1');self.assertEqual(h.gmove.homing_position[2],1.)


class OEMMenuIntegrationTests(unittest.TestCase):
    def test_exact_oem_submenu_order_and_available_native_actions(self):
        menu,_=menu_fixture();menu.page='zortrax'
        self.assertEqual([name for name,_ in menu.rows(1.)[1]],
            ['Back','Models','Maintenance','Homing XY','Homing ALL','Material','Settings','Information'])
        menu.page='maintenance';rows=menu.rows(1.)[1]
        self.assertEqual([name for name,_ in rows],['Back','Autocalibration','Heat the extruder',
            'Move the platform up','Move the platform down','Fan test'])
        self.assertTrue(require_rows(rows))
        menu.page='material';rows=menu.rows(1.)[1]
        self.assertEqual([name for name,_ in rows],['Back','Unload the material','Load the material'])
        self.assertTrue(require_rows(rows))

    def test_oled_actions_invoke_the_same_macros_as_fluidd_through_native_lexer(self):
        for page,index,operation in (('maintenance',1,'LEVEL'),('maintenance',2,'HOTEND'),
                                     ('material',1,'UNLOAD'),('material',2,'LOAD')):
            h=Harness();calls=[]
            if operation=='LEVEL':
                h.objects['m300_calibration']=NS(start=lambda temp:calls.append(temp))
            menu,_=menu_fixture();menu.page=page;menu.gcode=h.gcode;menu.reactor=h.reactor
            action=menu.rows(h.now)[1][index][1];menu.select(action,h.now)
            h.callbacks.pop()(h.now)
            if operation=='LEVEL':self.assertEqual(calls,[260.])
            elif operation=='HOTEND':self.assertEqual((h.m.operation,h.hotend.target),('HOTEND',260.))
            else:self.assertEqual((h.f.machine.mode,h.hotend.target),(operation,240.))

    def test_selected_rows_use_original_menu_sprites(self):
        expected={'ZORTRAX_LEVEL':'0x0801ca28','ZORTRAX_HEAT':'0x0801c2b8',
                  'ZORTRAX_UNLOAD':'0x0801cfb0','ZORTRAX_LOAD':'0x0801d0b8'}
        for script,icon in expected.items():
            self.assertEqual(choose_icon(rows=[('',('native_gcode',script))]),icon)
        for direction,icon in ((-1,'0x0801cb24'),(1,'0x0801cc24')):
            self.assertEqual(choose_icon(rows=[('',('platform_hold',direction))]),icon)

    def test_main_menu_uses_two_distinct_project_sprites(self):
        h = Harness()
        oled, menu, ui, _, _ = physical_panel(h)
        menu.page = 'main'
        frames = []
        for label, icon, expected_width in (('Klipper', 'project-klipper', 62),
                                            ('Zortrax M300', 'project-zortrax', 50)):
            _, rows = oled._rows(h.now)
            oled.selection = next(i for i, row in enumerate(rows) if row[0] == label)
            oled._render(h.now)
            self.assertEqual(ui.last_sprite, icon)
            width, height, pixels = ui.oem_sprites.get(icon)
            self.assertEqual((width, height, len(pixels)), (expected_width, 50, expected_width * 25))
            self.assertLessEqual(set(pixels), {0x00, 0x0F, 0xF0, 0xFF})
            self.assertTrue(any(pixels[:width // 2]))
            self.assertTrue(any(pixels[-width // 2:]))
            frames.append(pixels)
        self.assertNotEqual(*frames)
        oled.selection = 0
        oled._render(h.now)
        self.assertIsNone(ui.last_sprite)

    def test_fluidd_groups_procedure_macros_without_unhiding_user_choices(self):
        names = ['ZORTRAX_' + name for name in (
            'LEVEL', 'HEAT', 'HOME_XY', 'HOME_ALL', 'PLATFORM_UP', 'PLATFORM_DOWN', 'LOAD', 'UNLOAD')]
        before=dict(categories=[dict(id='tests',name='TEST M300')],
                    stored=[dict(name='ZORTRAX_LOAD',categoryId='tests',visible=False)])
        after,assigned=merge_groups(before,names)
        self.assertEqual(set(assigned.values()),{'ZORTRAX M300'})
        self.assertFalse(after['stored'][0]['visible'])
        self.assertEqual(merge_groups(after,names)[0],after)

    def test_native_oem_dialogs_use_shared_english_text_for_every_legacy_language(self):
        for language in ('EN','PL','FR','DE','ES'):
            for owner,operation,state in (('m300_maintenance','HOTEND','WAIT_CONFIRM'),
                    ('m300_filament','LOAD','WAIT_INSERT'),('m300_filament','LOAD','LOADING'),
                    ('m300_filament','UNLOAD','UNLOADING'),('m300_filament','UNLOAD','WAIT_UNLOAD')):
                h=Harness();h.language=language
                status=dict(state=state,operation=operation,native_control=True,busy=True,ready=True,
                            session_token=3,phase_id=4,can_confirm=True,can_cancel=True)
                h.objects[owner]=NS(get_status=lambda now:status)
                view=h.p.view(h.now);h.lines.clear();h.p._prompt(view)
                visible=[line.removeprefix('// action:prompt_text ') for line in h.lines
                         if line.startswith('// action:prompt_text ')]
                self.assertEqual(visible,view['leveling_screen']['text'].split('\n'))
                self.assertFalse(any('Session ' in line or state+':' in line for line in visible))
                self.assertEqual(len(render(view['leveling_screen'],OEMGraphics(),test_display.renderer.Frame)),8192)

    def test_native_profiles_enable_only_manual_services_and_preserve_calibration(self):
        source='''[m300_job]
workflow_qualified: False
[m300_filament]
filament_qualified: False
load_length: 137
unload_speed: 2.7
[m300_maintenance]
qualified: False
jog_speed: 2
[extruder]
rotation_distance: 26.133
[stepper_z]
position_max: 315
#*# <--- SAVE_CONFIG --->
#*# pid_Kp = 15.152
'''
        new=m300_profile.convert_text(source)
        for kept in ('workflow_qualified: False','load_length: 137','unload_speed: 2.7',
                     'jog_speed: 2','rotation_distance: 26.133','position_max: 315',
                     '#*# pid_Kp = 15.152'):
            self.assertIn(kept,new)
        self.assertIn('filament_qualified: True',new)
        self.assertIn('[m300_maintenance]\nqualified: True',new)
        self.assertEqual(m300_profile.convert_text(new),new)


def physical_panel(h):
    display=test_display.Harness()
    o=M300OLED.__new__(M300OLED)
    o.printer=h.printer;o.reactor=h.reactor;o.stream=display.stream
    o.generation=1;o._input_epoch=0;o.page='m04';o.selection=3;o.message=None
    o.connected=o.fast=True;o._user_refresh_pending=False
    o._render_key=o._render_wire=o._presented_context=o._presented_actions=None
    o.job_token=o.cancel_token=o.filament_token=o.filament_phase_id=o.filament_cancel_token=None
    o.render_count=0;o.render_max_ms=0.;o.render_at=0.;o.timer='oled'
    o.encoder=test_display.transport.EncoderSnapshots(4,validated=True)
    menu,_=menu_fixture();menu.page='maintenance';menu.printer=h.printer
    menu.job=h.job;menu.maintenance=h.m;menu.reactor=h.reactor;menu.gcode=h.gcode
    ui=M300MenuUI.__new__(M300MenuUI)
    ui.menu=menu;ui.oled=o;ui.printer=h.printer;ui.procedures=h.p
    ui.language=lambda:h.language;ui._leveling_frames=deque(maxlen=16)
    ui.oem_sprites=OEMGraphics();ui.history=MenuHistory(10)
    ui.row_pixels=216;ui.scroll_delay=1.25;ui.scroll_interval=.2
    h.objects.update(m300_oled=o,m300_menu=menu,m300_menu_ui=ui)
    sequence=[0]
    def packet(pressed,presses=0,releases=0,shorts=0,longs=0):
        h.now+=.1;sequence[0]+=1
        o._panel(dict(sequence=sequence[0],position=0,nav_position=0,invalid=0,
            pressed=pressed,presses=presses,releases=releases,shorts=shorts,longs=longs,
            **{'#receive_time':h.now}))
        h.callbacks.pop(0)(h.now)
    o._render(h.now)
    return o,menu,ui,display,packet


class PhysicalPanelDispatchTests(unittest.TestCase):
    def test_homing_macros_and_oled_rows_share_native_progress(self):
        for axes, label, command, g28 in (
                ('xy', 'Homing XY', 'ZORTRAX_HOME_XY', 'G28 X Y'),
                ('xyz', 'Homing ALL', 'ZORTRAX_HOME_ALL', 'G28')):
            with self.subTest(axes=axes):
                h = Harness()
                oled, menu, ui, _, _ = physical_panel(h)
                motion = motion_fixture()
                motion.printer = h.printer
                h.objects['m300_motion'] = motion
                h.objects['m300_settings'] = NS(brightness_prompt=lambda keys: [
                    'M300_BRIGHTNESS %s 14' % key for key in keys])
                native_home = motion.native_G28
                commands = []

                def g28_handler(gcmd):
                    commands.append(gcmd.get_commandline())
                    motion.home(axes=axes)

                def observe(params):
                    if list(params) == ['Y']:
                        h.p._tick(h.now)
                        self.assertEqual((menu.page, oled.page), ('procedure', 'm04'))
                        self.assertEqual(h.p.view(h.now)['message'], 'Homing Y')
                        self.assertIn('// action:prompt_begin ZORTRAX M300 - ' + label, h.lines)
                        self.assertIn('// action:prompt_text M300_HOMING_ACTIVE', h.lines)
                        self.assertIn('// action:prompt_text Homing Y', h.lines)
                        self.assertFalse(any('M300_BRIGHTNESS' in line for line in h.lines))
                        self.assertEqual(h.p.rows(h.now)[1][1], ('Homing Y', None))
                        oled._render(h.now)
                        before = oled._render_wire
                        oled._render(h.now + .5)
                        self.assertEqual(ui.last_sprite, '0x0801c2b8')
                        self.assertNotEqual(before, oled._render_wire)
                    native_home(params)

                motion.native_G28 = observe
                h.gcode.register_command('G28', None)
                h.gcode.register_command('G28', g28_handler)
                menu.page = 'zortrax'
                _, rows = menu.rows(h.now)
                selected = next(i for i, row in enumerate(rows) if row[0] == label)
                action = rows[selected][1]
                self.assertEqual(action, ('native_gcode', command))
                self.assertEqual(ui.get_oem_sprite('m04', rows, selected, h.now),
                                 ui.get_oem_sprite('m04', rows, selected, h.now + .5))
                if axes == 'xy':
                    menu.select(action, h.now)
                    h.callbacks.pop()(h.now)
                else:
                    h.run(command)
                h.p._tick(h.now)
                self.assertEqual(commands, [g28])
                self.assertEqual((menu.page, oled.page), ('zortrax', 'm04'))
                self.assertEqual(h.lines[-1], '// action:prompt_end')
                h.print_state = 'paused'
                with self.assertRaisesRegex(native_gcode.CommandError, 'requires an idle'):
                    h.run(command)
                self.assertEqual(commands, [g28])

    def test_platform_hold_uses_oled_without_opening_fluidd_even_on_shutdown(self):
        h = Harness()
        h.homed = 'z'
        oled, menu, _, display, packet = physical_panel(h)
        display.pump()
        packet(False)
        packet(False)
        packet(True, 1)
        self.assertEqual(h.m.state, 'PLATFORM_HOLD')
        h.objects['m300_settings'] = NS(brightness_prompt=lambda keys:['M300_BRIGHTNESS led_brightness 14'])
        h.lines.clear()
        h.p._tick(h.now)
        h.run('ZORTRAX_PROCEDURE_SHOW')
        self.assertFalse(any('action:prompt_begin' in line for line in h.lines))
        self.assertEqual((menu.page, oled.page), ('maintenance', 'm04'))
        h.m._fault('Native position failed')
        h.emit('klippy:shutdown')
        self.assertFalse(any('action:prompt_begin' in line for line in h.lines))
        self.assertIn('// action:prompt_end', h.lines)

    def test_real_oled_hold_requires_acknowledged_row_and_complete_press_release_gesture(self):
        h=Harness();h.homed='z';o,menu,ui,display,packet=physical_panel(h)
        packet(False);packet(False)
        packet(True,1)
        self.assertEqual(h.m.state,'IDLE')
        packet(False,1,1,1)
        display.pump();packet(False,1,1,1)
        packet(True,2,1,1)
        self.assertEqual(h.m.state,'PLATFORM_HOLD')
        h.step()
        def release():
            packet(True, 2, 1, 1, 1)
            self.assertEqual((menu.page, o.page), ('maintenance', 'm04'))
            packet(False, 2, 2, 1, 1)
            self.assertEqual(h.m.state, 'CANCELLING')
            return 4.75
        h.hold_sample = release
        h.start_hold_worker()
        self.assertEqual(h.position[2], 4.75)
        self.assertEqual(h.hold_actions, [((150., 158., 0., 17.), 10., 2), 'stop'])
        h.assert_restored(self)

    def test_both_oled_directions_reconcile_actual_position_after_release(self):
        for row, direction, limit in ((3, -1, 0.), (4, 1, 315.)):
            with self.subTest(direction=direction):
                h = Harness()
                h.homed = 'z'
                oled, _, _, display, packet = physical_panel(h)
                oled.selection = row
                oled._render(h.now)
                display.pump()
                packet(False)
                packet(False)
                packet(True, 1)
                h.step()
                stopped = 5. + direction * .25
                def release():
                    for command in ('G4 P100', 'M400', 'SET_STEPPER_ENABLE STEPPER=stepper_z ENABLE=0'):
                        with self.assertRaisesRegex(native_gcode.CommandError, 'owns resources'):
                            h.run(command)
                    for _ in range(12):
                        packet(True, 1)
                        h.step(.05)
                        self.assertEqual(h.m.state, 'PLATFORM_HOLD')
                    packet(False, 1, 1, 1)
                    return stopped
                h.hold_sample = release
                h.start_hold_worker()
                self.assertEqual(h.m.state, 'CANCELLED')
                self.assertEqual(h.position[2], stopped)
                self.assertEqual(h.hold_actions, [((150., 158., limit, 17.), 10., 1), 'stop'])
                h.assert_restored(self)

    def test_coalesced_release_and_repress_stops_without_restarting(self):
        h = Harness()
        h.homed = 'z'
        _, _, _, display, packet = physical_panel(h)
        display.pump()
        packet(False)
        packet(False)
        packet(True, 1)
        h.step(.05)
        def release():
            packet(True, 2, 1, 1)
            self.assertEqual(h.m.state, 'CANCELLING')
            return 4.75
        h.hold_sample = release
        h.start_hold_worker()
        packet(True, 2, 1, 1)
        self.assertEqual(h.m.state, 'CANCELLED')
        self.assertEqual(h.position[2], 4.75)
        self.assertEqual(h.hold_actions, [((150., 158., 0., 17.), 10., 1), 'stop'])
        h.assert_restored(self)

    def test_selection_change_between_receipt_and_callback_cannot_arm_new_row(self):
        h=Harness();h.homed='z';o,menu,ui,display,packet=physical_panel(h)
        display.pump();packet(False);packet(False)
        h.now+=.1
        o._panel(dict(sequence=3,position=0,nav_position=0,invalid=0,pressed=True,
            presses=1,releases=0,shorts=0,longs=0,**{'#receive_time':h.now}))
        o.selection=4
        h.callbacks.pop()(h.now)
        self.assertEqual(h.m.state,'IDLE')
        self.assertEqual(h.position[2],5.)

    def test_display_wake_gesture_cannot_start_an_unseen_platform_move(self):
        h=Harness();h.homed='z';o,menu,ui,display,packet=physical_panel(h)
        display.pump();packet(False);packet(False)
        h.objects['m300_display']=NS(_consume_gesture=True,phase='IDLE',_presentation_wait=False)
        packet(True,1);h.step()
        self.assertEqual(h.m.state,'IDLE')
        self.assertEqual(h.position[2],5.)

    def test_external_heat_load_and_unload_share_modal_oled_and_return_to_submenu(self):
        for command,owner,waiting,page in (('ZORTRAX_HEAT','m','WAIT_CONFIRM','maintenance'),
                   ('ZORTRAX_LOAD','f','WAIT_INSERT','material'),
                   ('ZORTRAX_UNLOAD','f','WAIT_UNLOAD','material')):
            h=Harness();o,menu,ui,display,packet=physical_panel(h)
            h.run(command);h.p._tick(h.now)
            self.assertEqual(menu.page,'procedure')
            service=getattr(h,owner);h.heat(service,waiting)
            o._render(h.now);display.pump()
            packet(False);packet(False,1,1,1)
            h.until(service,'COMPLETE');h.p._tick(h.now)
            self.assertEqual(menu.page,page)
            self.assertEqual(o.page,'m04');self.assertEqual(h.hotend.target,0.)
            self.assertEqual(h.lines[-1],'// action:prompt_end')
            packet(False, 1, 1, 1)  # Refresh telemetry after simulated extrusion.
            for clicks, expected in ((2, 'zortrax'), (3, 'main'), (4, 'status')):
                o._render(h.now);display.pump()
                packet(False, clicks, clicks, clicks)
                self.assertEqual(o.page if expected == 'status' else menu.page, expected)


if __name__=='__main__':unittest.main()
