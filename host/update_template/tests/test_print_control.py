# Marcin Kowalik <mkowalik@agh.edu.pl>
# test_print_control.py - Sprawdza przygotowanie, pauzę, wznowienie, anulowanie i zakończenie zadania.
"""Native parser/pause ownership with modeled heaters and physical motion.

Real file descriptors verify file identity. Hardware temperature, motion and
drain are modeled; passing this suite is not a physical M300 acceptance.
"""
from pathlib import Path
from types import SimpleNamespace as NS
import copy
import tempfile
import unittest

import test_native_oem_services as oem
from payload.m300_print_control import M300PrintControl
from payload.m300_print_ui import M300PrintUI


class Harness(oem.Harness):
    def __init__(self):
        super().__init__()
        self.homed='xyz';self.position=[100.,110.,10.,17.]
        self.hotend.target=self.hotend.temperature=240.
        self.bed.target=self.bed.temperature=60.
        self.temp=tempfile.TemporaryDirectory()
        p=Path(self.temp.name)/'test.gcode';p.write_text('G1 X200\n'*300)
        self.sd=self.objects['virtual_sdcard']
        self.sd.current_file=p.open();self.sd.file_position=123;self.sd.work_timer='native'
        self.sd.must_pause_work=False
        self.sd.do_pause=self.do_pause;self.sd.do_resume=self.do_resume;self.sd.do_cancel=self.do_cancel
        self.sd.is_active=lambda:self.sd.work_timer is not None
        self.sd.cmd_from_sd = False
        self.sd.is_cmd_from_sd = lambda: self.sd.cmd_from_sd
        self.sd.print_stats=NS(state='printing',filename='test.gcode',last_pause_time=None)
        self.print_state='printing'
        self.web=NS(_endpoints={'pause_resume/'+name:getattr(self.pause,'_handle_'+name+'_request')
                               for name in ('pause','resume','cancel')})
        self.objects['webhooks']=self.web
        self.objects['heaters']=NS(lookup_heater=lambda name:self.hotend if name=='extruder' else self.bed,
                                  turn_off_all_heaters=self.off)
        self.objects['stepper_enable']=NS(get_steppers=lambda:[])
        self.objects['display_status']=NS(message='')
        self.mesh=None
        self.objects['bed_mesh']=NS(get_mesh=lambda:self.mesh,set_mesh=self.set_mesh,
            pmgr=NS(get_profiles=lambda:{'m300_pads':{}},load_profile=self.load_mesh))
        def native_mesh_profile(cmd):
            name = cmd.get('LOAD')
            if name not in self.objects['bed_mesh'].pmgr.get_profiles():
                raise cmd.error('Unknown profile')
            self.load_mesh(name)
        self.gcode.register_command('BED_MESH_PROFILE', native_mesh_profile)
        self.objects['m300_motion']=NS(home=self.home,ensure_xy_clearance=self.clearance,
                                       is_busy=lambda:False)
        self.objects['fan']=NS(set_speed=lambda time,value:self.events.append(('fan',value)))
        self.gcode.register_command('M107',lambda cmd:self.events.append(('fan',0.)))
        for name in ('M24','BED_MESH_CLEAR','SAVE_CONFIG','SET_GCODE_OFFSET','PROBE','PROBE_ACCURACY',
                     'SET_EXTRUDER_ROTATION_DISTANCE','SYNC_EXTRUDER_MOTION'):
            if name not in self.gcode.ready_gcode_handlers:self.gcode.register_command(name,lambda cmd:None)
        self.c=M300PrintControl(self.config)
        self.objects['m300_print_control']=self.c
        self.c._connect();self.c._ready();self.events.clear()
        self.gmove.reset_last_position()
        self.original_move=self.toolhead.move

    def file_command(self, script):
        self.sd.cmd_from_sd = True
        try:
            self.run(script)
        finally:
            self.sd.cmd_from_sd = False

    def close(self):
        self.c._stop('test ends')
        if self.sd.current_file:self.sd.current_file.close()
        self.temp.cleanup()

    def off(self):
        self.hotend.set_temp(0.);self.bed.set_temp(0.)

    def do_pause(self):
        self.sd.must_pause_work=True
        self.events.append(('native_pause',))

    def stop_worker(self):
        self.sd.work_timer=None;self.print_state='paused';self.sd.print_stats.state='paused'

    def do_resume(self):
        self.sd.work_timer='native';self.sd.must_pause_work=False
        self.print_state='printing';self.sd.print_stats.state='printing'
        self.events.append(('native_resume',))

    def do_cancel(self):
        if self.sd.work_timer is not None:raise RuntimeError('closed inside native worker')
        if self.sd.current_file:self.sd.current_file.close()
        self.sd.current_file=None;self.sd.file_position=0
        self.print_state='cancelled';self.events.append(('native_cancel',))

    def set_mesh(self,value):self.mesh=value
    def load_mesh(self,name):
        self.events.append(('mesh',name));self.mesh=NS(profile_name=name, get_profile_name=lambda:name, mesh_offsets=[0.,0.])
    def clearance(self,check):
        check()
        assert self.c.lease is None
        self.events.append(('clearance',))
    def home(self, *, filament_prepared):
        assert filament_prepared
        self.events.append(('home',self.hotend.target,self.bed.target))
        self.homed='xyz';self.position=[150.,158.,5.,self.position[3]]
        self.gmove.reset_last_position()

    def step_control(self,dt=.25):
        self.now+=dt;self.c._tick(self.now)

    def control_until(self,state,phase=None):
        for _ in range(1200):
            if self.c.state==state and (phase is None or self.c.phase==phase):return
            if self.c.state=='FAILED':raise AssertionError(self.c.last_error)
            self.step_control()
        raise AssertionError((self.c.state,self.c.phase))

    def pause_print(self):
        self.run('PAUSE');self.stop_worker();self.control_until('PAUSED')

    def pause_at_material_park(self):
        self.position[:2] = self.c.park_xy
        self.gmove.reset_last_position()
        self.pause_print()


class PrintControlTests(unittest.TestCase):
    def setUp(self):self.h=Harness();self.addCleanup(self.h.close)

    def test_pause_waits_for_native_worker_and_drains_before_any_move(self):
        h=self.h;h.run('PAUSE')
        self.assertTrue(h.pause.is_paused)
        h.step_control(2.);self.assertFalse(any(e[0]=='move' for e in h.events))
        h.stop_worker();h.busy_until=h.now+4.;h.step_control(2.)
        self.assertFalse(any(e[0]=='move' for e in h.events))
        h.control_until('PAUSED');self.assertEqual(h.position[:3],[100.,110.,15.])
        moves=[e[1] for e in h.events if e[0]=='move']
        self.assertEqual(moves, [(100.,110.,10.,15.), (100.,110.,15.,15.)])

    def test_duplicate_pause_does_not_replace_native_saved_state(self):
        h=self.h;h.pause_print();saved=copy.deepcopy(h.c.context['saved']);h.run('PAUSE')
        self.assertEqual(saved,h.gmove.saved_states['PAUSE_STATE'])

    def test_near_z_max_never_moves_xy_or_exceeds_z_travel(self):
        h=self.h;h.position[2]=313.;h.gmove.reset_last_position();h.pause_print()
        self.assertEqual(h.position[:3],[100.,110.,315.])
        self.assertFalse(h.c.context['plan']['xy_allowed'])

    def test_active_stream_refuses_external_home_start_and_end_without_side_effects(self):
        h = self.h
        from payload.m300_native_motion import M300NativeMotion
        motion = NS(printer=h.printer, home=lambda **kwargs: self.fail('unexpected home'))
        h.gcode.register_command('ZORTRAX_HOME', lambda gcmd: M300NativeMotion.cmd_home(motion, gcmd))
        for command in ('ZORTRAX_PRINT_START EXTRUDER_TEMP=240', 'ZORTRAX_PRINT_END',
                        'G28', 'ZORTRAX_HOME AXES=XYZ'):
            with self.subTest(command=command), self.assertRaisesRegex(
                    h.printer.command_error, 'active print file'):
                h.run(command)
        self.assertEqual(h.events, [])
        self.assertTrue(h.sd.is_active())
        self.assertFalse(h.sd.must_pause_work)
        self.assertEqual((h.c.state, h.hotend.target, h.bed.target), ('IDLE', 240., 60.))

    def test_native_boundaries_are_one_shot_and_legacy_home_is_allowed_before_extrusion(self):
        h = self.h
        h.file_command('G28')
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240')
        h.stop_worker()
        h.control_until('IDLE')
        for command in ('ZORTRAX_PRINT_START EXTRUDER_TEMP=240', 'G28'):
            with self.assertRaisesRegex(h.printer.command_error, 'after print preparation'):
                h.file_command(command)
        h.file_command('ZORTRAX_PRINT_END')
        h.stop_worker()
        h.control_until('IDLE')
        for command in ('G0 X10', 'G1 X10', 'ZORTRAX_PRINT_END'):
            with self.assertRaisesRegex(h.printer.command_error, 'follows END_PRINT'):
                h.file_command(command)
        h.emit('virtual_sdcard:reset_file')
        h.file_command('G1 X11 F300')
        self.assertEqual(h.position[0], 11.)
        h.objects['m300_models'] = NS(runtime_deposited=True)
        for command in ('ZORTRAX_PRINT_START EXTRUDER_TEMP=240', 'G28'):
            with self.assertRaisesRegex(h.printer.command_error, 'model extrusion'):
                h.file_command(command)

    def test_m600_from_file_without_safe_xy_park_preserves_resumable_pause(self):
        for z, corner in ((314., (300.,305.)), (10., (999.,305.))):
            with self.subTest(z=z, corner=corner):
                h = Harness()
                self.addCleanup(h.close)
                h.c.park_xy = corner
                h.position[2] = z
                h.gmove.reset_last_position()
                h.file_command('M600')
                h.stop_worker()
                h.control_until('PAUSED')
                self.assertIn('Material change skipped', h.c.notice)
                self.assertFalse(h.f.is_busy())
                self.assertFalse(h.c.context['change_required'])
                self.assertFalse(h.c.context['invalid'])
                self.assertEqual(h.position[:2], [100.,110.])
                self.assertEqual((h.hotend.target, h.bed.target), (240.,60.))
                h.run('RESUME')
                h.control_until('IDLE')
                self.assertTrue(h.sd.is_active())
                self.assertEqual(h.position[:3], [100.,110.,z])

    def test_unused_legacy_adapter_never_detaches_native_file_on_restart(self):
        from payload.m300_job_sd import JobSD
        h = self.h
        legacy = JobSD.__new__(JobSD)
        legacy.v_sd = h.sd
        legacy.installed = False
        legacy.selected = legacy.prepared = None
        legacy._generation = 0
        stream = h.sd.current_file
        legacy._lifecycle_stop()
        self.assertTrue(legacy._halted)
        self.assertFalse(stream.closed)
        self.assertIs(h.sd.current_file, stream)
        self.assertEqual(h.sd.file_position, 123)
        self.assertEqual(h.sd.work_timer, 'native')
        self.assertFalse(h.sd.must_pause_work)

    def test_older_travel_does_not_silently_clip_configured_park(self):
        h=self.h;h.c.park_xy=(999.,305.);h.pause_print()
        self.assertEqual(h.position[:2],[100.,110.])
        with self.assertRaisesRegex(h.printer.command_error,'material-change park'):
            h.run('M600')
        self.assertIn('outside XY',h.c.notice)
        h.run('RESUME');h.control_until('IDLE')

    def test_paused_idle_holds_bed_and_all_motors(self):
        h=self.h;h.pause_print();h.run('ZORTRAX_PAUSE_IDLE')
        self.assertEqual(h.bed.target,60.);self.assertNotIn(('native_resume',),h.events)
        self.assertFalse(any(e[0]=='shutdown' for e in h.events))

    def test_nozzle_standby_and_off_boundaries_without_bed_cooldown(self):
        h=self.h;h.pause_print();start=h.c.context['thermal_since']
        h.now=start+599.999;h.c._tick(h.now);self.assertEqual(h.hotend.target,240.)
        h.now=start+600.;h.c._tick(h.now);self.assertEqual(h.hotend.target,150.)
        h.now=start+1800.;h.c._tick(h.now);self.assertEqual(h.hotend.target,0.)
        self.assertEqual(h.bed.target,60.)

    def test_cooling_timer_never_reheats_an_explicitly_off_nozzle(self):
        h=self.h;h.pause_print();h.hotend.target=0.;h.step_control(650.)
        self.assertEqual(h.hotend.target,0.)

    def test_resume_reheats_original_targets_before_return_and_native_resume(self):
        h=self.h;h.pause_print();h.hotend.temperature=30.;h.hotend.target=0.
        h.run('RESUME');self.assertEqual(h.hotend.target,240.)
        for _ in range(20):h.step_control()
        self.assertEqual(h.position[:3],[100.,110.,15.]);self.assertIsNone(h.sd.work_timer)
        h.hotend.temperature=240.;h.control_until('IDLE')
        self.assertEqual(h.position[:3],[100.,110.,10.]);self.assertFalse(h.pause.is_paused)
        self.assertEqual(h.sd.work_timer,'native');self.assertEqual(h.bed.target,60.)

    def test_native_parser_modes_speed_flow_and_e_state_survive_pause(self):
        h=self.h;h.run('G91\nM83\nM220 S90\nM221 S95')
        before=h.gmove.get_status(h.now);h.pause_print();h.run('RESUME');h.control_until('IDLE')
        after=h.gmove.get_status(h.now)
        for key in ('absolute_coordinates','absolute_extrude','speed_factor','extrude_factor'):
            self.assertEqual(before[key],after[key],key)
        self.assertAlmostEqual(h.position[3],17.)

    def test_interlocks_block_home_mesh_bypass_resume_and_manual_xyz(self):
        h=self.h;h.pause_print()
        for script in ('G28','M24','BED_MESH_CLEAR','SAVE_CONFIG','SET_GCODE_OFFSET Z=1','G1 X20',
                       'CLEAR_PAUSE','PROBE','PROBE_ACCURACY','SET_EXTRUDER_ROTATION_DISTANCE DISTANCE=99',
                       'SYNC_EXTRUDER_MOTION EXTRUDER=extruder MOTION_QUEUE='):
            with self.subTest(script=script),self.assertRaises(h.printer.command_error):h.run(script)

    def test_lost_homing_or_stepper_release_cannot_resume(self):
        h=self.h;h.pause_print();h.c._motor_off()
        with self.assertRaisesRegex(h.printer.command_error,'position was released'):h.run('RESUME')

    def test_changed_file_position_cannot_resume(self):
        h=self.h;h.pause_print();h.sd.file_position+=1
        with self.assertRaisesRegex(h.printer.command_error,'file identity'):h.run('RESUME')

    def test_replaced_native_pause_state_cannot_resume(self):
        h=self.h;h.pause_print();h.gmove.saved_states['PAUSE_STATE']['speed']=1
        with self.assertRaisesRegex(h.printer.command_error,'PAUSE_STATE'):h.run('RESUME')

    def test_mesh_change_invalidates_resume_even_without_gcode(self):
        h=self.h;h.pause_print();h.mesh=NS(mesh_offsets=[0.,0.])
        with self.assertRaisesRegex(h.printer.command_error,'bed mesh changed'):h.run('RESUME')

    def test_thermal_timeout_fails_off_and_does_not_resume_file(self):
        h=self.h;h.pause_print();h.hotend.temperature=25.;h.run('RESUME')
        h.step_control(h.c.heat_timeout+1.)
        self.assertEqual(h.c.state,'FAILED');self.assertEqual(h.hotend.target,0.)
        self.assertEqual(h.bed.target,0.);self.assertIsNone(h.sd.work_timer)

    def test_cancel_does_not_close_a_file_inside_its_sd_command(self):
        h=self.h;h.run('CANCEL_PRINT');h.step_control()
        self.assertIsNotNone(h.sd.current_file)
        h.stop_worker();h.control_until('IDLE')
        self.assertEqual(h.print_state,'cancelled');self.assertIsNone(h.sd.current_file)
        self.assertEqual((h.hotend.target,h.bed.target),(0.,0.));self.assertIn(('fan',0.),h.events)

    def test_restart_revokes_all_callbacks_without_reheat_or_resume(self):
        h=self.h;h.pause_print();h.run('RESUME');h.c._stop('restart')
        before=len(h.events);h.step_control(800.)
        self.assertEqual(len(h.events),before);self.assertEqual(h.hotend.target,0.)
        self.assertIsNone(h.sd.work_timer)

    def test_material_confirmation_requires_success_and_hot_visible_flow(self):
        h=self.h;h.pause_at_material_park();self.assertEqual(h.c.material_begin(),240.)
        with self.assertRaisesRegex(h.printer.command_error,'complete the material'):h.run('FILAMENT_READY')
        h.c.material_complete(True);h.hotend.temperature=25.;h.hotend.target=0.
        with self.assertRaisesRegex(h.printer.command_error,'heat the nozzle'):h.run('FILAMENT_READY')
        h.run('RESUME');h.hotend.temperature=240.;h.control_until('PAUSED','WAIT_FILAMENT_READY')
        self.assertIsNone(h.sd.work_timer);h.run('FILAMENT_READY\nRESUME');h.control_until('IDLE')

    def test_failed_material_change_never_resumes_or_confirms(self):
        h=self.h;h.pause_at_material_park();h.c.material_begin();h.c.material_complete(False)
        for command in ('RESUME','FILAMENT_READY'):
            with self.assertRaises(h.printer.command_error):h.run(command)

    def test_m600_stops_and_parks_before_starting_existing_change_wizard(self):
        h=self.h;h.run('M600');self.assertEqual(h.c.state,'PAUSING')
        self.assertFalse(h.f.is_busy());h.stop_worker();h.control_until('PAUSED')
        self.assertTrue(h.f.is_busy());self.assertEqual(h.f.machine.mode,'CHANGE')
        self.assertEqual(h.position[:3],[300.,305.,15.])
        self.assertEqual(h.f._native_pause['target'],240.)

    def test_start_retracts_before_home_then_feeds_and_purges_without_crossing(self):
        h = self.h
        h.hotend.temperature = 25.
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        h.stop_worker()
        h.step_control()
        self.assertEqual((h.hotend.target,h.bed.target),(240.,60.))
        h.step_control(4.)
        self.assertFalse(any(event[0] in ('move', 'home') for event in h.events))
        h.hotend.temperature = 240.
        h.control_until('STARTING', 'RETRACT_DRAIN')
        self.assertEqual(h.events[-1], ('move', (100., 110., 10., 7.), h.c.e_speed))
        self.assertEqual(h.events[-2], ('clearance',))
        h.step_control()
        self.assertNotIn(('home', 240., 60.), h.events)
        h.control_until('IDLE')
        home = h.events.index(('home', 240., 60.))
        mesh = h.events.index(('mesh', 'm300_pads'))
        self.assertLess(home, mesh)
        moves = [event for event in h.events[mesh:] if event[0] == 'move']
        self.assertEqual(moves[1][1], (3., 10., 5., 7.))
        self.assertEqual(moves[2], ('move', (3., 10., 5., 13.), h.c.e_speed))
        self.assertEqual([event[1][:3] for event in moves[3:]], [
            (3., 10., .28), (3., 270., .28), (3.5, 270., .28),
            (3.5, 10., .28), (253.5, 10., .28), (253.5, 9.5, .28),
            (3.5, 9.5, .28), (3.5, 9.5, 5.)])
        self.assertEqual(moves[4][1][3], moves[5][1][3])
        self.assertEqual(moves[7][1][3], moves[8][1][3])
        self.assertEqual(h.sd.work_timer, 'native')
        self.assertEqual(h.hotend.target, 240.)

    def test_completed_start_keeps_light_white_for_its_native_file_without_accounting(self):
        h = self.h
        h.objects['m300_motion'].get_status = lambda now: dict(state='IDLE', busy=False)
        self.assertNotIn('m300_nvm', h.objects)
        self.assertNotIn('m300_models', h.objects)
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        h.stop_worker()
        h.step_control()
        self.assertFalse(h.c.get_status(h.now)['model_print_ready'])
        self.assertEqual(h.m.status_led_rgb(h.now), (1, 0, 0))
        h.control_until('IDLE')
        h.hotend.temperature -= 5.
        self.assertTrue(h.c.get_status(h.now)['model_print_ready'])
        self.assertEqual(h.m.status_led_rgb(h.now), (1, 1, 1))
        h.pause.is_paused = True
        self.assertEqual(h.m.status_led_rgb(h.now), (1, 0, 1))
        h.pause.is_paused = False
        h.objects['m300_errors'] = NS(current={'fatal': True})
        self.assertEqual(h.m.status_led_rgb(h.now), (1, 0, 0))

    def test_start_completion_belongs_to_one_file_and_resets_on_end(self):
        h = self.h
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        h.stop_worker()
        h.control_until('IDLE')
        stream = h.sd.current_file
        with open(stream.name) as other_stream:
            h.sd.current_file = other_stream
            self.assertFalse(h.c.model_print_ready)
            h.sd.current_file = stream
        h.emit('virtual_sdcard:reset_file')
        self.assertFalse(h.c.model_print_ready)

        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        h.stop_worker()
        h.control_until('IDLE')
        self.assertTrue(h.c.model_print_ready)
        h.file_command('ZORTRAX_PRINT_END')
        self.assertFalse(h.c.model_print_ready)
        h.stop_worker()
        h.control_until('IDLE')
        self.assertFalse(h.c.model_print_ready)

    def test_missing_mesh_fails_before_heating_or_stopping_file(self):
        h=self.h
        with self.assertRaisesRegex(h.printer.command_error,'saved mesh'):
            h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60 MESH=missing')
        self.assertEqual(h.c.state,'IDLE');self.assertFalse(h.sd.must_pause_work)

    def test_start_validates_extrusion_requirements_before_taking_ownership(self):
        h = self.h
        h.hotend.target = 0.
        with self.assertRaisesRegex(h.printer.command_error, 'requires a nozzle target'):
            h.file_command('ZORTRAX_PRINT_START BED_TEMP=60')
        h.toolhead.get_extruder = lambda: NS(max_e_dist=9.5)
        with self.assertRaisesRegex(h.printer.command_error, 'max_extrude_only_distance'):
            h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        self.assertEqual(h.c.state, 'IDLE')
        self.assertFalse(h.sd.must_pause_work)

    def test_start_waits_for_native_extrusion_threshold_inside_heat_tolerance(self):
        h = self.h
        h.hotend.temperature = 169.
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=170 BED_TEMP=60')
        h.stop_worker()
        for _ in range(12):
            h.step_control()
        self.assertEqual(h.c.state, 'STARTING')
        self.assertFalse(any(event[0] in ('move', 'home') for event in h.events))
        h.hotend.temperature = 170.
        h.control_until('STARTING', 'RETRACT_DRAIN')
        self.assertEqual(h.position[3], 7.)

    def test_start_supports_explicit_no_mesh(self):
        h=self.h;h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60 MESH=NONE')
        h.stop_worker();h.control_until('IDLE');self.assertNotIn(('mesh','m300_pads'),h.events)

    def test_cancel_during_start_heating_never_homes_or_resumes(self):
        h=self.h;h.hotend.temperature=25.
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60');h.stop_worker();h.step_control()
        h.run('CANCEL_PRINT');h.control_until('IDLE')
        self.assertFalse(any(e[0] in ('home','native_resume') for e in h.events))
        self.assertEqual(h.print_state,'cancelled')

    def test_cancel_during_start_retract_drain_never_homes_or_feeds_back(self):
        h = self.h
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        h.stop_worker()
        h.control_until('STARTING', 'RETRACT_DRAIN')
        h.run('CANCEL_PRINT')
        h.control_until('IDLE')
        self.assertEqual(h.print_state, 'cancelled')
        self.assertFalse(any(event[0] in ('home', 'mesh', 'native_resume') for event in h.events))
        self.assertEqual(h.position[3], 7.)
        self.assertEqual((h.hotend.target, h.bed.target), (0., 0.))
        self.assertNotIn('M300_START_RETRACT', h.gmove.saved_states)

    def test_cancel_inside_yielding_native_home_revokes_stale_purge(self):
        h=self.h
        h.objects['m300_motion'].home=lambda **kwargs:h.c._request_cancel('cancel during home')
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60');h.stop_worker()
        h.control_until('IDLE');self.assertEqual(h.print_state,'cancelled')
        self.assertNotIn(('mesh','m300_pads'),h.events);self.assertNotIn(('native_resume',),h.events)

    def test_end_parks_turns_off_and_leaves_real_eof_to_native_worker(self):
        h=self.h;h.file_command('ZORTRAX_PRINT_END');h.stop_worker();h.control_until('IDLE')
        # The fixture has 315 mm travel and starts at Z10: request a relative 300 mm.
        moves = [event[1][:3] for event in h.events if event[0] == 'move']
        self.assertEqual(moves, [(100.,110.,10.), (100.,110.,310.), (300.,305.,310.)])
        self.assertEqual(h.sd.work_timer,'native')
        self.assertEqual(h.print_state,'printing');self.assertIsNotNone(h.sd.current_file)
        self.assertEqual((h.hotend.target,h.bed.target),(0.,0.));self.assertIn(('fan',0.),h.events)

    def test_end_clamps_drop_and_skips_xy_if_model_clearance_is_unavailable(self):
        for start_z, expected_xy in ((200., (300.,305.)), (310., (300.,305.)),
                                     (313., (100.,110.)), (315., (100.,110.))):
            with self.subTest(z=start_z):
                h = Harness()
                self.addCleanup(h.close)
                h.position[2] = start_z
                h.gmove.reset_last_position()
                h.file_command('ZORTRAX_PRINT_END')
                h.stop_worker()
                h.control_until('IDLE')
                self.assertEqual(h.position[:3], [*expected_xy, 315.])
                self.assertEqual((h.hotend.target, h.bed.target), (0., 0.))
                self.assertEqual(h.sd.work_timer, 'native')

    def test_end_waits_for_slow_z_descent_before_xy_then_eof(self):
        h = self.h
        h.c.z_speed = 1.
        h.file_command('ZORTRAX_PRINT_END')
        h.stop_worker()
        h.control_until('ENDING', 'END_PARK')
        h.step_control()
        h.step_control(2.)
        self.assertEqual(h.position[:3], [100.,110.,310.])
        h.step_control(150.)
        self.assertEqual(h.c.state, 'ENDING')
        self.assertEqual(h.position[:2], [100.,110.])
        self.assertIsNone(h.sd.work_timer)
        h.step_control(151.)
        self.assertEqual(h.position[:3], [300.,305.,310.])
        self.assertIsNone(h.sd.work_timer)
        h.control_until('IDLE')
        self.assertEqual(h.sd.work_timer, 'native')

    def test_cancel_during_final_descent_revokes_end_and_never_resumes_the_file(self):
        h = self.h
        h.c.z_speed = 1.
        h.file_command('ZORTRAX_PRINT_END')
        h.stop_worker()
        h.control_until('ENDING', 'END_PARK')
        h.step_control()
        h.step_control(2.)
        self.assertTrue(h.c.waiting)
        h.run('CANCEL_PRINT')
        h.step_control()
        self.assertIsNone(h.sd.current_file)
        h.step_control(180.)
        self.assertEqual(h.c.phase, 'WAIT_CANCEL_DRAIN')
        h.control_until('IDLE')
        self.assertEqual(h.print_state, 'cancelled')
        self.assertNotIn(('native_resume',), h.events)

    def test_unhomed_z_refuses_end_motion_and_eof(self):
        h = self.h
        h.homed = 'xy'
        h.file_command('ZORTRAX_PRINT_END')
        h.stop_worker()
        h.step_control()
        self.assertEqual(h.c.state, 'FAILED')
        self.assertFalse(any(e[0] in ('move', 'native_resume') for e in h.events))
        self.assertEqual((h.hotend.target, h.bed.target), (0., 0.))

    def test_nonfinite_resume_and_start_temperatures_rejected(self):
        h=self.h
        with self.assertRaises(h.printer.command_error):h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=nan BED_TEMP=60')
        h.pause_print()
        with self.assertRaises(h.printer.command_error):h.run('RESUME VELOCITY=nan')

    def test_m25_uses_the_same_protected_pause(self):
        h=self.h;h.run('M25');h.stop_worker();h.control_until('PAUSED')
        self.assertEqual(h.position[:3],[100.,110.,15.])

    def test_dry_xy_only_file_resumes_without_inventing_nozzle_heat(self):
        h=self.h;h.hotend.target=0.;h.hotend.temperature=25.
        h.pause_print();self.assertEqual(h.c.context['retracted'],0.)
        h.run('RESUME');h.control_until('IDLE');self.assertEqual(h.hotend.target,0.)

    def test_bed_must_also_stabilize_before_return(self):
        h=self.h;h.pause_print();h.bed.temperature=40.;h.run('RESUME')
        h.step_control(4.);self.assertEqual(h.c.state,'RESUMING')
        self.assertEqual(h.position[:3],[100.,110.,15.]);self.assertIsNone(h.sd.work_timer)
        h.bed.temperature=60.;h.control_until('IDLE')

    def test_replaced_file_content_invalidates_resume(self):
        h=self.h;h.pause_print()
        Path(h.sd.current_file.name).write_text('G1 X1\n')
        with self.assertRaisesRegex(h.printer.command_error,'file identity'):h.run('RESUME')

    def test_external_xyz_change_invalidates_resume(self):
        h=self.h;h.pause_print();h.position[0]-=1.
        with self.assertRaisesRegex(h.printer.command_error,'parked position'):h.run('RESUME')

    def test_material_uses_original_target_after_standby(self):
        h=self.h;h.pause_print();h.step_control(600.)
        self.assertEqual(h.hotend.target,150.)
        h.run('ZORTRAX_CHANGE');h.control_until('PAUSED');self.assertEqual(h.f.target,240.)

    def test_pause_cooling_does_not_override_material_service_temperature(self):
        h=self.h;h.pause_print();h.run('ZORTRAX_CHANGE TEMP=250');h.control_until('PAUSED')
        self.assertEqual(h.hotend.target,240.);h.step_control(700.)
        self.assertEqual(h.hotend.target,240.)
        h.heat(h.f,'WAIT_INSERT');self.assertEqual(h.hotend.target,250.)

    def test_near_z_limit_refuses_material_service(self):
        h=self.h;h.position[2]=314.;h.gmove.reset_last_position();h.pause_print()
        with self.assertRaisesRegex(h.printer.command_error,'clearance'):h.run('ZORTRAX_CHANGE')

    def test_duplicate_change_during_parking_does_not_replace_explicit_temperature(self):
        h=self.h;h.run('ZORTRAX_CHANGE TEMP=250')
        with self.assertRaises(h.printer.command_error):h.run('M600')
        h.stop_worker();h.control_until('PAUSED');self.assertEqual(h.f.target,240.)
        h.heat(h.f,'WAIT_INSERT');self.assertEqual(h.hotend.target,250.)

    def test_change_from_plain_pause_reaches_corner_before_starting_with_custom_lengths(self):
        h = self.h
        h.pause_print()
        with self.assertRaisesRegex(h.printer.command_error, 'material-change park'):
            h.c.material_begin()
        with self.assertRaises(h.printer.command_error):
            h.run('CHANGE_FILAMENT LOAD_LENGTH=-1')
        self.assertEqual(h.c.state, 'PAUSED')
        h.run('CHANGE_FILAMENT TEMP=250 LOAD_LENGTH=30 UNLOAD_LENGTH=20')
        self.assertFalse(h.f.is_busy())
        h.step_control()
        self.assertEqual(h.position[:3], [300.,305.,15.])
        self.assertFalse(h.f.is_busy())
        h.control_until('PAUSED')
        self.assertTrue(h.f.is_busy())
        self.assertEqual(h.f.target, 240.)
        h.heat(h.f, 'WAIT_INSERT')
        self.assertEqual(h.hotend.target, 250.)
        plan = h.f.machine.plan
        self.assertEqual(plan['planned_mm']['load'], 30.)
        self.assertEqual(plan['planned_mm']['unload'], 20.)
        self.assertEqual(h.c.context['plan']['return_moves'], [[100.,110.,15.], [100.,110.,10.]])

    def test_cancel_during_material_park_never_starts_the_change_wizard(self):
        h = self.h
        h.pause_print()
        h.run('M600')
        h.step_control()
        h.run('CANCEL_PRINT')
        h.control_until('IDLE')
        self.assertEqual(h.print_state, 'cancelled')
        self.assertFalse(h.f.is_busy())
        self.assertNotIn(('native_resume',), h.events)

    def test_fluidd_cancel_revokes_heat_without_waiting_for_gcode_mutex(self):
        h=self.h;h.pause_print();h.hotend.temperature=25.;h.run('RESUME')
        def forbidden(script):raise AssertionError('cancel waited on G-code dispatch')
        h.gcode.run_script=forbidden
        with h.gcode.get_mutex():h.web._endpoints['pause_resume/cancel'](None)
        self.assertEqual(h.c.state,'CANCELLING');self.assertEqual(h.hotend.target,0.)
        h.control_until('IDLE');self.assertEqual(h.print_state,'cancelled')

    def test_oled_uses_native_status_while_busy_and_invalidates_old_pause_view(self):
        h=self.h;ui=M300PrintUI(h.config);ui._ready();h.pause_at_material_park()
        first=ui.view(h.now)[0]
        h.c.material_begin();h.c.material_complete(True)
        self.assertNotEqual(ui.view(h.now)[0],first)
        h.run('RESUME');self.assertIsNone(ui.view(h.now))

    def test_display_footer_restores_previous_message_when_procedure_finishes(self):
        h=self.h;h.objects['display_status'].message='Ready'
        h.pause_print();h.run('RESUME');h.control_until('IDLE')
        self.assertEqual(h.objects['display_status'].message,'Ready')

    def test_shutdown_during_homing_cannot_issue_a_purge_or_resume(self):
        h=self.h
        def home(*, filament_prepared):
            h.shutdown=True;h.c._stop('native homing cancelled')
        h.objects['m300_motion'].home=home
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60');h.stop_worker()
        h.control_until('STARTING', 'RETRACT_DRAIN')
        h.step_control(h.busy_until - h.now + .01)
        self.assertFalse(h.c.ready);self.assertNotIn(('native_resume',),h.events)
        self.assertEqual((h.hotend.target,h.bed.target),(0.,0.))

    def test_failed_heater_off_requests_native_shutdown_instead_of_restarting_file(self):
        h=self.h;h.pause_print()
        def fail():raise RuntimeError('PWM shutdown failure')
        h.objects['heaters'].turn_off_all_heaters=fail
        h.run('CANCEL_PRINT')
        self.assertTrue(h.shutdown);self.assertTrue(h.sd.must_pause_work)
        self.assertNotIn(('native_resume',),h.events)

    def test_start_purge_is_bounded_and_restores_existing_speed_and_flow(self):
        h=self.h;h.run('G91\nM82\nG92 E8\nM220 S150\nM221 S200')
        logical_e = h.gmove.get_status(h.now)['gcode_position'].e
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60');h.stop_worker()
        h.control_until('IDLE')
        self.assertAlmostEqual(h.gmove.speed_factor,1.5/60.)
        self.assertEqual(h.gmove.extrude_factor,2.)
        self.assertAlmostEqual(h.gmove.get_status(h.now)['gcode_position'].e, logical_e)
        self.assertFalse(h.gmove.absolute_coord)
        self.assertTrue(h.gmove.allow_absolute_extrude)
        # Two Y legs of 260 mm and two X legs of 250 mm; M221=200 must
        # not double the metered dose. Native parser state is then restored.
        expected=17.-10.+6.+(2.*260.+2.*250.)*h.c.purge_filament/h.c.purge_length
        self.assertAlmostEqual(h.position[3],expected,places=4)

    def test_oled_offers_reheat_after_material_nozzle_off_then_confirmation_then_resume(self):
        h=self.h;ui=M300PrintUI(h.config);ui._ready();h.pause_at_material_park()
        h.c.material_begin();h.c.material_complete(True)
        hot_key=ui.view(h.now)[0]
        self.assertEqual(ui.pause_rows(h.now)[0],('Confirm material flow','ready'))
        h.hotend.temperature=25.;h.hotend.target=0.
        self.assertEqual(ui.pause_rows(h.now)[0],('Heat nozzle to resume','resume'))
        self.assertNotEqual(hot_key,ui.view(h.now)[0])
        h.run('RESUME');h.hotend.temperature=240.;h.control_until('PAUSED','WAIT_FILAMENT_READY')
        self.assertEqual(ui.pause_rows(h.now)[0][1],'ready')
        h.run('FILAMENT_READY');self.assertEqual(ui.pause_rows(h.now)[0][1],'resume')

    def test_start_refuses_active_fan_test_but_allows_normal_thermostat_updates(self):
        h=self.h;h.objects['m300_fans']=NS(test={'channel':'BOTH'})
        with self.assertRaisesRegex(h.printer.command_error,'m300_fans owns resources'):
            h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        self.assertEqual(h.c.state,'IDLE');self.assertFalse(h.sd.must_pause_work)
        h.objects['m300_fans'].test=None
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        self.assertEqual(h.c.state,'STARTING')

    def test_cancel_without_an_active_print_does_not_move_the_printer(self):
        h=self.h;h.sd.current_file.close();h.sd.current_file=None
        h.sd.work_timer=None;h.print_state='standby'
        h.run('CANCEL_PRINT');h.control_until('IDLE')
        self.assertEqual(h.position[:3],[100.,110.,10.])
        self.assertFalse(any(e[0]=='move' for e in h.events))

    def test_auto_mesh_without_a_saved_profile_preserves_machine_and_refuses_start(self):
        h=self.h;h.objects['bed_mesh'].pmgr.get_profiles=lambda:{}
        h.mesh=NS(mesh_offsets=[0.,0.])
        with self.assertRaisesRegex(h.printer.command_error,'saved bed mesh'):
            h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        self.assertIsNotNone(h.mesh)
        self.assertFalse(h.c.busy)
        self.assertEqual(h.events,[])

    def test_full_platform_preheat_holds_both_targets_before_any_homing(self):
        h=self.h;h.objects['m300_nvm']=NS(get_setting=lambda name,default:True)
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60');h.stop_worker()
        h.control_until('STARTING','PLATFORM_SOAK')
        start=h.now
        for _ in range(4):h.step_control(10.)
        self.assertFalse(any(e[0]=='home' for e in h.events))
        self.assertEqual((h.hotend.target,h.bed.target),(240.,60.))
        h.control_until('IDLE');self.assertGreaterEqual(h.now-start,60.)

    def test_platform_soak_restarts_continuous_stability_after_temperature_excursion(self):
        h=self.h;h.objects['m300_nvm']=NS(get_setting=lambda name,default:True)
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60');h.stop_worker()
        h.control_until('STARTING','PLATFORM_SOAK');h.step_control(30.)
        h.bed.temperature=55.;h.step_control();self.assertIsNone(h.c.stable_since)
        h.bed.temperature=60.;h.step_control();h.step_control(40.)
        self.assertFalse(any(e[0]=='home' for e in h.events))
        h.control_until('IDLE')

    def test_cancel_during_soak_never_homes_or_reheats(self):
        h=self.h;h.objects['m300_nvm']=NS(get_setting=lambda name,default:True,
                                        runtime_drained=lambda now:None)
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60');h.stop_worker()
        h.control_until('STARTING','PLATFORM_SOAK');h.run('CANCEL_PRINT');h.control_until('IDLE')
        h.step_control(600.)
        self.assertFalse(any(e[0]=='home' for e in h.events))
        self.assertEqual((h.hotend.target,h.bed.target),(0.,0.));self.assertEqual(h.print_state,'cancelled')

    def test_full_preheat_choice_is_captured_once_for_the_new_session(self):
        h=self.h;choice=[True]
        h.objects['m300_nvm']=NS(get_setting=lambda name,default:choice[0])
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60');choice[0]=False
        h.stop_worker();h.control_until('STARTING','PLATFORM_SOAK')
        self.assertEqual(h.c.operation['soak_seconds'],60.)

    def test_no_bed_target_does_not_request_a_pointless_soak(self):
        h=self.h;h.objects['m300_nvm']=NS(get_setting=lambda name,default:True)
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=0');h.stop_worker();h.control_until('IDLE')
        self.assertEqual(h.bed.target,0.)

    def test_soak_uses_the_existing_finite_heat_deadline(self):
        h=self.h;h.objects['m300_nvm']=NS(get_setting=lambda name,default:True)
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60');h.stop_worker();h.step_control()
        deadline=h.c.deadline;h.control_until('STARTING','PLATFORM_SOAK')
        self.assertEqual(h.c.deadline,deadline)
        h.bed.temperature=55.;h.step_control(h.c.heat_timeout+1.)
        self.assertEqual(h.c.state,'FAILED');self.assertEqual(h.bed.target,0.)


if __name__=='__main__':unittest.main()
