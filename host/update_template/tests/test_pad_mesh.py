"""Regression coverage for the optional Classic M300 pad mesh adapter."""
from types import SimpleNamespace as NS
import unittest

from payload.m300_calibration_state import POINTS
from payload.m300_native_service import native_service_frame
from payload.m300_pad_mesh import (GRID_COUNT, M300PadMesh, mesh_bounds,
                                   pad_points, pad_triangles, surface_grid)


class PadMeshTests(unittest.TestCase):
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
        mesh.points = pad_points(8., 1.)
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
                  respond_info=lambda message: None)
        published = []
        mesh._publish = lambda profile, heights: published.append((profile, heights))

        def probe(params):
            self.assertEqual(positions[-1][2], 6.)
            self.assertEqual(params['SAMPLES'], '3')
            raise ValueError('No trigger')

        mesh.probe_points = NS(start_probe=probe)
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
