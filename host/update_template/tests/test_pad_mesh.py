"""Regression coverage for the optional Classic M300 pad mesh adapter."""
from types import SimpleNamespace as NS
import unittest

from payload.m300_calibration_state import POINTS
from payload.m300_native_service import native_service_frame
from payload.m300_pad_mesh import GRID_COUNT, M300PadMesh, pad_points, surface_grid


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

    def test_surface_preserves_a_plane_and_captures_a_center_deviation(self):
        def plane(x, y):
            return .001 * x - .0004 * y

        reference = plane(*POINTS[2])
        grid = surface_grid([plane(*p) for p in POINTS])
        for i, row in enumerate(grid):
            for j, z in enumerate(row):
                self.assertAlmostEqual(z, plane(35 + 234 * j / (GRID_COUNT - 1),
                                               44 + 231 * i / (GRID_COUNT - 1))
                                       - reference)
        bowl = surface_grid([.1, .1, -.2, .1, .1])
        self.assertAlmostEqual(bowl[GRID_COUNT // 2][GRID_COUNT // 2], 0., places=3)
        self.assertAlmostEqual(bowl[0][0], .3)
        self.assertTrue(all(0. <= z <= .1 - (-.2) for row in bowl for z in row))

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
        readings, pads, heights = mesh.samples
        self.assertEqual(len(readings), 25)
        self.assertAlmostEqual(pads[0]['spread'], .01)
        self.assertAlmostEqual(heights[0], -.1)

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
            mesh.samples = ([.01] * 25, [], [.01] * 5)

        mesh.probe_points.start_probe = probe_success
        mesh.cmd_calibrate(gcmd)
        self.assertEqual(positions[-1][2], 5.)
        self.assertEqual(cleared, ['z'])
        self.assertEqual(published, [('m300_pads', [.01] * 5)])
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
