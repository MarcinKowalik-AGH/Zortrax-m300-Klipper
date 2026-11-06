"""Measured contact rectangles override approximate square geometry."""
from types import SimpleNamespace as NS
import unittest

from payload.m300_pad_mesh import (BOUNDS_FIELDS,GEOMETRY_DEFAULTS,GRID_COUNT,M300PadMesh,
                                  fit_pad_points,geometry_points,mesh_bounds,surface_grid)


RECTANGLES = {
    'front_right':(260.,0.,300.,51.), 'front_left':(0.,0.,43.,51.),
    'center':(125.,125.,175.,175.), 'rear_right':(260.,262.,300.,305.),
    'rear_left':(0.,260.,43.,305.),
}


def measured_geometry():
    geometry=dict(GEOMETRY_DEFAULTS,corner_pad_width=60.,edge_margin=0.,
        front_left_x=15.,front_left_y=15.,front_right_x=285.,front_right_y=15.,
        center_x=150.,center_y=150.,rear_left_x=15.,rear_left_y=290.,
        rear_right_x=285.,rear_right_y=290.)
    geometry.update((name+'_bounds',bounds) for name,bounds in RECTANGLES.items())
    return geometry


class PadBoundsTests(unittest.TestCase):
    def test_all_25_positions_stay_in_the_measured_contact_rectangles(self):
        geometry=measured_geometry()
        points=geometry_points(geometry)
        expected=(
            (285.,15.),(260.,0.),(300.,0.),(300.,51.),(260.,51.),
            (15.,15.),(0.,0.),(43.,0.),(43.,51.),(0.,51.),
            (150.,150.),(125.,125.),(175.,125.),(175.,175.),(125.,175.),
            (285.,290.),(260.,262.),(300.,262.),(300.,305.),(260.,305.),
            (15.,290.),(0.,260.),(43.,260.),(43.,305.),(0.,305.))
        self.assertEqual(points,expected)
        self.assertEqual(fit_pad_points(points,(0.,0.),(300.,305.),0.),points)
        self.assertEqual(mesh_bounds(points),(0.,0.,300.,305.))
        self.assertEqual(len(set(points)),25)
        for index,bounds in enumerate(RECTANGLES.values()):
            x0,y0,x1,y1=bounds
            self.assertTrue(all(x0 <= x <= x1 and y0 <= y <= y1 for x,y in points[index*5:index*5+5]))

    def test_explicit_bounds_do_not_add_a_second_inset_or_relocate_the_center(self):
        geometry=measured_geometry()
        points=geometry_points(geometry)
        for width,margin in ((50.,2.),(60.,5.)):
            self.assertEqual(geometry_points(dict(geometry,corner_pad_width=width,edge_margin=margin)),points)
        self.assertEqual(geometry['front_left_x'],15.)
        self.assertEqual(geometry['front_left_bounds'],(0.,0.,43.,51.))
        # AUTO restores this one pad's legacy size/center calculation.
        automatic=geometry_points(dict(geometry,front_left_bounds='AUTO'))
        self.assertEqual(automatic[5:10],((15.,15.),(-15.,-15.),(45.,-15.),(45.,45.),(-15.,45.)))
        self.assertEqual(automatic[:5],points[:5])

    def test_invalid_bounds_are_rejected_before_probe_points_or_control_io(self):
        bad=('0,0,43','0,0,inf,51','0,0,nan,51','0,0,43,51,52',
             '43,0,0,51','16,0,43,51','0,0,101,51','bad')
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):
                geometry_points(dict(measured_geometry(),front_left_bounds=value))
        mesh=M300PadMesh.__new__(M300PadMesh)
        mesh.geometry=measured_geometry();mesh.busy=False;mesh._error=ValueError
        mesh.probe_points=NS(update_probe_points=lambda *args:self.fail('invalid plan installed'))
        mesh._preflight=lambda:self.fail('invalid plan entered physical preparation')
        gcmd=NS(get=lambda key,default:'43,0,0,51' if key=='FRONT_LEFT_BOUNDS' else default,
                get_command_parameters=lambda:{'FRONT_LEFT_BOUNDS':'43,0,0,51'},
                get_int=lambda key,default,**kw:default,get_float=lambda key,default:default)
        with self.assertRaisesRegex(ValueError,'bounds must enclose'):mesh.cmd_calibrate(gcmd)

    def test_macro_passes_rectangles_and_preview_preserves_them_without_moving(self):
        from test_macro_dispatch import ENV,dispatcher,templates
        mesh=M300PadMesh.__new__(M300PadMesh)
        mesh.geometry=measured_geometry();mesh.points=geometry_points(mesh.geometry)
        mesh.busy,mesh.state,mesh.report=False,'IDLE',None
        mesh._error=ValueError;mesh.reactor=NS(monotonic=lambda:0.)
        limits=dict(homed_axes='',axis_minimum=(0.,0.,0.),axis_maximum=(300.,305.,315.))
        toolhead=NS(get_kinematics=lambda:NS(get_status=lambda now:limits))
        mesh.printer=NS(lookup_object=lambda name,default=None:toolhead if name=='toolhead' else default)
        mesh._preflight=lambda:self.fail('preview started physical work')
        mesh.probe_points=NS(update_probe_points=lambda *args:None)
        gcode,_,output=dispatcher();gcode.register_command('BED_MESH_CALIBRATE',mesh.cmd_calibrate)
        template=ENV.from_string(templates()['ZORTRAX_BED_MESH'])
        params={'PREVIEW':'1','TRAVEL_MARGIN':'0'}
        params.update((name.upper()+'_BOUNDS',', '.join(map(str,bounds))) for name,bounds in RECTANGLES.items())
        gcode.run_script_from_command(template.render(printer=NS(m300_pad_mesh=mesh),params=params))
        expected=geometry_points(measured_geometry())
        self.assertEqual(mesh.points,expected)
        gcode.run_script_from_command(template.render(printer=NS(m300_pad_mesh=mesh),params={'PREVIEW':'1'}))
        self.assertEqual(mesh.points,expected)
        status=mesh.get_status(0.)
        self.assertTrue(all(region['explicit'] for region in status['contact_regions']))
        self.assertEqual(status['contact_regions'][3]['bounds'],[260.,262.,300.,305.])
        self.assertEqual(status['probe_points'],[list(point) for point in expected])
        self.assertEqual(limits['axis_maximum'],(300.,305.,315.))

    def test_asymmetric_rectangles_preserve_a_plane_and_every_contact_without_overshoot(self):
        points=geometry_points(measured_geometry())
        plane=lambda x,y:.001*x+.002*y
        reference=plane(150.,150.)
        grid=surface_grid(points,[plane(*point) for point in points])
        for j,row in enumerate(grid):
            for i,z in enumerate(row):
                self.assertAlmostEqual(z,plane(300.*i/(GRID_COUNT-1),305.*j/(GRID_COUNT-1))-reference)
        for index in range(25):
            heights=[0.]*25;heights[index]=.1
            values=[value for row in surface_grid(points,heights) for value in row]
            self.assertGreater(max(values)-min(values),.02,index)
            self.assertGreaterEqual(min(values),-heights[10]-1e-12)
            self.assertLessEqual(max(values),.1-heights[10]+1e-12)


if __name__=='__main__':unittest.main()
