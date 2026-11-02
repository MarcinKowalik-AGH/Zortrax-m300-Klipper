"""Native M07 with the pinned HomingMove and modeled contact/heater boundaries.

These tests exercise complete sessions, not physical printer acceptance.
"""
import copy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import test_display
from payload.m300_calibration import M300Calibration
from payload.m300_leveling_state import LevelingState, validate_observation
from payload.m300_oem_graphics import choose_icon
from payload.m300_procedures import M300Procedures
from payload.m300_menu_ui import M300MenuUI
import m300_profile

spec = importlib.util.spec_from_file_location('payload.homing',
    Path(__file__).parent / 'reference/native_homing.py')
homing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(homing)


class Stepper:
    def __init__(self, scale=400):
        self.scale, self.actual, self.offset = scale, 2000, 0.
    def get_name(self): return 'stepper_z'
    def get_step_dist(self): return 1. / self.scale
    def get_mcu_position(self, commanded=None):
        return self.actual if commanded is None else round((commanded-self.offset)*self.scale)
    def mcu_to_commanded_position(self, position): return position/self.scale+self.offset
    def get_past_mcu_position(self, when): return self.actual
    def calc_position_from_coord(self, coord): return coord[2]
    def get_commanded_position(self): return self.mcu_to_commanded_position(self.actual)


class Heater:
    def __init__(self): self.target, self.temperature = 0., 25.


class Harness:
    def __init__(self, scale=400, margin=1.):
        self.now, self.shutdown, self.events = 1., False, []
        self.position = [150., 158., 5., 17.]
        self.stepper = Stepper(scale)
        self.stepper.actual = 5 * scale
        self.hotend, self.bed = Heater(), Heater()
        for heater in (self.hotend, self.bed):
            heater.set_temp = lambda v, h=heater: setattr(h, 'target', v)
        self.level, self.triggered, self.trigger_time = False, True, 0.
        self.surface = lambda xy: -1./scale
        self.no_contact = self.no_release = False
        self.reclose_after_edge = self.stuck_after_tail = False
        self.release_target = None
        self.on_wait = None
        self.on_drip = None
        self.endstop = NS(get_steppers=lambda: [self.stepper],
            query_endstop=self.query, home_start=self.home_start,
            home_wait=lambda now: self.trigger_time)
        self.kin = NS(get_status=lambda now: {'homed_axes':'xyz'},
            get_steppers=lambda: [self.stepper],
            calc_position=lambda spos: self.position[:2]+[spos['stepper_z']])
        self.toolhead = NS(get_position=lambda: self.position[:],
            move=self.move, drip_move=self.drip, set_position=self.set_position,
            get_last_move_time=lambda: self.now, check_busy=lambda now: (self.now,self.now,True),
            get_kinematics=lambda: self.kin, flush_step_generation=lambda: None,
            dwell=lambda delay: self.events.append(('dwell', delay)), wait_moves=self.wait_moves)
        self.commands = {'G1': lambda cmd: self.move([1.,2.,3.,17.],1.),
                         'G28': lambda cmd: None, 'M109': lambda cmd: None}
        self.gcode = NS(register_command=self.register)
        self.reactor = NS(monotonic=lambda: self.now, NOW=0., NEVER=1.e30,
                          update_timer=lambda timer, when: self.events.append(('timer',timer,when)))
        self.record = None
        self.nvm = NS(is_busy=lambda: False, store=NS(identity={'machine_id':'modeled','mechanics_id':'modeled'}),
                      commit_calibration=self.commit)
        self.job = NS(board=NS(native_control=True, require_motion=lambda:None,require_heating=lambda:None),
            workflow_qualified=False, toolhead=self.toolhead, hotend=self.hotend, bed=self.bed,
            gcode_move=NS(move_with_transform=self.toolhead.move, move_transform=None,
                          reset_last_position=lambda:None),
            steppers=NS(get_steppers=lambda:[]), idle=NS(idle_timeout=300.),
            _axis_bounds=lambda: ([0.,0.,0.],[305.,305.,315.]),
            _check_position=lambda:self.position[:],
            _temperatures=lambda now:{'hotend':(self.hotend.temperature,self.hotend.target),
                                      'bed':(self.bed.temperature,self.bed.target)},
            get_status=lambda now:{'state':'IDLE','busy':False})
        self.motion = NS(get_status=lambda now:{'state':'COMPLETE','busy':False},home=self.home)
        self.objects = {'m300_motion':self.motion,'m300_job':self.job,
                        'm300_procedures':NS(timer='procedures')}
        self.printer = NS(command_error=RuntimeError, is_shutdown=lambda:self.shutdown,
            lookup_object=lambda name, default=None:self.objects.get(name,default),
            send_event=lambda *args:self.events.append(args),get_start_args=lambda:{},
            invoke_async_shutdown=self.stop)
        c=self.c=M300Calibration.__new__(M300Calibration)
        self.objects['m300_calibration']=c
        c.native_mode=True; c.workflow='M07_STOCK'; c.qualified=True
        c.printer=self.printer;c.reactor=self.reactor;c.gcode=self.gcode;c.job=self.job;c.board=self.job.board
        c.hotend=self.hotend;c.bed=self.bed;c.toolhead=self.toolhead;c.endstop=self.endstop;c.nvm=self.nvm
        c.machine=LevelingState(samples=3,sample_spread=.05,directions={k:'CCW' for k in
            ('rear_left','rear_right','front')},stock_steps_per_mm=scale)
        c.points=((269.,44.),(35.,44.),(150.,158.),(269.,275.),(35.,275.))
        c.safe_z=5.;c.search_margin=margin;c.approach_distance=5.+margin;c.release_distance=1.
        c.screw_pitch=c.center_tolerance=None;c.directions=c.machine.directions
        c.procedure_temperature=260.; self.hotend.min_extrude_temp=170.;self.hotend.max_temp=300.
        c.travel_speed=10.;c.z_speed=1.;c.probe_speed=.5;c.release_speed=.5;c.min_clearance=.5
        c.move_timeout=120.;c.heat_timeout=1200.;c.confirm_timeout=600.;c.total_timeout=3600.
        c.tolerance=2.;c.stable_time=.1
        c.ready=c.installed=True;c._executing=c._native_active=c._cleanup_pending=c._committing=False
        c._cal_homing=c._homed_once=False;c._frame_offset=0.;c._cancel_generation=0
        c.target=c._expected_hotend=0.;c._stable_since=None;c._moves=c._pending_point=None
        c._samples=[];c._wait_until=c._move_deadline=None;c._permit_move=c._permit_heat=None
        c._native_move=self.toolhead.move;c._native_drip=self.toolhead.drip_move
        c._native_set_position=self.toolhead.set_position;c._native_heaters={}
        c._ownership_methods=[];c._ownership_commands=[];c._ownership_callbacks=False
        c._idle_saved=None;c.last_rejection='';c._bind=lambda:None;c._timer='cal';c._watch_timer='watch'
        self.original_move=self.toolhead.move;self.original_g1=self.commands['G1']
        self.original_heat=self.hotend.set_temp

    def register(self,name,callback):
        old=self.commands.pop(name,None)
        if callback is not None:self.commands[name]=callback
        return old
    def stop(self,reason): self.shutdown=True;self.events.append(('shutdown',reason))
    def set_position(self,p):
        self.position=list(p);self.stepper.offset=p[2]-self.stepper.actual/self.stepper.scale
    def move(self,p,speed):
        if not 0.<=p[2]<=315.:raise RuntimeError('native Z boundary')
        self.position=list(p);self.stepper.actual=round((p[2]-self.stepper.offset)*self.stepper.scale)
        self.events.append(('move',tuple(p),speed))
    def query(self, now):
        if self.release_target is not None and self.reclose_after_edge:
            return self.position[2] < self.release_target or self.stuck_after_tail
        return self.level
    def wait_moves(self):
        self.events.append(('drain', self.position[2]))
        if self.on_wait:
            fn, self.on_wait = self.on_wait, None
            fn()
    def home(self,axes):
        self.events.append(('home',axes,self.c.get_status(self.now)['state']))
        self.c._foreign_home()
        self.position=[150.,158.,5.,17.];self.stepper.actual=5*self.stepper.scale;self.stepper.offset=0.
        self.level=False
    def home_start(self,*args,triggered=True,**kw):
        self.triggered=triggered
        return NS(wait=lambda:0)
    def drip(self,target,speed,completion):
        start=self.position[2]
        if self.triggered:
            self.release_target = None
            threshold=self.surface(tuple(target[:2]))+self.c._frame_offset
            success=not self.no_contact and target[2]<=threshold<start
            value=threshold if success else target[2]
            self.level=success
        else:
            self.release_target = target[2]
            value=start+59./self.stepper.scale;success=not self.no_release and value<=target[2]
            if not success:value=target[2]
            self.level=not success
        self.stepper.actual=round((value-self.stepper.offset)*self.stepper.scale)
        self.trigger_time=self.now if success else 0.
        self.events.append(('contact',self.triggered,target[2],value))
        if self.on_drip:
            fn,self.on_drip=self.on_drip,None;fn()
    def commit(self,record,token,phase):
        validate_observation(record);self.record=copy.deepcopy(record)
    def tick(self):
        self.now+=.1
        if self.hotend.target:self.hotend.temperature=self.hotend.target
        self.c._tick(self.now)
    def until(self,state):
        for _ in range(1000):
            if self.c.machine.state==state:return
            if self.c.machine.state=='FAULT':raise AssertionError(self.c.machine.reason)
            self.tick()
        raise AssertionError('did not reach '+state)
    def start(self):
        self.c.start();self.until('WAIT_WARNING')
        try:
            self.confirm()
        except RuntimeError:
            if self.c.machine.state == 'FAULT':return
            raise
        self.confirm()
    def confirm(self):
        self.c.confirm(self.c.machine.token,self.c.machine.phase_id)


class NativeLevelingTests(unittest.TestCase):
    def setUp(self):
        self.patch=patch.dict(sys.modules,{'payload.homing':homing})
        self.patch.start();self.addCleanup(self.patch.stop)

    def test_zero_margin_reproduces_reported_missing_contact_at_native_zero(self):
        h=Harness(margin=0.);h.start();h.until('FAULT')
        self.assertIn('No trigger',h.c.machine.reason)
        self.assertIsNone(h.record)

    def test_both_factory_scales_measure_below_home_without_changing_global_limits(self):
        for scale in (400,800):
            with self.subTest(scale=scale):
                h=Harness(scale);h.start();h.until('REVIEW')
                self.assertAlmostEqual(h.c.machine.reference,-1./scale)
                self.assertEqual(h.job._axis_bounds()[0][2],0.)
                self.assertEqual(h.job._axis_bounds()[1][2],315.)
                self.assertEqual([e for e in h.events if e[0]=='home'],[('home','xyz','HOMING')])
                self.assertIsNone(h.record)
                h.confirm()
                self.assertEqual(h.c.machine.state,'COMPLETE')
                self.assertIsNotNone(h.record)
                self.assertAlmostEqual(h.position[2],5.)
                self.assertEqual(h.position[3],17.)
                self.assertEqual(h.c._frame_offset,0.)
                self.assertEqual(h.toolhead.move,h.original_move)
                self.assertEqual(h.commands['G1'],h.original_g1)
                self.assertEqual(h.hotend.set_temp,h.original_heat)
                self.assertFalse(h.job.workflow_qualified)

    def test_native_ready_starts_both_execution_and_watchdog(self):
        h=Harness();h.c._ready()
        self.assertEqual(h.events,[('timer','cal',0.),('timer','watch',0.)])

    def test_oem_preflight_heats_then_waits_for_warning_and_knob_confirmations(self):
        h=Harness();h.c.start()
        self.assertEqual(h.c.machine.state,'HEATING')
        self.assertEqual(h.hotend.target,260.)
        h.until('WAIT_WARNING')
        for _ in range(10):h.tick()
        self.assertFalse(any(e[0] in ('home','move','contact') for e in h.events))
        h.confirm()
        self.assertEqual(h.c.machine.state,'WAIT_TIGHTEN')
        for _ in range(10):h.tick()
        self.assertFalse(any(e[0]=='contact' for e in h.events))
        h.confirm();h.until('REVIEW')

    def test_external_movement_is_rejected_only_during_session_and_restored_after_cancel(self):
        h=Harness();h.c.start()
        with self.assertRaisesRegex(RuntimeError,'owns resources'):h.commands['G1'](None)
        with self.assertRaisesRegex(RuntimeError,'owns motion'):h.toolhead.move([150.,158.,4.,17.],1.)
        h.c.cancel();h.tick()
        self.assertEqual(h.c.machine.state,'CANCELLED')
        self.assertEqual(h.commands['G1'],h.original_g1)
        self.assertEqual(h.toolhead.move,h.original_move)

    def test_stale_confirmation_does_not_advance_phase(self):
        h=Harness();h.c.start();h.until('WAIT_WARNING');token,phase=h.c.machine.token,h.c.machine.phase_id
        h.confirm()
        with self.assertRaisesRegex(RuntimeError,'stale'):h.c.confirm(token,phase)
        self.assertEqual(h.c.machine.state,'WAIT_TIGHTEN')

    def test_screw_instruction_waits_for_explicit_confirmation(self):
        h=Harness();h.surface=lambda xy:.4 if xy in ((269.,275.),(35.,275.)) else 0.
        h.start();h.until('ADJUST');instruction=copy.deepcopy(h.c.machine.instruction)
        for _ in range(10):h.tick()
        self.assertEqual(h.c.machine.instruction,instruction)
        self.assertIsNone(h.record)
        h.surface=lambda xy:h.c.machine.reference;h.confirm()
        for _ in range(1000):
            if h.c.machine.state=='REVIEW':break
            if h.c.machine.state=='ADJUST':h.confirm()
            h.tick()
        self.assertEqual(h.c.machine.state,'REVIEW');h.confirm()
        self.assertEqual(h.c.machine.state,'COMPLETE')

    def test_contact_failure_keeps_prior_record_and_cuts_heaters(self):
        h=Harness();h.record={'prior':'kept'};h.no_contact=True;h.start();h.until('FAULT')
        self.assertEqual(h.record,{'prior':'kept'})
        self.assertEqual((h.hotend.target,h.bed.target),(0.,0.))
        self.assertTrue(h.shutdown)

    def test_cancel_during_native_contact_causes_shutdown_and_cannot_save(self):
        h=Harness();h.start();h.on_drip=lambda:h.c.cancel('modelled stop')
        h.until('FAULT')
        self.assertTrue(h.shutdown);self.assertIsNone(h.record)

    def test_cancel_during_owned_homing_faults_even_when_queue_is_temporarily_empty(self):
        h=Harness()
        h.motion.home=lambda axes:h.c.cancel('operator stop during G28')
        h.start();h.until('FAULT')
        self.assertTrue(h.shutdown);self.assertIsNone(h.record)
        self.assertFalse(any(e[0]=='contact' for e in h.events))

    def test_leveling_instruction_precedes_buttons_on_physical_panel(self):
        h=Harness();h.surface=lambda xy:.4 if xy in ((269.,275.),(35.,275.)) else 0.
        h.start();h.until('ADJUST')
        status=h.c.get_status(h.now)
        view={'owner':'m300_calibration','title':'Platform leveling','state':'ADJUST',
              'token':status['session_token'],'phase':status['phase_id'],
              'actions':['CONFIRM','CANCEL'],'view_id':'modeled','snapshots':{'m300_calibration':status},
              'progress':None,'elapsed':None,'phase_remaining':None,'completed_mm':None,
              'filename':'','reason':''}
        p=M300Procedures.__new__(M300Procedures);p.view=lambda now:view
        title,rows=p.rows(h.now)
        screw=next(i for i,(label,action) in enumerate(rows) if ' side is too ' in label)
        confirm=next(i for i,(label,action) in enumerate(rows) if label=='Continue')
        self.assertLess(screw,confirm)

    def test_oem_icons_follow_prepare_heat_home_measure_adjust_review_and_cancel(self):
        for state,expected in (('WAIT_WARNING','0x0801c434'),('WAIT_TIGHTEN','0x0801fe50'),('HEATING','0x0801c2b8'),
            ('HOMING','0x0801c2b8'),('PROBING','0x0801c2b8'),('REVIEW','0x0801c024'),
            ('CANCELLED','0x0801fe34')):
            self.assertEqual(choose_icon(menu_page='calibration',calibration={'state':state}),expected)
        icon=choose_icon(menu_page='calibration',calibration={'state':'ADJUST',
            'instruction':{'screw':'rear_left','action':'TIGHTEN'}})
        self.assertNotEqual(icon,'0x0801ca28')

    def test_configuration_migration_keeps_user_geometry_and_legacy_print_disabled(self):
        cfg='[stepper_z]\nposition_min: 0\nposition_max: 315\n[m300_job]\nworkflow_qualified: False\n[m300_calibration]\nqualified: False\nworkflow: M07_STOCK\nstock_steps_per_mm: 800\n'
        new=m300_profile.convert_text(cfg)
        sections=dict(m300_profile.blocks(new)[1])
        self.assertEqual(m300_profile.option(sections['stepper_z'],'position_min'),'0')
        self.assertEqual(m300_profile.option(sections['stepper_z'],'position_max'),'315')
        self.assertEqual(m300_profile.option(sections['m300_job'],'workflow_qualified'),'False')
        self.assertEqual(m300_profile.option(sections['m300_calibration'],'probe_search_margin'),'1')
        self.assertEqual(m300_profile.convert_text(new),new)

    def test_shared_presenter_is_live_for_native_board(self):
        h=Harness();p=M300Procedures.__new__(M300Procedures)
        p.reactor=h.reactor;p.timer='present';p.live=False
        p._ready()
        self.assertTrue(p.live);self.assertEqual(h.events[-1],('timer','present',0.))

    def test_missing_release_faults_without_publishing_observation(self):
        h=Harness();h.no_release=True;h.start();h.until('FAULT')
        self.assertIsNone(h.record);self.assertTrue(h.shutdown)
        self.assertEqual(h.hotend.target,0.)

    def test_hw05_open_edge_then_reclose_completes_full_retract_before_query(self):
        for scale in (400, 800):
            h=Harness(scale);h.reclose_after_edge=True
            h.start();h.until('REVIEW')
            reverse=[i for i,e in enumerate(h.events) if e[0]=='contact' and not e[1]]
            self.assertTrue(reverse)
            for i in reverse:
                edge=h.events[i]
                tail,settle,drain=[e for e in h.events[i+1:] if e[0] in ('move','dwell','drain')][:3]
                self.assertAlmostEqual(edge[2]-edge[3],1.-59./scale)
                self.assertEqual(tail[0],'move')
                self.assertAlmostEqual(tail[1][2],edge[2])
                self.assertEqual(settle,('dwell',.05))
                self.assertEqual(drain,('drain',edge[2]))
            self.assertFalse(h.shutdown)

    def test_reclosed_contact_still_active_after_full_retract_is_a_real_fault(self):
        h=Harness();h.reclose_after_edge=h.stuck_after_tail=True
        h.record={'previous':'kept'};h.start();h.until('FAULT')
        self.assertIn('NO_RELEASE',h.c.machine.reason)
        self.assertEqual(h.record,{'previous':'kept'})
        self.assertTrue(h.shutdown);self.assertEqual(h.hotend.target,0.)

    def test_cancel_during_release_tail_cannot_publish_or_continue(self):
        h=Harness();h.start();h.on_wait=lambda:h.c.cancel('stop during retract drain')
        h.until('FAULT')
        self.assertIsNone(h.record);self.assertTrue(h.shutdown)
        self.assertEqual(h.hotend.target,0.)

    def test_old_edge_only_retract_reproduces_the_reported_closed_query(self):
        h=Harness();h.reclose_after_edge=True;h.start()
        queue=h.c._queue_move
        def skip_tail(target,speed):
            if h.release_target is not None:
                h.c._wait_until=h.now;h.c._move_deadline=h.now+120.
            else:queue(target,speed)
        with patch.object(h.c,'_queue_move',skip_tail):
            h.until('FAULT')
        self.assertIn('NO_RELEASE',h.c.machine.reason)

    def test_cancel_after_measurements_restores_frame_and_native_owners(self):
        h=Harness();h.start();h.until('REVIEW')
        self.assertEqual(h.c._frame_offset,1.)
        h.c.cancel();h.tick()
        self.assertIsNone(h.record);self.assertEqual(h.c._frame_offset,0.)
        self.assertAlmostEqual(h.position[2],5.)
        self.assertEqual(h.toolhead.move,h.original_move)

    def test_second_session_keeps_same_reference_and_no_frame_accumulation(self):
        h=Harness()
        for _ in range(2):
            h.start();h.until('REVIEW');h.confirm()
            self.assertAlmostEqual(h.record['reference_mm'],-.0025)
            self.assertAlmostEqual(h.position[2],5.)
            self.assertEqual(h.c._frame_offset,0.)

    def test_external_start_displays_same_prepare_prompt_and_oem_icon_and_rejects_stale_click(self):
        h=Harness();p=M300Procedures.__new__(M300Procedures)
        prompts=[];p.printer=h.printer;p.reactor=h.reactor;p.gcode=NS(respond_raw=prompts.append)
        p.timer='present';p.live=True;p.epoch='modeled';p.revision=0
        p.identity=p.view_id=p.consumed=p.last_prompt=None
        p.changes={};p.last_keys={};p.started={};p.last_display=p.previous_display=None
        h.objects['m300_procedures']=p
        menu=NS(page='main',generation=0)
        def navigate(page):menu.page=page;menu.generation+=1
        menu._navigate=navigate
        oled=NS(page='status',selection=4,render_at=5.)
        h.objects.update(m300_menu=menu,m300_oled=oled)
        h.c.start();h.until('WAIT_WARNING');p._tick(h.now)
        self.assertEqual((menu.page,oled.page,oled.selection),('procedure','m04',0))
        self.assertTrue(any('WARNING: Printhead will be hot' in line for line in prompts))
        self.assertTrue(any('ZORTRAX_PROCEDURE_ACTION VIEW=' in line for line in prompts))
        ui=M300MenuUI.__new__(M300MenuUI)
        ui.menu=menu;ui.procedures=p;ui.printer=h.printer;ui.oem_sprites=NS(get=lambda icon,now:icon)
        self.assertEqual(ui.get_oem_sprite('m04',[],0,h.now),'0x0801c434')
        old=p.view_id;p.action(old,'CONFIRM')
        self.assertEqual(h.c.machine.state,'WAIT_TIGHTEN')
        with self.assertRaisesRegex(RuntimeError,'expired'):p.action(old,'CONFIRM')
        self.assertEqual(ui.get_oem_sprite('m04',[],0,h.now),'0x0801fe50')


if __name__=='__main__':unittest.main()
