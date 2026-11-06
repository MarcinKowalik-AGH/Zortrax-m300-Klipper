"""Regression coverage for the optional Classic M300 pad mesh adapter."""
from types import SimpleNamespace as NS
import statistics
import unittest

from payload.m300_calibration_state import POINTS
from payload.m300_native_service import native_service_frame
from payload.m300_pad_mesh import (GEOMETRY_DEFAULTS, GRID_COUNT, M300PadMesh,
                                   fit_pad_points, geometry_points, mesh_bounds, pad_points,
                                   pad_triangles, preparation_targets, surface_grid)


class PadMeshTests(unittest.TestCase):
    def preflight_case(self, homed=''):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.geometry = dict(GEOMETRY_DEFAULTS, edge_margin=16.)
        mesh.points = geometry_points(mesh.geometry)
        mesh._error = ValueError
        mesh.busy,mesh.state,mesh.report=False,'IDLE',None
        mesh.phase,mesh.cancelled='IDLE',False
        mesh.heat_timeout=60.
        mesh.max_bed_span,mesh.max_pad_spread=.5,None
        events,clock,freeze = [],[0.],[False]
        limits = dict(homed_axes=homed, axis_minimum=(0.,0.,0.), axis_maximum=(300.,305.,315.))
        position = [150.,158.,5. if 'z' in homed else 315.,0.]
        contact = [False]
        def query(when):
            events.append('contact')
            return contact[0]
        endstop = NS(query_endstop=query, get_steppers=lambda:[NS(get_name=lambda:'stepper_z')])
        temps = dict(hotend=(185.,185.),bed=(60.,60.))
        def pause(until):
            events.append('pause')
            clock[0]=until
            if not freeze[0]:
                for name,(actual,target) in temps.items():
                    temps[name]=(actual+max(-20.,min(20.,target-actual)),target)
            return until
        mesh.reactor = NS(monotonic=lambda:clock[0],pause=pause)
        board = NS(native_control=True,mcu=NS(is_fileoutput=lambda:False),
                   require_motion=lambda:events.append('motion_ready'),
                   require_heating=lambda:events.append('heating_ready'))
        def heater(name):
            def set_temp(target):
                events.append(('heat',name,target))
                temps[name]=(temps[name][0],target)
            return NS(set_temp=set_temp,get_temp=lambda now:temps[name],
                      min_temp=0.,max_temp=300. if name=='hotend' else 120.)
        job = NS(board=board,service_busy=lambda:False,get_status=lambda now:dict(busy=False),
                 _temperatures=lambda now:dict(temps),hotend=heater('hotend'),bed=heater('bed'))
        def clear_homing_state(axes):
            limits['homed_axes']=''.join(axis for axis in limits['homed_axes'] if axis not in axes)
        kin = NS(get_status=lambda now:dict(limits),clear_homing_state=clear_homing_state)
        toolhead = NS(get_kinematics=lambda:kin,get_position=lambda:position[:],
                      get_last_move_time=lambda:0.,wait_moves=lambda:events.append('wait'),
                      register_lookahead_callback=lambda callback:events.append('flush'))
        active_mesh = [None]
        def set_mesh(value):active_mesh[0]=value;events.append('clear_mesh')
        bedmesh = NS(get_mesh=lambda:active_mesh[0],set_mesh=set_mesh)
        def home(axes):
            events.append(('home',axes))
            limits['homed_axes']=''.join(axis for axis in 'xyz' if axis in limits['homed_axes']+axes)
            if 'z' in axes:position[2]=5.
            contact[0]=False
        objects = {'m300_job':job,'toolhead':toolhead,'gcode_move':NS(move_transform=bedmesh),
            'probe':NS(get_offsets=lambda:(0.,0.,0.),
                       mcu_probe=NS(mcu_endstop=endstop,homing_helper=NS(z_min_position=0.))),
            'm300_motion':NS(home=home,z_home_hotend_target=180.,ensure_xy_clearance=lambda check:check())}
        mesh.bedmesh = bedmesh
        mesh.gcode = NS(respond_info=lambda message:events.append(message))
        mesh.printer = NS(lookup_object=lambda name,default=None:objects.get(name,default),
                          is_shutdown=lambda:False,command_error=ValueError)
        return mesh,NS(events=events,limits=limits,position=position,contact=contact,
                       temps=temps,objects=objects,board=board,clock=clock,freeze=freeze,active_mesh=active_mesh)

    def start_preparation(self, mesh):
        mesh.busy,mesh.state,mesh.run_id,mesh.cancelled=True,'PROBING','a'*24,False
        mesh._prepare(mesh.run_id)

    def complete_command(self, mesh, case, publish=None):
        mesh.toolhead=case.objects['toolhead']
        mesh.toolhead.set_position=lambda position:case.position.__setitem__(slice(None),position)
        mesh.gcode.create_gcode_command=lambda name,text,params:params
        mesh._publish=publish or (lambda profile,readings:None)
        mesh.probe_points=NS(update_probe_points=lambda *args:None,
            start_probe=lambda cmd:mesh._capture([
                NS(bed_x=x,bed_y=y,bed_z=1.+.0001*x) for x,y in mesh.points]))
        gcmd=NS(get=lambda key,default:default,get_command_parameters=dict,
                get_int=lambda key,default,**kw:default,get_float=lambda key,default:default,
                respond_info=lambda message:None)
        mesh.cmd_calibrate(gcmd)

    def test_successful_automatic_measurement_turns_previously_off_heaters_back_off(self):
        for measured in (25.,240.):
            with self.subTest(measured=measured):
                mesh,case=self.preflight_case('xyz')
                case.temps.update(hotend=(measured,0.),bed=(25.,0.))
                self.complete_command(mesh,case)
                self.assertEqual(mesh.state,'COMPLETE')
                self.assertEqual((case.temps['hotend'][1],case.temps['bed'][1]),(0.,0.))
                self.assertEqual(mesh.targets['hotend'],max(measured,180.))

    def test_completion_restores_prior_working_targets_without_overriding_an_explicit_off(self):
        for original,off,expected in ((240.,False,240.),(180.,False,180.),(240.,True,0.)):
            with self.subTest(original=original,off=off):
                mesh,case=self.preflight_case('xyz')
                case.temps.update(hotend=(240.,original),bed=(80.,80.))
                def publish(profile,readings):
                    if off:case.objects['m300_job'].hotend.set_temp(0.)
                self.complete_command(mesh,case,publish)
                self.assertEqual(mesh.state,'COMPLETE')
                self.assertEqual((case.temps['hotend'][1],case.temps['bed'][1]),(expected,80.))

    def test_failed_measurement_never_restores_previous_positive_heat(self):
        mesh,case=self.preflight_case('xyz')
        case.temps.update(hotend=(240.,240.),bed=(80.,80.))
        def reject(profile,readings):raise ValueError('publication failed')
        with self.assertRaisesRegex(ValueError,'publication failed'):
            self.complete_command(mesh,case,reject)
        self.assertEqual(mesh.state,'FAILED')
        self.assertEqual((case.temps['hotend'][1],case.temps['bed'][1]),(0.,0.))

    def test_unhomed_pad_measurement_uses_native_homing_then_checks_clearance(self):
        for homed,axes in (('', 'xyz'),('x','xyz'),('y','xyz'),('xy','z'),
                           ('z','xy'),('xz','y'),('yz','x')):
            with self.subTest(homed=homed):
                mesh,case=self.preflight_case(homed)
                mesh._preflight()
                self.start_preparation(mesh)
                homes=[event for event in case.events if isinstance(event,tuple) and event[0]=='home']
                self.assertEqual(homes,[('home',axes)])
                self.assertEqual(case.limits['homed_axes'],'xyz')
                self.assertEqual(case.position[2],5.)
                self.assertEqual(mesh.shift,1.)
                self.assertEqual(mesh.horizontal_z,6.)
                self.assertEqual(mesh.phase,'PROBING')
                self.assertEqual(case.events[-1],'contact')
                self.assertLess(case.events.index('motion_ready'),case.events.index(('home',axes)))
                self.assertEqual(case.temps,dict(hotend=(185.,185.),bed=(60.,60.)))

    def test_already_homed_pad_measurement_does_not_repeat_homing(self):
        mesh,case=self.preflight_case('xyz')
        mesh._preflight()
        self.start_preparation(mesh)
        self.assertNotIn(('home','xyz'),case.events)
        case.contact[0]=True
        with self.assertRaisesRegex(ValueError,'PC7 must be open'):
            self.start_preparation(mesh)

    def test_missing_xy_with_closed_pc7_uses_native_release_before_xy_homing(self):
        mesh,case=self.preflight_case('z')
        case.contact[0]=True
        mesh._preflight()
        self.start_preparation(mesh)
        self.assertIn(('home','xyz'),case.events)
        self.assertLess(case.events.index('contact'),case.events.index(('home','xyz')))
        self.assertFalse(case.contact[0])

    def test_pad_preflight_refuses_invalid_inputs_before_any_heating_or_homing(self):
        def transform(case):case.objects['gcode_move'].move_transform=object()
        def unsafe_geometry(case):case.limits['axis_maximum']=(280.,305.,315.)
        def fileoutput(case):case.board.mcu.is_fileoutput=lambda:True
        def busy_service(case):case.objects['m300_job'].service_busy=lambda:True
        def active_print(case):case.objects['print_stats']=NS(get_status=lambda now:dict(state='printing'))
        def offsets(case):case.objects['probe'].get_offsets=lambda:(1.,0.,0.)
        def unarmed(case):case.board.require_motion=lambda:(_ for _ in ()).throw(ValueError('not armed'))
        cases = [(transform,'native Bed Mesh motion transform'),(unsafe_geometry,'configured XY travel'),
                 (fileoutput,'physical MCU'),(busy_service,'physical MCU'),
                 (active_print,'idle native print'),(offsets,'zero offsets'),(unarmed,'not armed')]
        for change,message in cases:
            with self.subTest(change=change.__name__):
                mesh,case=self.preflight_case()
                change(case)
                with self.assertRaisesRegex(ValueError,message):mesh._preflight()
                self.assertFalse(any(isinstance(event,tuple) for event in case.events))
        for params in ({'HOTEND_TEMP':170.},{'HOTEND_TEMP':float('nan')},{'BED_TEMP':0.},
                       {'BED_TEMP':121.},{'HOTEND_TEMP':301.}):
            mesh,case=self.preflight_case()
            mesh.temperature_params=params
            with self.assertRaises(ValueError):mesh._preflight()
            self.assertFalse(any(isinstance(event,tuple) for event in case.events))

    def test_failed_or_incomplete_native_homing_cannot_start_pad_probing(self):
        mesh,case=self.preflight_case()
        mesh.report={'profile':'previous'}
        mesh.probe_points=NS(update_probe_points=lambda *args:None,
                             start_probe=lambda cmd:self.fail('probe started after a failed home'))
        gcmd=NS(get=lambda key,default:default,get_command_parameters=dict,
                get_int=lambda key,default,**kw:default,get_float=lambda key,default:default)
        def failed_home(axes):raise ValueError('native homing failed')
        case.objects['m300_motion'].home=failed_home
        with self.assertRaisesRegex(ValueError,'native homing failed'):mesh.cmd_calibrate(gcmd)
        self.assertFalse(mesh.busy)
        self.assertEqual(mesh.report,{'profile':'previous'})
        self.assertEqual(case.temps['hotend'][1],0.)
        self.assertEqual(case.temps['bed'][1],0.)
        case.objects['m300_motion'].home=lambda axes:None
        with self.assertRaisesRegex(ValueError,'did not establish XYZ'):mesh.cmd_calibrate(gcmd)
        self.assertFalse(mesh.busy)
        self.assertEqual(mesh.report,{'profile':'previous'})

    def test_preparation_temperature_policy_is_a_180_degree_floor(self):
        for measured,current,expected in ((25.,0.,180.),(180.,0.,180.),(240.,240.,240.),
                (240.,0.,240.),(240.,180.,240.),(242.,240.,240.),(200.,240.,240.)):
            with self.subTest(measured=measured,current=current):
                result=preparation_targets(dict(hotend=(measured,current),bed=(30.,0.)),{})
                self.assertEqual(result,dict(hotend=expected,bed=60.))
        result=preparation_targets(dict(hotend=(200.,200.),bed=(80.,80.)),{})
        self.assertEqual(result,dict(hotend=200.,bed=80.))
        result=preparation_targets(dict(hotend=(240.,240.),bed=(80.,80.)),
                                   {'HOTEND_TEMP':180.,'BED_TEMP':60.})
        self.assertEqual(result,dict(hotend=240.,bed=60.))

    def test_cold_start_heats_both_channels_before_waiting_then_renews_z(self):
        mesh,case=self.preflight_case('xyz')
        case.temps.update(hotend=(25.,0.),bed=(25.,0.))
        case.active_mesh[0]=object()
        mesh._preflight()
        self.start_preparation(mesh)
        self.assertIsNone(case.active_mesh[0])
        self.assertLess(case.events.index(('heat','hotend',180.)),case.events.index('pause'))
        self.assertLess(case.events.index(('heat','bed',60.)),case.events.index('pause'))
        self.assertIn(('home','z'),case.events)
        self.assertEqual(case.temps,dict(hotend=(180.,180.),bed=(60.,60.)))
        self.assertEqual(mesh.phase,'PROBING')

    def test_preparation_timeout_and_changed_target_abort_without_reheating(self):
        mesh,case=self.preflight_case()
        case.temps['bed']=(25.,0.)
        case.freeze[0]=True
        mesh.heat_timeout=1.
        mesh._preflight()
        with self.assertRaisesRegex(ValueError,'timed out'):self.start_preparation(mesh)
        self.assertFalse(any(isinstance(event,tuple) and event[0]=='home' for event in case.events))
        mesh,case=self.preflight_case()
        mesh._preflight()
        old_pause=mesh.reactor.pause
        def change(until):
            result=old_pause(until)
            case.temps['hotend']=(185.,0.)
            return result
        mesh.reactor.pause=change
        with self.assertRaisesRegex(ValueError,'target changed'):self.start_preparation(mesh)
        self.assertEqual(case.temps['hotend'][1],0.)
        self.assertFalse(any(isinstance(event,tuple) and event[0]=='home' for event in case.events))

    def test_shutdown_during_lookahead_never_sets_a_positive_heater_target(self):
        mesh,case=self.preflight_case()
        mesh._preflight()
        mesh.toolhead.register_lookahead_callback=lambda callback:mesh._stop('disconnect')
        with self.assertRaisesRegex(ValueError,'session ended'):self.start_preparation(mesh)
        heat=[event for event in case.events if isinstance(event,tuple) and event[0]=='heat']
        self.assertEqual(heat,[('heat','hotend',0.),('heat','bed',0.)])
        self.assertFalse(mesh.busy)

    def test_preparation_calls_the_real_native_homing_adapter(self):
        from test_normal_operations import motion_fixture
        mesh,case=self.preflight_case()
        case.temps['hotend']=(240.,0.)
        motion=motion_fixture()
        motion.homed=set()
        case.board.hardware=motion.board.hardware
        motion.reactor,motion.board=mesh.reactor,case.board
        motion.hotend=case.objects['m300_job'].hotend
        motion.hotend.get_temp=lambda now:case.temps['hotend']
        motion.heaters=NS(set_temperature=lambda heater,target,wait=False:heater.set_temp(target))
        motion.precision.endstop=case.objects['probe'].mcu_probe.mcu_endstop
        kin=motion.toolhead.get_kinematics()
        old_status=kin.get_status
        kin.get_status=lambda now:dict(old_status(now),axis_minimum=(0.,0.,0.),axis_maximum=(300.,305.,315.))
        motion.toolhead.register_lookahead_callback=lambda callback:None
        case.objects['toolhead']=motion.toolhead
        case.objects['m300_motion']=motion
        mesh._preflight()
        self.start_preparation(mesh)
        homes=[event for event in motion.events if event[0]=='home']
        self.assertEqual(homes,[('home','Y'),('home','X'),('home','Z')])
        self.assertEqual(motion.state,'COMPLETE')
        self.assertEqual(mesh.phase,'PROBING')
        self.assertEqual(case.temps['hotend'],(240.,240.))

    def test_fifty_mm_pads_fit_x300_y305_without_moving_centers_or_shrinking_all_pads(self):
        points=geometry_points(GEOMETRY_DEFAULTS)
        fitted=fit_pad_points(points,(0.,0.),(300.,305.))
        self.assertEqual(mesh_bounds(fitted),(10.,10.,299.,304.))
        self.assertEqual(fitted[:5],((290.,30.),(270.,10.),(299.,10.),(299.,50.),(270.,50.)))
        self.assertEqual(fitted[5:15],points[5:15])
        self.assertEqual(fitted[15:20],((290.,290.),(270.,270.),(299.,270.),(299.,304.),(270.,304.)))
        self.assertEqual(len(set(fitted)),25)
        conservative=geometry_points(dict(GEOMETRY_DEFAULTS,edge_margin=16.))
        self.assertEqual(fit_pad_points(conservative,(0.,0.),(300.,305.)),conservative)
        self.assertEqual(mesh_bounds(conservative),(21.,21.,299.,299.))
        for index,(nominal,actual) in enumerate(zip(points,fitted)):
            if index%5==0:self.assertEqual(actual,nominal)
            cx,cy=points[index//5*5]
            self.assertLess(abs(actual[0]-cx),25.)
            self.assertLess(abs(actual[1]-cy),25.)
            self.assertTrue(1. <= actual[0] <= 299. and 1. <= actual[1] <= 304.)
        reference=.001*160.-.0004*160.
        grid=surface_grid(fitted,[.001*x-.0004*y for x,y in fitted])
        for j,row in enumerate(grid):
            for i,value in enumerate(row):
                self.assertAlmostEqual(value,.001*(10.+289.*i/60)-.0004*(10.+294.*j/60)-reference)
        for index in range(25):
            heights=[0.]*25;heights[index]=.1
            values=[value for row in surface_grid(fitted,heights) for value in row]
            self.assertGreater(max(values)-min(values),.02, index)

    def test_travel_fit_never_uses_an_unreachable_center_or_a_collapsed_pad(self):
        points=geometry_points(GEOMETRY_DEFAULTS)
        for bounds in ((280.,305.),(300.,280.),(290.5,305.)):
            with self.assertRaisesRegex(ValueError,'pad center'):
                fit_pad_points(points,(0.,0.),bounds)
        for margin in (-.01,6.,float('nan')):
            with self.assertRaisesRegex(ValueError,'TRAVEL_MARGIN'):
                fit_pad_points(points,(0.,0.),(300.,305.),margin)
        self.assertEqual(fit_pad_points(points,(0.,0.),(320.,320.)),points)

    def test_macro_inherits_configured_geometry_and_preview_lists_only_changed_corners(self):
        from test_macro_dispatch import ENV, dispatcher, templates
        mesh=M300PadMesh.__new__(M300PadMesh)
        mesh.geometry=dict(GEOMETRY_DEFAULTS,front_left_x=31.25)
        mesh.points=geometry_points(mesh.geometry)
        mesh.busy,mesh.state,mesh.report=False,'IDLE',None
        mesh._error=ValueError;mesh.reactor=NS(monotonic=lambda:0.)
        limits=dict(homed_axes='',axis_minimum=(0.,0.,0.),axis_maximum=(300.,305.,315.))
        toolhead=NS(get_kinematics=lambda:NS(get_status=lambda now:limits))
        mesh.printer=NS(lookup_object=lambda name,default=None:toolhead if name=='toolhead' else default)
        mesh._preflight=lambda:self.fail('preview attempted physical work')
        updates=[];mesh.probe_points=NS(update_probe_points=lambda *args:updates.append(args))
        gcode,_,output=dispatcher();gcode.register_command('BED_MESH_CALIBRATE',mesh.cmd_calibrate)
        template=ENV.from_string(templates()['ZORTRAX_BED_MESH'])
        def run(params):
            gcode.run_script_from_command(template.render(printer=NS(m300_pad_mesh=mesh),params=params))
        run({'PREVIEW':'1'})
        self.assertEqual(mesh.geometry['corner_pad_width'],50.)
        self.assertEqual(mesh.points[5],(31.25,30.))
        status=mesh.get_status(0.)
        self.assertTrue(status['travel']['fits'])
        self.assertEqual(mesh_bounds(mesh.points),(11.25,10.,299.,304.))
        self.assertTrue(status['adjusted_points'])
        self.assertTrue(all(change['point']%5 for change in status['adjusted_points']))
        self.assertTrue(any('Travel fit adjusted' in line for line in output))
        run({'PREVIEW':'1','FIT_TRAVEL':'0'})
        self.assertFalse(mesh.get_status(0.)['travel']['fits'])
        self.assertEqual(mesh.points,geometry_points(mesh.geometry))
        run({'PREVIEW':'1','FIT_TRAVEL':'1','CORNER_PAD_WIDTH':'60',
             'FRONT_LEFT_X':'15','FRONT_LEFT_Y':'15','FRONT_RIGHT_X':'285','FRONT_RIGHT_Y':'15',
             'EDGE_MARGIN':'0','TRAVEL_MARGIN':'0'})
        self.assertEqual(mesh.points[5:10],((15.,15.),(0.,0.),(45.,0.),(45.,45.),(0.,45.)))
        self.assertEqual(mesh.geometry['corner_pad_width'],60.)
        self.assertEqual(mesh.geometry['edge_margin'],0.)
        self.assertEqual(mesh.travel_margin,0.)
        self.assertEqual(limits['axis_maximum'],(300.,305.,315.))

    def test_known_old_macro_migrates_without_replacing_explicit_pad_dimensions_or_centers(self):
        from pathlib import Path
        import m300_profile
        legacy=(Path(__file__).parent/'reference/pad_mesh_macro_r1613.cfg').read_text()
        config='[m300_pad_mesh]\ncorner_pad_width: 60\ncenter_pad_width: 50\nfront_left_x: 31.25\n'
        result=m300_profile.convert_text(config+legacy)
        self.assertIn('corner_pad_width: 60',result)
        self.assertIn('front_left_x: 31.25',result)
        self.assertIn(m300_profile.pad_mesh_command(),result)
        self.assertEqual(m300_profile.convert_text(result),result)
        custom=legacy.replace('default(60)','default(61)')
        self.assertEqual(m300_profile.convert_text(custom),custom)
        self.assertEqual(m300_profile.convert_text(config.replace('60','52')),config.replace('60','52'))
        current=(Path(__file__).parent/'reference/pad_mesh_macro_r1615.cfg').read_text()
        updated=m300_profile.convert_text(current)
        self.assertIn(m300_profile.pad_mesh_command(),updated)
        self.assertIn('HOTEND_TEMP',updated)
        self.assertIn('BED_TEMP',updated)
        self.assertEqual(m300_profile.convert_text(updated),updated)
        recent=(Path(__file__).parent/'reference/pad_mesh_macro_r1617.cfg').read_text()
        updated=m300_profile.convert_text(recent)
        self.assertIn(m300_profile.pad_mesh_command(),updated)
        self.assertEqual(m300_profile.convert_text(updated),updated)
        lines=m300_profile.pad_mesh_command().splitlines()
        for field in ('CORNER_PAD_WIDTH','CENTER_PAD_WIDTH','EDGE_MARGIN','BED_TEMP','HOTEND_TEMP'):
            self.assertTrue(any('params.'+field in line for line in lines))

    def test_320_mm_layout_and_individual_center_corrections(self):
        geometry = dict(GEOMETRY_DEFAULTS, corner_pad_width=60.)
        points = geometry_points(geometry)
        self.assertEqual(mesh_bounds(points), (5., 5., 315., 315.))
        self.assertEqual(points[:5], ((290., 30.), (265., 5.), (315., 5.),
                                    (315., 55.), (265., 55.)))
        self.assertEqual(points[10:15], ((160., 160.), (140., 140.), (180., 140.),
                                        (180., 180.), (140., 180.)))
        geometry.update(front_left_x=31.5, rear_right_y=289., center_x=159.)
        corrected = geometry_points(geometry)
        self.assertEqual(corrected[5], (31.5, 30.))
        self.assertEqual(corrected[10], (159., 160.))
        self.assertEqual(corrected[15], (290., 289.))
        x0, y0, x1, y1 = mesh_bounds(corrected)
        grid = surface_grid(corrected, [.001*x + .0001*y for x, y in corrected])
        reference = .001*159 + .0001*160
        for j, row in enumerate(grid):
            for i, z in enumerate(row):
                self.assertAlmostEqual(z, .001*(x0 + (x1-x0)*i/(GRID_COUNT-1))
                                       + .0001*(y0 + (y1-y0)*j/(GRID_COUNT-1)) - reference)
        for bad in (dict(center_x=10.), dict(front_left_x=float('nan')),
                    dict(rear_left_y=35.)):
            with self.assertRaises(ValueError):
                geometry_points(dict(geometry, **bad))

    def test_geometry_only_probes_the_inset_corners_and_center(self):
        points = pad_points(8., 1.)
        self.assertEqual(len(set(points)), 25)
        for i, (x, y) in enumerate(POINTS):
            self.assertEqual(points[i * 5:(i + 1) * 5],
                             ((x, y), (x-3, y-3), (x+3, y-3), (x+3, y+3), (x-3, y+3)))
        for width, margin in ((2., 1.), (8., -.01), (float('nan'), 1.)):
            with self.assertRaises(ValueError):
                pad_points(width, margin)

    def test_home_is_15_mm_inside_the_60_mm_pad_and_zero_margin_keeps_native_zero(self):
        geometry=dict(GEOMETRY_DEFAULTS,corner_pad_width=60.,edge_margin=0.,
                      front_left_x=15.,front_left_y=15.,front_right_x=285.,front_right_y=15.)
        nominal=geometry_points(geometry)
        self.assertEqual(nominal[5:10],((15.,15.),(-15.,-15.),(45.,-15.),(45.,45.),(-15.,45.)))
        fitted=fit_pad_points(nominal,(0.,0.),(300.,305.),margin=0.)
        self.assertEqual(fitted[5:10],((15.,15.),(0.,0.),(45.,0.),(45.,45.),(0.,45.)))
        self.assertEqual(fitted[:5],((285.,15.),(255.,0.),(300.,0.),(300.,45.),(255.,45.)))
        self.assertEqual(len(set(fitted)),25)
        self.assertTrue(all(0. <= x <= 300. and 0. <= y <= 305. for x,y in fitted))
        reference=.001*geometry['center_x']+.002*geometry['center_y']
        grid=surface_grid(fitted,[.001*x+.002*y for x,y in fitted])
        x0,y0,x1,y1=mesh_bounds(fitted)
        for j,row in enumerate(grid):
            for i,z in enumerate(row):
                self.assertAlmostEqual(z,.001*(x0+(x1-x0)*i/60)+.002*(y0+(y1-y0)*j/60)-reference)

    def test_metal_inset_keeps_home_zero_and_only_moves_reachable_inner_edges(self):
        geometry=dict(GEOMETRY_DEFAULTS,corner_pad_width=60.,edge_margin=2.,
                      front_left_x=15.,front_left_y=15.,front_right_x=285.,front_right_y=15.)
        fitted=fit_pad_points(geometry_points(geometry),(0.,0.),(300.,305.),margin=0.)
        self.assertEqual(fitted[5:10],((15.,15.),(0.,0.),(43.,0.),(43.,43.),(0.,43.)))
        self.assertEqual(fitted[:5],((285.,15.),(257.,0.),(300.,0.),(300.,43.),(257.,43.)))

    def test_zero_margin_still_rejects_invalid_dimensions_and_collapsed_contact_areas(self):
        for width in (0.,-1.,101.,float('nan'),float('inf')):
            with self.subTest(width=width),self.assertRaisesRegex(ValueError,'pad widths'):
                pad_points(width,0.)
        for margin in (-1.,float('nan'),float('inf')):
            with self.subTest(margin=margin),self.assertRaisesRegex(ValueError,'edge_margin'):
                pad_points(60.,margin,50.)
        for margin in (25.,30.):
            with self.subTest(margin=margin),self.assertRaisesRegex(ValueError,'half of both'):
                pad_points(60.,margin,50.)

    def test_measured_60_mm_outer_and_50_mm_center_geometry_fits_travel(self):
        points = pad_points(60., 5., 50.)
        self.assertEqual(len(set(points)), 25)
        self.assertEqual(mesh_bounds(points), (10., 19., 294., 300.))
        for i, (x, y) in enumerate(POINTS):
            span = 20 if i == 2 else 25
            self.assertEqual(points[i * 5:(i + 1) * 5],
                             ((x, y), (x-span, y-span), (x+span, y-span),
                              (x+span, y+span), (x-span, y+span)))
        for center_width in (float('nan'), float('inf'), 10., 101.):
            with self.assertRaises(ValueError):
                pad_points(60., 5., center_width)

    def test_triangles_cover_the_rectangle_and_use_every_contact(self):
        points = pad_points(60., 5., 50.)
        triangles = pad_triangles()
        self.assertEqual(len(triangles), 36)
        self.assertEqual({i for triangle in triangles for i in triangle}, set(range(25)))
        area = 0.
        for a, b, c in triangles:
            ax, ay = points[a]
            bx, by = points[b]
            cx, cy = points[c]
            cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            self.assertGreater(cross, 0.)
            area += cross / 2
        self.assertEqual(area, 284 * 281)
        # The complete grid also exercises triangle boundaries and all gaps.
        self.assertTrue(all(z == 0. for row in surface_grid(points, [0.] * 25) for z in row))

    def test_surface_preserves_a_plane_and_captures_a_center_deviation(self):
        def plane(x, y):
            return .001 * x - .0004 * y

        points = pad_points(60., 5., 50.)
        reference = plane(*POINTS[2])
        grid = surface_grid(points, [plane(*p) for p in points])
        for i, row in enumerate(grid):
            for j, z in enumerate(row):
                self.assertAlmostEqual(z, plane(10 + 284 * j / (GRID_COUNT - 1),
                                               19 + 281 * i / (GRID_COUNT - 1))
                                       - reference)
        bowl = surface_grid(points, [.1] * 10 + [-.2] * 5 + [.1] * 10)
        self.assertAlmostEqual(bowl[GRID_COUNT // 2][GRID_COUNT // 2], 0., places=3)
        self.assertAlmostEqual(bowl[0][0], .3)
        self.assertTrue(all(-1e-12 <= z <= .3 + 1e-12 for row in bowl for z in row))

    def test_each_of_the_25_heights_affects_the_mesh_without_overshoot(self):
        points = pad_points(60., 5., 50.)
        for index in range(25):
            heights = [0.] * 25
            heights[index] = .1
            values = [z for row in surface_grid(points, heights) for z in row]
            self.assertGreater(max(values) - min(values), .02, msg='contact %d' % index)
            self.assertGreaterEqual(min(values), -heights[10] - 1e-12)
            self.assertLessEqual(max(values), .1 - heights[10] + 1e-12)
        for heights in ([0.] * 24, [0.] * 24 + [float('nan')]):
            with self.assertRaises(ValueError):
                surface_grid(points, heights)

    def test_incomplete_bad_xy_and_uneven_pad_cannot_become_measurements(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.points = pad_points(8., 1.)
        mesh._check_clear = lambda: None
        mesh._error = ValueError
        mesh.shift = 1.
        mesh.max_pad_spread = .05
        mesh.max_bed_span = .5
        results = [NS(bed_x=x, bed_y=y, bed_z=.9) for x, y in mesh.points]
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            mesh._capture(results[:-1])
        results[0].bed_x += 1.
        with self.assertRaisesRegex(ValueError, 'requested pad position'):
            mesh._capture(results)
        results[0].bed_x -= 1.
        results[0].bed_z = 1.01
        with self.assertRaisesRegex(ValueError, 'uneven'):
            mesh._capture(results)
        results[0].bed_z = .91
        mesh._capture(results)
        readings, pads = mesh.samples
        self.assertEqual(len(readings), 25)
        self.assertAlmostEqual(pads[0]['spread'], .01)
        self.assertAlmostEqual(pads[0]['z'], -.1)

    def test_wide_pad_slope_is_preserved_and_span_checks_every_contact(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.points = pad_points(60., 5., 50.)
        mesh._check_clear = lambda: None
        mesh._error = ValueError
        mesh.shift = 1.
        mesh.max_pad_spread = None
        mesh.max_bed_span = .5
        results = [NS(bed_x=x, bed_y=y, bed_z=1. + .001 * x) for x, y in mesh.points]
        mesh._capture(results)
        readings, pads = mesh.samples
        self.assertAlmostEqual(pads[0]['spread'], .05)
        self.assertAlmostEqual(readings[0], .269)
        # One high contact must fail even when all five pad medians are zero.
        for result in results:
            result.bed_z = 1.
        results[1].bed_z = 1.51
        with self.assertRaisesRegex(ValueError, 'bed span'):
            mesh._capture(results)

    def test_run_restores_physical_frame_and_rejects_incomplete_probe(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.busy = False
        mesh.report = {'profile': 'previous'}
        mesh.geometry = dict(GEOMETRY_DEFAULTS)
        mesh.points = geometry_points(mesh.geometry)
        mesh.shift, mesh.horizontal_z = 1., 6.
        mesh._error = ValueError
        mesh._preflight = lambda: None
        mesh._prepare = lambda token: None
        mesh._check_session = lambda token: None
        mesh.printer = NS(is_shutdown=lambda: False, lookup_object=lambda name, default=None: default)
        positions = [[150., 158., 5., 0.]]
        mesh.toolhead = NS(get_position=lambda: positions[-1][:],
                           set_position=lambda pos: positions.append(pos[:]),
                           wait_moves=lambda: None)
        cleared = []
        mesh.kin = NS(clear_homing_state=cleared.append)
        mesh.gcode = NS(create_gcode_command=lambda _, __, params: params)
        gcmd = NS(get=lambda _, default: default, get_command_parameters=dict,
                  get_int=lambda _, default, **kw: default,
                  get_float=lambda _, default: default,
                  respond_info=lambda message: None)
        published = []
        mesh._publish = lambda profile, heights: published.append((profile, heights))

        def probe(params):
            self.assertEqual(positions[-1][2], 6.)
            self.assertEqual(params['SAMPLES'], '3')
            raise ValueError('No trigger')

        mesh.probe_points = NS(start_probe=probe, update_probe_points=lambda *args: None)
        with self.assertRaisesRegex(ValueError, 'No trigger'):
            mesh.cmd_calibrate(gcmd)
        self.assertEqual(positions[-1][2], 5.)
        self.assertEqual(cleared, ['z'])
        self.assertEqual(published, [])
        self.assertEqual(mesh.report, {'profile': 'previous'})
        self.assertEqual(mesh.state, 'FAILED')
        self.assertFalse(mesh.busy)
        self.assertEqual(mesh.last_error, 'No trigger')
        failed_run = mesh.run_id
        self.assertRegex(failed_run, r'^[a-f0-9]{24}$')

        def probe_success(params):
            self.assertEqual(positions[-1][2], 6.)
            mesh.samples = ([.01] * 25, [])

        mesh.probe_points.start_probe = probe_success
        mesh.cmd_calibrate(gcmd)
        self.assertEqual(positions[-1][2], 5.)
        self.assertEqual(cleared, ['z'])
        self.assertEqual(published, [('m300_pads', [.01] * 25)])
        self.assertEqual(mesh.state, 'COMPLETE')
        self.assertEqual(len(mesh.report['points']), 25)
        self.assertEqual(mesh.last_error, '')
        self.assertNotEqual(mesh.run_id, failed_run)
        self.assertEqual(mesh.report['run_id'], mesh.run_id)

    def test_operator_75_contacts_retain_diagnostics_but_reject_the_08025_mm_span(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.geometry = dict(GEOMETRY_DEFAULTS, edge_margin=16.)
        mesh.points = geometry_points(mesh.geometry)
        mesh.shift, mesh.max_pad_spread, mesh.max_bed_span = 1., None, .5
        mesh.run_id, mesh.samples = 'a'*24, None
        mesh.report = {'profile': 'previous'}
        mesh._check_clear, mesh._error = lambda: None, ValueError
        triples = [(.855,.8625,.86),(.845,.8525,.855),(.725,.7275,.73),
            (.8325,.8325,.8325),(.9675,.9825,.985),(.5475,.5525,.5525),
            (.415,.415,.415),(.53,.5325,.5325),(.67,.675,.675),(.56,.565,.565),
            (1.0325,1.035,1.035),(.975,.9775,.9775),(1.015,1.015,1.015),
            (1.0425,1.0475,1.045),(1.015,1.02,1.0175),(1.1525,1.155,1.155),
            (1.2125,1.2175,1.22),(1.1125,1.115,1.115),(1.06,1.0625,1.0625),
            (1.1525,1.1575,1.1575),(.855,.8575,.8575),(.8425,.8475,.8475),
            (.9475,.9525,.9525),(.88,.8825,.8825),(.785,.7875,.7875)]
        self.assertAlmostEqual(max(max(t)-min(t) for t in triples), .0175)
        results = [NS(bed_x=x,bed_y=y,bed_z=statistics.median(t))
                   for (x,y),t in zip(mesh.points,triples)]
        with self.assertRaisesRegex(ValueError, '0.8025 mm exceeds max_bed_span 0.5000 mm'):
            mesh._capture(results)
        attempt = mesh.last_attempt
        self.assertFalse(attempt['accepted'])
        self.assertEqual(attempt['run_id'], mesh.run_id)
        self.assertAlmostEqual(attempt['span_mm'], .8025)
        self.assertAlmostEqual(attempt['min_mm'], -.585)
        self.assertAlmostEqual(attempt['max_mm'], .2175)
        self.assertEqual(attempt['limit_mm'], .5)
        self.assertEqual(len(attempt['points']), 25)
        self.assertEqual(len(attempt['pads']), 5)
        self.assertEqual(mesh.points_measured, 25)
        self.assertIsNone(mesh.samples)
        self.assertEqual(mesh.report, {'profile': 'previous'})

    def test_current_run_status_only_accepts_successful_published_measurements(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.busy, mesh.state, mesh.report = False, 'IDLE', {'profile':'previous'}
        mesh.geometry = dict(GEOMETRY_DEFAULTS, edge_margin=16.)
        mesh.points = geometry_points(mesh.geometry)
        mesh.shift, mesh.horizontal_z, mesh.max_pad_spread, mesh.max_bed_span = 1., 6., None, .5
        mesh._error, mesh._preflight, mesh._check_clear = ValueError, lambda:None, lambda:None
        mesh._prepare = lambda token:None
        mesh._check_session = lambda token:None
        mesh.printer = NS(is_shutdown=lambda:False, lookup_object=lambda name,default=None:default)
        mesh.reactor = NS(monotonic=lambda:0.)
        positions, cleared, published = [[150.,158.,5.,0.]], [], []
        mesh.toolhead = NS(get_position=lambda:positions[-1][:],
                           set_position=lambda pos:positions.append(pos[:]), wait_moves=lambda:None)
        mesh.kin = NS(clear_homing_state=cleared.append)
        mesh.gcode = NS(create_gcode_command=lambda _,__,params:params)
        params, observed = {}, []
        gcmd = NS(get=lambda key,default:params.get(key,default), get_command_parameters=lambda:params,
                  get_int=lambda key,default,**kw:int(params.get(key,default)),
                  get_float=lambda key,default:float(params.get(key,default)), respond_info=lambda message:None)
        mesh._publish = lambda profile,readings:published.append((profile,readings))
        high = [False]
        def probe(params):
            observed.append(mesh.get_status(0.))
            results = [NS(bed_x=x,bed_y=y,bed_z=1.+.0001*x) for x,y in mesh.points]
            if high[0]:results[1].bed_z=1.6
            mesh._capture(results)
        mesh.probe_points = NS(start_probe=probe,update_probe_points=lambda *args:None)
        mesh.cmd_calibrate(gcmd)
        status = mesh.get_status(0.)
        self.assertEqual(observed[0]['state'], 'PROBING')
        self.assertTrue(observed[0]['busy'])
        self.assertEqual(observed[0]['points_measured'], 0)
        self.assertEqual((status['points_measured'],status['total_points']), (25,25))
        self.assertTrue(status['last_attempt']['accepted'])
        self.assertEqual(status['last_attempt']['run_id'], status['result']['run_id'])
        self.assertEqual(status['run_id'], observed[0]['run_id'])
        old_report, old_run = mesh.report, mesh.run_id
        params['PREVIEW']='1'
        mesh.cmd_calibrate(gcmd)
        self.assertEqual(mesh.run_id, old_run)  # A geometry-only preview cannot trigger Tune navigation.
        params.clear()
        high[0]=True
        with self.assertRaisesRegex(ValueError,'bed span'):
            mesh.cmd_calibrate(gcmd)
        status=mesh.get_status(0.)
        self.assertEqual(status['state'],'FAILED')
        self.assertFalse(status['busy'])
        self.assertIn('No new mesh profile was created',status['last_error'])
        self.assertFalse(status['last_attempt']['accepted'])
        self.assertNotEqual(status['run_id'],old_run)
        self.assertIs(mesh.report,old_report)
        self.assertEqual(len(published),1)
        self.assertEqual(cleared,['z'])
        self.assertEqual(positions[-1][2],5.)

    def test_preview_applies_numeric_parameters_without_homing_heating_or_motion(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.busy, mesh.state, mesh.report = False, 'IDLE', None
        mesh.geometry = dict(GEOMETRY_DEFAULTS)
        mesh.points = geometry_points(mesh.geometry)
        mesh._error = ValueError
        mesh.reactor = NS(monotonic=lambda: 0.)
        mesh.printer = NS(lookup_object=lambda name, default=None: default)
        mesh._preflight = lambda: self.fail('preview called physical preflight')
        updates, output = [], []
        mesh.probe_points = NS(update_probe_points=lambda *args: updates.append(args))
        params = {'PREVIEW': '1', 'FRONT_LEFT_X': '31.25', 'CENTER_Y': '159.5'}
        gcmd = NS(get=lambda key, default: params.get(key, default),
                  get_command_parameters=lambda: params,
                  get_int=lambda key, default, **kw: int(params.get(key, default)),
                  get_float=lambda key, default: float(params.get(key, default)),
                  respond_info=output.append)
        mesh.cmd_calibrate(gcmd)
        self.assertEqual(mesh.points[5], (31.25, 30.))
        self.assertEqual(mesh.points[10], (160., 159.5))
        self.assertEqual(updates, [(mesh.points, 25)])
        self.assertEqual(mesh.state, 'IDLE')
        self.assertIn('M300_PAD_MESH ', output[0])
        params['CENTER_Y'] = 'nan'
        with self.assertRaisesRegex(ValueError, 'finite'):
            mesh.cmd_calibrate(gcmd)
        self.assertEqual(len(updates), 1)
        self.assertEqual(mesh.points[10], (160., 159.5))

    def test_macro_passes_geometry_and_preview_through_the_native_lexer(self):
        from test_macro_dispatch import ENV, dispatcher, templates
        from setup_fluidd import category
        template = ENV.from_string(templates()['ZORTRAX_BED_MESH'])
        gcode, printer, output = dispatcher()
        commands = []
        gcode.register_command('BED_MESH_CALIBRATE',
                               lambda cmd: commands.append(cmd.get_command_parameters()))
        rendered = template.render(printer=NS(m300_pad_mesh=object()),
                                   params={'FRONT_RIGHT_X': '289.25', 'PREVIEW': '1',
                                           'HOTEND_TEMP':'240','BED_TEMP':'60'})
        gcode.run_script_from_command(rendered)
        self.assertEqual(output, [])
        self.assertEqual(commands[0]['FRONT_RIGHT_X'], '289.25')
        self.assertEqual(commands[0]['PREVIEW'], '1')
        self.assertEqual(commands[0]['HOTEND_TEMP'],'240')
        self.assertEqual(commands[0]['BED_TEMP'],'60')
        self.assertEqual(set(commands[0]), {'FRONT_RIGHT_X', 'PREVIEW', 'HOTEND_TEMP', 'BED_TEMP'})
        rendered=template.render(printer=NS(m300_pad_mesh=object()),params={})
        gcode.run_script_from_command(rendered)
        self.assertEqual(commands[-1],{})
        self.assertEqual(category('ZORTRAX_BED_MESH'), 'ZORTRAX M300')

    def test_actual_preflight_rejects_a_300_mm_limit_before_315_mm_probing(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.geometry = dict(GEOMETRY_DEFAULTS, corner_pad_width=60.)
        mesh.points = geometry_points(mesh.geometry)
        mesh._error = ValueError
        mesh.reactor = NS(monotonic=lambda: 0.)
        job = NS(board=NS(native_control=True, mcu=NS(is_fileoutput=lambda: False)),
                 service_busy=lambda: False, get_status=lambda now: dict(busy=False))
        limits = dict(homed_axes='xyz', axis_minimum=(0., 0., 0.),
                      axis_maximum=(300., 300., 315.))
        toolhead = NS(get_kinematics=lambda: NS(get_status=lambda now: limits))
        mesh.bedmesh = object()
        objects = {'m300_job': job, 'toolhead': toolhead,
                   'gcode_move': NS(move_transform=object())}
        mesh.printer = NS(lookup_object=lambda name, default=None: objects.get(name, default))
        with self.assertRaisesRegex(ValueError, 'configured XY travel'):
            mesh._preflight()
        travel = mesh._geometry_travel(limits)
        self.assertEqual(travel['required_x'], [5., 315.])
        self.assertEqual(travel['configured_x'], [0., 300.])
        self.assertEqual(travel['suggested_edge_margin'], 21)
        self.assertEqual(travel['outside_points'][0]['pad'], 'front_right')
        limits['axis_maximum'] = (320., 320., 315.)
        with self.assertRaisesRegex(ValueError, 'native Bed Mesh motion transform'):
            mesh._preflight()

    def test_preview_reports_limits_and_fitting_inset_without_moving_or_extending_travel(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.geometry = dict(GEOMETRY_DEFAULTS, corner_pad_width=60.)
        mesh.points = geometry_points(mesh.geometry)
        mesh.busy, mesh.state, mesh.report = False, 'IDLE', None
        mesh._error = ValueError
        mesh.reactor = NS(monotonic=lambda: 0.)
        limits = dict(homed_axes='', axis_minimum=[0., 0., 0.], axis_maximum=[300., 300., 315.])
        toolhead = NS(get_kinematics=lambda: NS(get_status=lambda now: limits))
        mesh.printer = NS(lookup_object=lambda name, default=None: toolhead if name == 'toolhead' else default)
        mesh._preflight = lambda: self.fail('preview must not move, heat or home')
        mesh.probe_points = NS(update_probe_points=lambda *args: None)
        params, output = {'PREVIEW': '1', 'FIT_TRAVEL':'0'}, []
        gcmd = NS(get=lambda key, default: params.get(key, default), get_command_parameters=lambda: params,
                  get_int=lambda key, default, **kw: int(params.get(key, default)),
                  get_float=lambda key, default: float(params.get(key, default)), respond_info=output.append)
        mesh.cmd_calibrate(gcmd)
        self.assertIn('configured travel X0..300 Y0..300: OUTSIDE TRAVEL', output[1])
        self.assertIn('EDGE_MARGIN=21 PREVIEW=1', output[2])
        params['EDGE_MARGIN'] = '21'
        mesh.cmd_calibrate(gcmd)
        travel = mesh.get_status(0.)['travel']
        self.assertTrue(travel['fits'])
        self.assertEqual(travel['required_x'], [21., 299.])
        self.assertEqual(travel['required_y'], [21., 299.])
        self.assertEqual(len(set(mesh.points)), 25)
        for index, (x, y) in enumerate(mesh.points):
            cx, cy = ((290., 30.), (30., 30.), (160., 160.), (290., 290.), (30., 290.))[index // 5]
            width = 50. if index // 5 == 2 else 60.
            self.assertLess(abs(x - cx), width / 2)
            self.assertLess(abs(y - cy), width / 2)
        self.assertEqual(limits['axis_maximum'], [300., 300., 315.])
        surface_grid(mesh.points, [0.] * 25)  # Full interpolation still covers this geometry.

    def test_unreachable_pad_center_cannot_get_a_false_fitting_inset(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.geometry = dict(GEOMETRY_DEFAULTS)
        mesh.points = geometry_points(mesh.geometry)
        travel = mesh._geometry_travel(dict(axis_minimum=[0., 0., 0.], axis_maximum=[280., 280., 315.]))
        self.assertFalse(travel['fits'])
        self.assertNotIn('suggested_edge_margin', travel)

    def test_native_service_only_accepts_the_known_mesh_transform(self):
        mesh = NS(get_mesh=lambda: None)
        toolhead = object()
        parser = NS(move_transform=mesh)
        printer = NS(lookup_object=lambda name, default=None: NS(bedmesh=mesh))
        self.assertTrue(native_service_frame(printer, parser, toolhead))
        mesh.get_mesh = object
        self.assertFalse(native_service_frame(printer, parser, toolhead))
        self.assertTrue(native_service_frame(printer, parser, toolhead, paused_extrusion=True))
        parser.move_transform = object()
        self.assertFalse(native_service_frame(printer, parser, toolhead, paused_extrusion=True))
