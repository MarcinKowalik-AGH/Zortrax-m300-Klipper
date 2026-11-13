"""Independent OEM execution fixtures versus full native procedure sessions."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch, PropertyMock

import test_display
from test_native_oem_services import Harness, physical_panel
from test_native_leveling import Harness as ContactHarness, homing
from test_normal_operations import motion_fixture
from tests.reference import native_gcode
from payload.m300_leveling_state import LevelingState, CalibrationError
from payload.m300_stock_geometry import stock_xy_offsets
from payload.m300_native_z import M300ZRefinement
from payload.m300_menu_ui import M300MenuUI
from payload.m300_nvm import M300NVM
from payload.m300_ui_m11_state import MenuHistory


REFERENCE=json.loads((Path(__file__).parent/'reference/firmware131_procedures.json').read_text())


def paused_print(h,target=230.):
    h.homed='xyz';h.print_state='printing';h.hotend.target=target
    h.run('PAUSE')
    assert h.pause.is_paused and h.print_state=='paused'
    h.events.clear()


class FirmwareMaterialContractTests(unittest.TestCase):
    def test_status_polling_does_not_copy_the_full_segment_plan(self):
        h=Harness();h.run('ZORTRAX_LOAD')
        full=h.f.machine.snapshot()
        with patch.object(type(h.f.machine),'plan',new_callable=PropertyMock,
                          side_effect=AssertionError('full plan copied during polling')):
            status=h.f.get_status(h.now)
        self.assertEqual(status['budget_mm'],full['plan']['total_budget_mm'])
        self.assertEqual(status['completed_mm'],full['completed_mm'])

    def test_original_prompt_order_and_nominal_lengths_match_native_macros(self):
        for original in REFERENCE['material']:
            if not original['accept']:continue
            h=Harness();operation=original['operation']
            if operation=='CHANGE':paused_print(h)
            h.run('ZORTRAX_'+operation);h.hotend.temperature=h.hotend.target
            seen=[]
            for _ in range(3000):
                view=h.p.view(h.now);screen=view.get('leveling_screen')
                tid=screen.get('text_id') if screen else None
                if tid in (19,20,21,22) and (not seen or seen[-1]!=tid):seen.append(tid)
                if h.f.get_status(h.now)['can_confirm']:
                    h.p.action(view['view_id'],'CONFIRM')
                if h.f.machine.state=='COMPLETE':break
                h.step()
            self.assertFalse(h.shutdown)
            self.assertEqual(h.f.machine.state,'COMPLETE')
            expected=[e['text_id'] for e in original['events'] if e['kind']=='dialog']
            self.assertEqual(seen,expected,operation)
            nominal=[p/960. for p in original['requested_pulses']]
            self.assertAlmostEqual(h.f.machine.completed_mm,sum(abs(p) for p in nominal))
            self.assertAlmostEqual(h.position[3]-17.,sum(nominal))
            self.assertEqual(h.position[:3],[150.,158.,5.])
            h.assert_restored(self)

    def test_cancelled_original_prompts_have_no_native_transport(self):
        for original in REFERENCE['material']:
            if original['accept']:continue
            h=Harness();h.run('ZORTRAX_'+original['operation'])
            h.heat(h.f,'WAIT_INSERT' if original['operation']=='LOAD' else 'WAIT_UNLOAD')
            view=h.p.view(h.now);h.p.action(view['view_id'],'CANCEL')
            h.until(h.f,'CANCELLED')
            self.assertEqual(original['requested_pulses'],[])
            self.assertEqual(h.position[3],17.)
            self.assertEqual(h.hotend.target,0.);h.assert_restored(self)

    def test_unload_heater_off_is_an_explicit_port_difference(self):
        original=next(m for m in REFERENCE['material'] if m['operation']=='UNLOAD' and m['accept'])
        self.assertFalse(any(e['kind']=='target' for e in original['events']))
        h=Harness();h.run('ZORTRAX_UNLOAD');h.heat(h.f,'WAIT_UNLOAD')
        h.f.confirm(h.f.machine.token,h.f.machine.phase_id);h.until(h.f,'COMPLETE')
        self.assertEqual(h.hotend.target,0.)

    def test_readiness_is_a_minimum_threshold_at_238_including_small_overshoot(self):
        for measured,ready in ((237.9,False),(238.,True),(244.,True)):
            h=Harness();h.run('ZORTRAX_UNLOAD');h.hotend.temperature=measured
            for _ in range(25):h.step()
            self.assertEqual(h.f.machine.state=='WAIT_UNLOAD',ready)
            self.assertEqual(h.position[3],17.)


class NativeChangeTests(unittest.TestCase):
    def test_change_preserves_real_pause_state_and_never_resumes_automatically(self):
        h=Harness();paused_print(h,230.)
        saved=copy.deepcopy(h.gmove.saved_states['PAUSE_STATE'])
        h.run('ZORTRAX_CHANGE');self.assertEqual(h.hotend.target,230.)
        h.heat(h.f,'WAIT_INSERT')
        self.assertEqual(h.position[3],-93.)
        self.assertEqual(h.gmove.saved_states['PAUSE_STATE'],saved)
        with self.assertRaisesRegex(native_gcode.CommandError,'owns resources'):
            h.run('RESUME')
        view=h.p.view(h.now);h.p.action(view['view_id'],'CONFIRM');h.until(h.f,'COMPLETE')
        self.assertEqual(h.position[3],57.)
        self.assertEqual(h.gmove._get_gcode_position()[3],17.)
        self.assertEqual(h.gmove.saved_states['PAUSE_STATE'],saved)
        self.assertTrue(h.pause.is_paused)
        self.assertEqual(h.print_state,'paused')
        self.assertEqual(h.hotend.target,230.)
        self.assertFalse(any(e==('native_print','printing') for e in h.events))
        h.assert_restored(self)
        h.run('RESUME')
        self.assertFalse(h.pause.is_paused);self.assertEqual(h.print_state,'printing')

    def test_change_macro_and_m600_require_an_already_paused_native_print(self):
        for state in ('standby','printing'):
            for command in ('ZORTRAX_CHANGE','M600'):
                h=Harness();h.print_state=state
                with self.assertRaisesRegex(native_gcode.CommandError,'pause the native print'):
                    h.run(command)
                self.assertEqual(h.hotend.target,0.)
                self.assertFalse(h.f.machine.active);h.assert_restored(self)

    def test_m600_in_paused_print_uses_the_same_change_without_auto_resume(self):
        h=Harness();paused_print(h)
        h.run('M600');h.heat(h.f,'WAIT_INSERT')
        self.assertEqual(h.f.machine.mode,'CHANGE')
        self.assertEqual(h.position[3],-93.)
        self.assertTrue(h.pause.is_paused)

    def test_cancel_during_change_leaves_print_paused_and_heater_off(self):
        h=Harness();paused_print(h)
        h.run('ZORTRAX_CHANGE');h.heat(h.f,'WAIT_INSERT')
        view=h.p.view(h.now);h.p.action(view['view_id'],'CANCEL');h.until(h.f,'CANCELLED')
        self.assertEqual(h.hotend.target,0.)
        self.assertTrue(h.pause.is_paused);self.assertEqual(h.print_state,'paused')
        self.assertFalse(any(e==('native_print','printing') for e in h.events))
        h.assert_restored(self)

    def test_cancel_print_during_change_drains_without_resume_or_fake_position(self):
        h=Harness();paused_print(h)
        h.run('ZORTRAX_CHANGE');h.heat(h.f,'WAIT_INSERT')
        h.run('CANCEL_PRINT');h.until(h.f,'CANCELLED')
        self.assertEqual(h.print_state,'cancelled')
        self.assertFalse(h.pause.is_paused);self.assertEqual(h.hotend.target,0.)
        self.assertEqual(h.position[:3],[150.,158.,5.])
        h.assert_restored(self)

    def test_paused_file_identity_change_revokes_change_session(self):
        h=Harness();paused_print(h)
        h.run('ZORTRAX_CHANGE');h.heat(h.f,'WAIT_INSERT')
        h.file_position+=1;h.until(h.f,'CANCELLED')
        self.assertEqual(h.hotend.target,0.)
        self.assertEqual(h.position[3],-93.)
        self.assertFalse(h.shutdown);h.assert_restored(self)

    def test_paused_oled_print_menu_exposes_change_macro(self):
        from test_native_menu import fixture
        menu,objects=fixture();menu.page='native_job'
        objects['print_stats']=NS(get_status=lambda now:dict(state='paused'))
        self.assertIn(('Change the material',('native_gcode','ZORTRAX_CHANGE')),menu.rows(1.)[1])


class FirmwareLevelingContractTests(unittest.TestCase):
    def test_native_printing_or_pause_refuses_m07_before_heating_or_homing(self):
        for state in ('printing','paused'):
            h=ContactHarness()
            h.objects['print_stats']=NS(get_status=lambda now:dict(state=state))
            before=h.position[:]
            with self.assertRaisesRegex(RuntimeError,'idle native print'):h.c.start()
            self.assertEqual(h.c.machine.state,'IDLE')
            self.assertEqual(h.position,before);self.assertEqual(h.hotend.target,0.)
            self.assertFalse(any(e[0] in ('home','contact','move') for e in h.events))

    def test_connector_guard_failure_refuses_m07_before_any_actuation(self):
        h=ContactHarness()
        def fault():raise RuntimeError('platform connector fault')
        h.job.board.require_motion=fault
        with self.assertRaisesRegex(RuntimeError,'platform connector fault'):h.c.start()
        self.assertEqual(h.c.machine.state,'IDLE')
        self.assertEqual(h.hotend.target,0.)
        self.assertFalse(any(e[0] in ('home','contact','move') for e in h.events))

    def test_failed_initial_pad_contact_is_error_042_and_cannot_publish_height(self):
        original=next(w for w in REFERENCE['wizard'] if w.get('pad_error'))
        self.assertIn(dict(kind='failure',error=42),original['events'])
        self.assertFalse(any(e['kind']=='probe' for e in original['events']))
        h=ContactHarness();h.record={'prior':'kept'}
        h.motion.home_oem=Mock(side_effect=RuntimeError('No trigger on PC7 during initial contact'))
        h.c.start();h.until('WAIT_WARNING')
        with self.assertRaises(RuntimeError):h.confirm()
        self.assertEqual(h.c.machine.state,'FAULT')
        self.assertEqual(h.record,{'prior':'kept'})
        self.assertEqual(h.c.machine.current,{})
        self.assertEqual(h.hotend.target,0.)

    def test_all_nominal_points_and_offsets_match_the_original_program(self):
        for item in REFERENCE['xy_offsets']:
            self.assertEqual(list(stock_xy_offsets(item['seed'])),item['xy'])
        h=ContactHarness();nominal=tuple(h.c.points);h.c.start()
        offset=stock_xy_offsets(1000)
        self.assertEqual(h.c.xy_offset,offset)
        self.assertEqual(h.c.points,tuple((x+offset[0],y+offset[1]) for x,y in nominal))
        self.assertEqual(nominal,((269.,44.),(35.,44.),(150.,158.),(269.,275.),(35.,275.)))

    def test_original_wizard_probe_and_instruction_trace_matches_pure_native_contract(self):
        original=next(w for w in REFERENCE['wizard'] if w['converge'])
        expected=[]
        for event in original['events']:
            if event['kind']=='probe':expected.append(('point',event['point']))
            elif event['kind']=='instruction':expected.append(('turns',event['turns']))
        machine=LevelingState(samples=1,stock_steps_per_mm=400,
            directions={s:'CCW' for s in ('rear_left','rear_right','front')})
        token=machine.start(0.);machine.confirm(token,machine.phase_id,0.);machine.heated(token,0.)
        heights={0:160,1:0,4:0,3:20,2:160};actual=[]
        for _ in range(40):
            if machine.state=='PROBING':
                point=machine.next_point;actual.append(('point',point))
                machine.measured(token,machine.phase_id,point,[heights[point]/400.],1.)
            elif machine.state=='ADJUST':
                instruction=machine.instruction;actual.append(('turns',instruction['turns']))
                for point in {'rear_left':[4],'rear_right':[3],'front':[0,1]}[instruction['screw']]:heights[point]=160
                machine.confirm(token,machine.phase_id,1.)
            else:break
        self.assertEqual(actual,expected)
        self.assertEqual(machine.state,'REVIEW')
        self.assertEqual(machine.reference_raw,160)

    def test_original_and_port_bound_nonconverging_adjustments_at_forty(self):
        original=next(w for w in REFERENCE['wizard'] if not w['converge'])
        self.assertEqual(sum(e['kind']=='instruction' for e in original['events']),40)
        self.assertEqual(original['events'][-1],dict(kind='failure',error=41))
        machine=LevelingState(samples=1,stock_steps_per_mm=400,
            directions={s:'CCW' for s in ('rear_left','rear_right','front')})
        token=machine.start(0.);machine.confirm(token,machine.phase_id,0.);machine.heated(token,0.)
        heights={0:160,1:0,4:0,3:20,2:160}
        with self.assertRaises(CalibrationError):
            for _ in range(150):
                if machine.state=='PROBING':
                    p=machine.next_point;machine.measured(token,machine.phase_id,p,[heights[p]/400.],1.)
                else:machine.confirm(token,machine.phase_id,1.)
        self.assertEqual(len(machine.corrections),40)
        self.assertEqual(machine.state,'FAULT')

    def test_oem_calibration_homes_y_then_x_and_uses_its_offset_center(self):
        m=motion_fixture();m.homed.clear();m.hotend.target=260.
        m.hotend.measured = 260.
        m.hotend.check_busy = Mock(return_value=False)
        m.precision.run=Mock(side_effect=AssertionError('ordinary five-contact routine is not the M07 coarse contact'))
        m.home_oem((151.,161.))
        self.assertEqual([e[1] for e in m.events if e[0]=='home'],['Y','X','Z'])
        self.assertIn(('move',(151.,161.,None),50.),m.events)
        self.assertEqual([e for e in m.events if e[0]=='heat'],[('heat',260.,False)])
        m.hotend.check_busy.assert_called_once()
        m.precision.check_temperature.assert_not_called()
        m.precision.run.assert_not_called()

    def test_m07_ready_threshold_accepts_258_and_safe_overshoot(self):
        for temperature,ready in ((257.9,False),(258.,True),(265.,True)):
            h=ContactHarness();h.c.start();h.hotend.temperature=temperature
            for _ in range(4):h.now+=.1;h.c._tick(h.now)
            self.assertEqual(h.c.machine.state=='WAIT_WARNING',ready)


def precision_harness(profile, early_releases=()):
    h=ContactHarness(profile['steps_per_mm']);scale=profile['steps_per_mm']
    h.position=[150.,158.,0.,17.];h.stepper.actual=0;h.stepper.offset=0.
    h.level=True;index=[-1]
    contact_raw=[e['contact_raw']-1500 for e in profile['events']]
    h.kin.rails=[NS(get_range=lambda:(0.,305.)),NS(get_range=lambda:(0.,305.)),NS(get_range=lambda:(0.,315.))]
    def manual_move(position,speed):
        full=list(h.position)
        for axis,value in enumerate(position):
            if value is not None:full[axis]=value
        h.move(full,speed)
    h.toolhead.manual_move=manual_move
    old_start=h.home_start
    def start(*args,triggered=True,**kwargs):
        if triggered:index[0]+=1
        return old_start(*args,triggered=triggered,**kwargs)
    h.endstop.home_start=start
    def query(now):
        if index[0]>=0 and h.no_release:return True
        if index[0]>=0 and h.no_contact:return False
        return h.stepper.actual<=contact_raw[max(0,index[0])]
    h.endstop.query_endstop=query
    releases=[0]
    def drip(target,speed,completion):
        before=h.position[2]
        if not h.triggered:
            releases[0]+=1
            if releases[0] in early_releases:
                h.trigger_time=h.now
                h.level=False
                h.events.append(('contact',False,target[2],before))
                return
        level=(contact_raw[index[0]]+(0 if h.triggered else 1))/scale+h.stepper.offset
        success=(not h.no_contact and target[2]<=level<before if h.triggered else
                 not h.no_release and before<level<=target[2])
        value=level if success else target[2]
        h.stepper.actual=round((value-h.stepper.offset)*scale)
        h.trigger_time=h.now if success else 0.
        h.level=success if h.triggered else not success
        h.events.append(('contact',h.triggered,target[2],value))
        if h.on_drip:
            cb,h.on_drip=h.on_drip,None;cb()
    h.toolhead.drip_move=drip
    owner=NS(printer=h.printer,toolhead=h.toolhead,reactor=h.reactor,lift_speed=5.,
        _z_target=180.,z_home_hotend_target=180.,z_home_temperature_tolerance=5.,
        config=NS(error=RuntimeError),
        board=NS(require_motion=lambda:None,require_heating=lambda:None,
                 hardware=NS(get_status=lambda:dict(effective_z_steps_per_mm=scale))),
        hotend=NS(get_temp=lambda now:(180.,180.)),
        _check=lambda token:(_ for _ in ()).throw(RuntimeError('session invalidated')) if h.shutdown else None)
    ref=M300ZRefinement(owner,NS(get_offsets=lambda:(0.,0.,0.),mcu_probe=NS(mcu_endstop=h.endstop)))
    return h,ref


class NativeFiveContactTests(unittest.TestCase):
    def test_early_release_discards_the_pair_and_retries_at_both_factory_scales(self):
        for profile in REFERENCE['z_references']:
            for retries in (1,2):
                with self.subTest(scale=profile['steps_per_mm'],retries=retries):
                    expanded=copy.deepcopy(profile)
                    expanded['events']=([profile['events'][0]]*retries+expanded['events'])
                    h,ref=precision_harness(expanded,range(1,retries+1))
                    with patch.dict('sys.modules',{'payload.homing':homing}):
                        result=ref.run(1)
                    self.assertEqual(result['contacts'],5)
                    self.assertEqual(result['release_retries'],[
                        dict(iteration=1,attempt=i+1) for i in range(retries)])
                    self.assertAlmostEqual(result['final_reference_mm'],
                        (profile['result_raw']-1500)/profile['steps_per_mm'])
                    self.assertEqual([r['iteration'] for r in result['references']],list(range(1,6)))
                    self.assertTrue(all(r['release_mm']>r['contact_mm'] for r in result['references']))
                    self.assertEqual(len([e for e in h.events if e[0]=='contact']),2*(5+retries))
                    self.assertEqual(h.position[:2],[150.,158.])
                    self.assertEqual(h.position[3],17.)

    def test_repeated_early_release_has_three_attempts_and_no_accepted_reference(self):
        h,ref=precision_harness(REFERENCE['z_references'][1],(1,2,3))
        with patch.dict('sys.modules',{'payload.homing':homing}),self.assertRaisesRegex(
                RuntimeError,'PC7 opened before movement in 3 attempts'):
            ref.run(1)
        self.assertEqual(ref.references,[])
        self.assertEqual(len(ref.retry_events),3)
        self.assertEqual(len([e for e in h.events if e[0]=='contact']),6)
        self.assertFalse(h.endstop.query_endstop(h.now))

    def test_early_release_cannot_retry_with_contact_still_closed_after_retreat(self):
        h,ref=precision_harness(REFERENCE['z_references'][1],(1,))
        query=h.endstop.query_endstop
        h.endstop.query_endstop=lambda now: (True if ref.retry_events else query(now))
        with patch.dict('sys.modules',{'payload.homing':homing}),self.assertRaisesRegex(
                RuntimeError,'PC7 reclosed after full retreat'):
            ref.run(1)
        self.assertEqual(ref.references,[])
        self.assertEqual(len([e for e in h.events if e[0]=='contact']),2)

    def test_approach_without_movement_remains_a_failure_and_never_retries(self):
        h,ref=precision_harness(REFERENCE['z_references'][1])
        def early_contact(target,speed,completion):
            h.trigger_time=h.now
            h.events.append(('contact',h.triggered,target[2],h.position[2]))
        h.toolhead.drip_move=ref.drip=early_contact
        with patch.dict('sys.modules',{'payload.homing':homing}),self.assertRaisesRegex(
                RuntimeError,'PC7 transition occurred without movement'):
            ref.run(1)
        self.assertEqual(ref.references,[])
        self.assertEqual(ref.retry_events,[])
        self.assertEqual(len([e for e in h.events if e[0]=='contact']),1)

    def test_retry_keeps_the_original_iteration_deadline(self):
        h,ref=precision_harness(REFERENCE['z_references'][1],(1,2))
        ref.timeout=2.5
        def dwell(delay):
            h.now+=delay
        h.toolhead.dwell=dwell
        with patch.dict('sys.modules',{'payload.homing':homing}),self.assertRaisesRegex(
                RuntimeError,'deadline'):
            ref.run(1)
        self.assertEqual(ref.references,[])
        self.assertEqual(len(ref.retry_events),2)

    def test_restart_during_retry_retreat_prevents_another_approach(self):
        h,ref=precision_harness(REFERENCE['z_references'][1],(1,))
        wait=h.toolhead.wait_moves
        def cancelled_wait():
            wait()
            if ref.retry_events:h.shutdown=True
        h.toolhead.wait_moves=cancelled_wait
        with patch.dict('sys.modules',{'payload.homing':homing}),self.assertRaisesRegex(
                RuntimeError,'session invalidated'):
            ref.run(1)
        self.assertEqual(ref.references,[])
        self.assertEqual(len([e for e in h.events if e[0]=='contact']),2)

    def test_five_contacts_accept_a_shortfall_to_the_configured_lower_limit(self):
        for measured, target in ((176., 180.), (175., 180.), (181., 240.), (175., 240.)):
            with self.subTest(measured=measured, target=target):
                h, ref = precision_harness(REFERENCE['z_references'][1])
                ref.owner._z_target = target
                ref.owner.hotend.get_temp = lambda now: (measured, target)
                with patch.dict('sys.modules', {'payload.homing': homing}):
                    self.assertEqual(ref.run(1)['contacts'], 5)

    def test_bad_temperature_or_changed_target_refuses_motion_with_specific_reason(self):
        for measured, target, tolerance, reason in (
                (174.9, 180., 5., '174.90 C below contact minimum 175.00 C'),
                (177., 180., 2., '177.00 C below contact minimum 178.00 C'),
                (0., 180., 5., 'no valid nozzle temperature'),
                (float('nan'), 180., 5., 'no valid nozzle temperature'),
                (180., 0., 5., 'nozzle target changed from 180.0 C to 0.0 C')):
            with self.subTest(measured=measured, target=target, tolerance=tolerance):
                h, ref = precision_harness(REFERENCE['z_references'][1])
                ref.owner.z_home_temperature_tolerance = tolerance
                ref.owner.hotend.get_temp = lambda now: (measured, target)
                with self.assertRaises(RuntimeError) as error:
                    ref.run(1)
                self.assertIn(reason, str(error.exception))
                self.assertEqual(ref.references, [])
                self.assertFalse(any(e[0] in ('move', 'contact') for e in h.events))

    def test_reclosing_pc7_after_full_retreat_is_not_accepted_as_a_reference(self):
        h,ref=precision_harness(REFERENCE['z_references'][1])
        query=h.endstop.query_endstop
        def reclosed(now):
            released=any(e[0]=='contact' and e[1] is False for e in h.events)
            return True if released and h.position[2]>=2. else query(now)
        h.endstop.query_endstop=reclosed
        with patch.dict('sys.modules',{'payload.homing':homing}),self.assertRaisesRegex(RuntimeError,'NO_RELEASE'):
            ref.run(1)
        self.assertEqual(ref.references,[])

    def test_five_native_homing_moves_use_last_release_not_mean_for_both_factory_scales(self):
        for profile in REFERENCE['z_references']:
            h,ref=precision_harness(profile)
            with patch.dict('sys.modules',{'payload.homing':homing}):result=ref.run(1)
            scale=profile['steps_per_mm']
            expected=(profile['result_raw']-1500)/scale
            mean=sum((e['release_raw']-1500)/scale for e in profile['events'])/5.
            self.assertEqual(result['contacts'],5)
            self.assertFalse(result['averaging'])
            self.assertAlmostEqual(result['final_reference_mm'],expected)
            self.assertNotAlmostEqual(result['final_reference_mm'],mean)
            self.assertEqual(len([e for e in h.events if e[0]=='contact']),10)
            self.assertEqual(h.position[:2],[150.,158.]);self.assertEqual(h.position[3],17.)
            self.assertAlmostEqual(h.position[2],1.)

    def test_missing_contact_or_release_cannot_produce_an_accepted_reference(self):
        for fault in ('no_contact','no_release'):
            h,ref=precision_harness(REFERENCE['z_references'][1]);setattr(h,fault,True)
            with patch.dict('sys.modules',{'payload.homing':homing}),self.assertRaisesRegex(RuntimeError,'No trigger'):
                ref.run(1)
            self.assertEqual(ref.references,[])
            self.assertTrue(0.<=h.position[2]<=315.)

    def test_unmapped_probe_cannot_authorize_a_reference_or_a_move(self):
        h,ref=precision_harness(REFERENCE['z_references'][1])
        h.endstop.get_steppers=lambda:[]
        with self.assertRaisesRegex(RuntimeError,'one native Z stepper'):ref.run(1)
        self.assertFalse(any(e[0]=='move' for e in h.events))

    def test_restart_during_native_contact_revokes_its_retained_capability(self):
        h,ref=precision_harness(REFERENCE['z_references'][1])
        h.on_drip=lambda:setattr(h,'shutdown',True)
        with patch.dict('sys.modules',{'payload.homing':homing}),self.assertRaisesRegex(RuntimeError,'session invalidated'):
            ref.run(1)
        self.assertEqual(ref.references,[])

    def test_deadline_is_checked_after_native_drain_before_another_contact(self):
        h,ref=precision_harness(REFERENCE['z_references'][1])
        h.on_wait=lambda:setattr(h,'now',h.now+ref.timeout+1.)
        with self.assertRaisesRegex(RuntimeError,'deadline'):ref.run(1)
        self.assertFalse(any(e[0]=='contact' for e in h.events))

    def test_normal_homing_faults_on_refinement_failure_and_cuts_owned_heat(self):
        m=motion_fixture();m.precision.run=Mock(side_effect=RuntimeError('NO_RELEASE'))
        m.printer.invoke_shutdown=Mock()
        with self.assertRaisesRegex(RuntimeError,'NO_RELEASE'):m.home(axes='z')
        m.printer.invoke_shutdown.assert_called_once_with('M300 precision Z reference failed: NO_RELEASE')
        self.assertEqual(m.state,'FAULT');self.assertEqual(m.hotend.target,0.)


class EnglishOnlyTests(unittest.TestCase):
    def test_legacy_nvm_language_does_not_change_visible_runtime_language(self):
        ui=M300MenuUI.__new__(M300MenuUI);ui.nvm=NS(get_setting=lambda *args:'PL')
        self.assertEqual(ui.language(),'EN')
        self.assertEqual(MenuHistory(4).translate('Maintenance','PL',
                         {'Maintenance':{'pl':'Konserwacja'}}),'Maintenance')
        h=Harness();h.language='PL';h.run('ZORTRAX_UNLOAD');h.heat(h.f,'WAIT_UNLOAD')
        view=h.p.view(h.now);self.assertEqual(view['leveling_screen']['language'],'EN')
        self.assertIn('Press button',view['message'])

    def test_nvm_preserves_legacy_settings_but_exposes_and_accepts_only_english(self):
        saved=dict(language='PL',light_mode='WHITE',sleep_mode='15MIN')
        n=M300NVM.__new__(M300NVM);n._busy=False;n._deferred_settings={};n._runtime_error=None
        n.printer=NS(command_error=RuntimeError)
        n.store=NS(_published={'settings':saved},source='existing',warnings=[])
        n.snapshot=lambda:copy.deepcopy(n.store._published)
        self.assertEqual(n.get_setting('language'),'EN')
        self.assertEqual(n.get_setting('light_mode'),'WHITE')
        status=n.get_status(1.)
        self.assertEqual(status['setting_choices']['language'],[{'value':'EN','label':'English'}])
        self.assertEqual(saved['language'],'PL')
        with self.assertRaisesRegex(RuntimeError,'English only'):n.set_setting('language','PL')

    def test_runtime_prompts_ignore_a_non_english_saved_language_and_close_on_completion(self):
        h=Harness();h.language='DE';o,menu,ui,display,packet=physical_panel(h)
        menu.page='material';o.selection=0
        h.run('ZORTRAX_UNLOAD');h.heat(h.f,'WAIT_UNLOAD')
        self.assertEqual(h.p.view(h.now)['leveling_screen']['language'],'EN')
        view=h.p.view(h.now);h.p.action(view['view_id'],'CONFIRM');h.until(h.f,'COMPLETE')
        self.assertEqual(menu.page,'material')
        self.assertEqual(h.lines[-1],'// action:prompt_end')


if __name__=='__main__':unittest.main()
