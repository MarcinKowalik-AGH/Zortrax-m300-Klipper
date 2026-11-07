"""Native median observations, the 0.8 mm span and one shared error surface."""
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import m300_profile
from payload.m300_pad_mesh import M300PadMesh, geometry_points, GEOMETRY_DEFAULTS
from test_oem_errors import errors_session


class PadLiveHeightsTests(unittest.TestCase):
    def mesh(self):
        mesh = M300PadMesh.__new__(M300PadMesh)
        mesh.points = geometry_points(dict(GEOMETRY_DEFAULTS, edge_margin=16.))
        mesh.shift, mesh.max_bed_span, mesh.max_pad_spread = 1., .8, None
        mesh.run_id, mesh.samples = 'a'*24, None
        mesh._error, mesh._check_clear = ValueError, lambda:None
        mesh.measurements, mesh.points_measured = [], 0
        return mesh

    def results(self, mesh, heights):
        return [NS(bed_x=x, bed_y=y, bed_z=1.+z)
                for (x,y),z in zip(mesh.points,heights)]

    def test_live_points_are_validated_native_coordinates_and_normalized_contact_heights(self):
        mesh = self.mesh()
        results = self.results(mesh, [.125,-.25,0.,.3125,-.05])
        mesh._update_measurements(results)
        self.assertEqual(mesh.points_measured,5)
        self.assertEqual([r.bed_z for r in results],[1.125,.75,1.,1.3125,.95])
        for point, native in zip(mesh.measurements,results):
            self.assertEqual(point[:2],[native.bed_x,native.bed_y])
            self.assertAlmostEqual(point[2],native.bed_z-1.)

    def test_invalid_native_point_does_not_replace_last_good_partial_measurement(self):
        mesh = self.mesh()
        mesh._update_measurements(self.results(mesh,[.1]))
        original = list(mesh.measurements)
        for fault in ('xy','nonfinite','range','too_many'):
            results = self.results(mesh,[.1,.2])
            if fault=='xy':results[-1].bed_x += 1.
            elif fault=='nonfinite':results[-1].bed_z = float('nan')
            elif fault=='range':results[-1].bed_z = 2.
            else:results = self.results(mesh,[0.]*25)+[results[0]]
            with self.assertRaises(ValueError):mesh._update_measurements(results)
            self.assertEqual(mesh.measurements,original)

    def test_native_helper_reads_completed_medians_without_draining_or_sampling_the_session(self):
        class Points:
            def __init__(self,config,*args):self.printer=config.get_printer()
            def update_probe_points(self,*args):pass
            def use_xy_offsets(self,*args):pass
            def _raise_tool(self,is_first=False):pass
        session = NS(results=[])
        objects = dict(gcode=NS(register_command=lambda *a,**kw:None), probe=NS(probe_session=session))
        printer = NS(get_reactor=lambda:None,lookup_object=lambda name,*a:objects[name],
            load_object=lambda *a:None,register_event_handler=lambda *a:None)
        config = NS(get_printer=lambda:printer,has_section=lambda s:True,
            getsection=lambda s:NS(get=lambda key:'^!PC7'),get=lambda key,default=None:default,
            getfloat=lambda key,default=None,**kw:default,getboolean=lambda key,default:default)
        with patch.dict(sys.modules,{'payload.probe':NS(ProbePointsHelper=Points)}):
            mesh = M300PadMesh(config)
        self.assertEqual(mesh.max_bed_span,.8)
        self.assertEqual(mesh.hotend_temperature,260.)
        mesh.busy,mesh.phase,mesh.shift=True,'PROBING',1.
        session.results = self.results(mesh,[.1,.2])
        queue = session.results
        mesh.probe_points._raise_tool()
        self.assertIs(session.results,queue)
        self.assertEqual(len(queue),2)
        self.assertEqual(mesh.points_measured,2)
        mesh.busy=False;session.results=[]
        mesh.probe_points._raise_tool()
        self.assertEqual(mesh.points_measured,2)

    def test_operator_span_0735_and_exact_0800_pass_but_08025_is_rejected(self):
        for high,accepted in ((.335,True),(.4,True),(.4025,False)):
            mesh = self.mesh()
            results = self.results(mesh,[-.4,high]+[0.]*23)
            if accepted:
                mesh._capture(results)
                self.assertEqual(len(mesh.samples[0]),25)
            else:
                with self.assertRaisesRegex(ValueError,'exceeds max_bed_span 0.8000'):
                    mesh._capture(results)
                self.assertIsNone(mesh.samples)
            self.assertEqual(len(mesh.measurements),25)
            self.assertAlmostEqual(mesh.last_attempt['span_mm'],high+.4)

    def test_stock_threshold_migration_is_idempotent_and_preserves_custom_limits(self):
        for value in ('0.5','.5','0.5000','5e-1'):
            source='[m300_pad_mesh]\nmax_bed_span: '+value+'\nedge_margin: 0\n'
            result=m300_profile.convert_text(source)
            self.assertIn('max_bed_span: 0.8',result)
            self.assertEqual(m300_profile.convert_text(result),result)
        for value in ('0.6','0.8','1.0'):
            source='[m300_pad_mesh]\nmax_bed_span: '+value+'\n'
            self.assertEqual(m300_profile.convert_text(source),source)
        self.assertEqual(m300_profile.convert_text('[m300_pad_mesh]\n'),'[m300_pad_mesh]\n')

    def test_nested_mesh_fault_keeps_shared_identity_and_oled_without_a_second_web_prompt(self):
        with errors_session() as h:
            h.objects['m300_pad_mesh']=NS(busy=True,run_id='a'*24)
            record=h.errors.record('Probe triggered prior to movement',source='m300_motion')
            h.flush_errors()
            self.assertEqual((record['code'],record['surface'],record['run_id']),(42,'pad_mesh','a'*24))
            self.assertEqual(h.oled.message[0],'Error #042')
            self.assertFalse(any('prompt_begin' in line for line in h.lines))
            h.objects['m300_pad_mesh'].busy=False
            h.run('ZORTRAX_ERROR_SHOW')
            self.assertEqual(record['view_revision'],2)
            self.assertFalse(any('prompt_begin' in line for line in h.lines))
            h.errors.acknowledge(record['id'])
            self.assertIsNone(h.errors.current)

    def test_fatal_mesh_fault_keeps_native_shutdown_presentation_and_cannot_be_acknowledged(self):
        with errors_session() as h:
            h.objects['m300_pad_mesh']=NS(busy=True,run_id='a'*24)
            record=h.errors.record('Timer too close',source='klipper_shutdown',fatal=True)
            h.flush_errors()
            self.assertNotIn('surface',record)
            self.assertTrue(any('prompt_begin' in line for line in h.lines))
            with self.assertRaisesRegex(Exception,'Safety latch remains active'):
                h.errors.acknowledge(record['id'])

    def test_repeated_cause_in_a_new_mesh_run_gets_a_new_identity(self):
        with errors_session() as h:
            pad=NS(busy=True,run_id='a'*24)
            h.objects['m300_pad_mesh']=pad
            first=h.errors.record('Probe triggered prior to movement',source='m300_motion')
            h.flush_errors()
            pad.run_id='b'*24
            second=h.errors.record('Probe triggered prior to movement',source='m300_motion')
            h.flush_errors()
            self.assertNotEqual(first['id'],second['id'])
            self.assertEqual(second['run_id'],'b'*24)
            self.assertEqual(len(h.errors.history),2)
