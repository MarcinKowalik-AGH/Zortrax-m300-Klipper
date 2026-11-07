"""Do not confuse an absolute homing offset with the accepted surface span."""
import unittest

import test_pad_mesh
import test_pad_live_heights
from payload.m300_error_codes import classify
from payload.m300_pad_mesh import surface_grid


class PadProbeWindowTests(unittest.TestCase):
    def test_common_offset_below_minus_075_preserves_native_contacts_and_compensation(self):
        fixture=test_pad_live_heights.PadLiveHeightsTests()
        heights=[-.3425,-.565,-.7025,-.3875,-.135,-.390,-.85]+[-.3]*18
        grids=[]
        for offset in (0.,1.2):
            mesh=fixture.mesh()
            results=fixture.results(mesh,[z+offset for z in heights])
            mesh._update_measurements(results[:6])
            mesh._update_measurements(results[:7])
            self.assertEqual(mesh.points_measured,7)
            self.assertAlmostEqual(mesh.measurements[6][2],-.85+offset)
            mesh._capture(results)
            self.assertEqual(len(mesh.samples[0]),25)
            self.assertAlmostEqual(mesh.last_attempt['span_mm'],.715)
            grids.append(surface_grid(mesh.points,mesh.samples[0]))
        for a,b in zip(grids[0],grids[1]):
            for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=12)

    def test_outside_actual_native_window_retains_exact_rejected_point_and_probe_error(self):
        fixture=test_pad_live_heights.PadLiveHeightsTests()
        for z in (-1.0025,5.0025):
            mesh=fixture.mesh()
            results=fixture.results(mesh,[-.3]*6+[z])
            mesh._update_measurements(results[:6])
            previous=list(mesh.measurements)
            with self.assertRaisesRegex(ValueError,'outside native Z search window') as caught:
                mesh._update_measurements(results)
            rejected=mesh.rejected_contact
            self.assertEqual(rejected['point'],7)
            self.assertEqual((rejected['minimum_z'],rejected['maximum_z']),(-1.,5.))
            self.assertAlmostEqual(rejected['z'],z)
            self.assertEqual(mesh.measurements,previous)
            self.assertIn('X%.3f Y%.3f'%mesh.points[6],str(caught.exception))
            self.assertEqual(classify(str(caught.exception),source='m300_pad_mesh'),(42,0))
        self.assertEqual(classify('M300 pad mesh: contact lies outside the usable Z search range'),(42,0))

    def test_valid_native_contacts_still_cannot_create_an_over_span_profile(self):
        fixture=test_pad_live_heights.PadLiveHeightsTests();mesh=fixture.mesh()
        mesh.report={'profile':'retained'}
        results=fixture.results(mesh,[-.95]*24+[0.])
        with self.assertRaisesRegex(ValueError,'bed span is too large'):
            mesh._capture(results)
        self.assertEqual(len(mesh.measurements),25)
        self.assertAlmostEqual(mesh.last_attempt['span_mm'],.95)
        self.assertFalse(mesh.last_attempt['accepted'])
        self.assertIsNone(mesh.samples)
        self.assertEqual(mesh.report,{'profile':'retained'})

    def test_preflight_keeps_native_minimum_search_depth_and_clearance_unchanged(self):
        for minimum in (0.,-2.5):
            mesh,case=test_pad_mesh.PadMeshTests().preflight_case('xyz')
            case.limits['axis_minimum']=(0.,0.,minimum)
            probe=case.objects['probe'].mcu_probe
            probe.homing_helper.z_min_position=minimum
            mesh._preflight()
            self.assertEqual(probe.homing_helper.z_min_position,minimum)
            self.assertEqual(mesh.shift,minimum+1.)
            self.assertEqual(mesh.probe_bounds,(minimum,minimum+6.))
            self.assertEqual((mesh.probe_bounds[0]-mesh.shift,mesh.horizontal_z-mesh.shift),(-1.,5.))
            self.assertFalse(any(isinstance(e,tuple) and e[0] in ('move','heat') for e in case.events))
