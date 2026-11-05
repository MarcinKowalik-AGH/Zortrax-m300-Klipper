"""Regression coverage for the optional Classic M300 pad mesh adapter."""
from types import SimpleNamespace as NS
import unittest

from payload.m300_calibration_state import POINTS
from payload.m300_native_service import native_service_frame
from payload.m300_pad_mesh import (GEOMETRY_DEFAULTS, GRID_COUNT, M300PadMesh,
                                   geometry_points, mesh_bounds, pad_points,
                                   pad_triangles, surface_grid)


class PadMeshTests(unittest.TestCase):
    def test_320_mm_layout_and_individual_center_corrections(self):
        geometry = dict(GEOMETRY_DEFAULTS)
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
        for width, margin in ((2., 1.), (8., 0.), (float('nan'), 1.)):
            with self.assertRaises(ValueError):
                pad_points(width, margin)

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
        mesh.printer = NS(is_shutdown=lambda: False)
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
                                   params={'FRONT_RIGHT_X': '289.25', 'PREVIEW': '1'})
        gcode.run_script_from_command(rendered)
        self.assertEqual(output, [])
        self.assertEqual(commands[0]['FRONT_RIGHT_X'], '289.25')
        self.assertEqual(commands[0]['PREVIEW'], '1')
        self.assertEqual(commands[0]['PROFILE'], 'm300_pads')
        for key, value in GEOMETRY_DEFAULTS.items():
            if key != 'front_right_x':
                self.assertEqual(float(commands[0][key.upper()]), value)
        self.assertEqual(category('ZORTRAX_BED_MESH'), 'ZORTRAX M300')

    def test_actual_preflight_rejects_a_300_mm_limit_before_315_mm_probing(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.geometry = dict(GEOMETRY_DEFAULTS)
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
        with self.assertRaisesRegex(ValueError, 'clear the active mesh'):
            mesh._preflight()

    def test_preview_reports_limits_and_fitting_inset_without_moving_or_extending_travel(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.geometry = dict(GEOMETRY_DEFAULTS)
        mesh.points = geometry_points(mesh.geometry)
        mesh.busy, mesh.state, mesh.report = False, 'IDLE', None
        mesh._error = ValueError
        mesh.reactor = NS(monotonic=lambda: 0.)
        limits = dict(homed_axes='', axis_minimum=[0., 0., 0.], axis_maximum=[300., 300., 315.])
        toolhead = NS(get_kinematics=lambda: NS(get_status=lambda now: limits))
        mesh.printer = NS(lookup_object=lambda name, default=None: toolhead if name == 'toolhead' else default)
        mesh._preflight = lambda: self.fail('preview must not move, heat or home')
        mesh.probe_points = NS(update_probe_points=lambda *args: None)
        params, output = {'PREVIEW': '1'}, []
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
