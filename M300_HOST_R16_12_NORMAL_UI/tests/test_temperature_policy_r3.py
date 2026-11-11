"""R3 target caps and native parser semantics. Hardware boundaries modeled."""
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock
import test_display
from payload.m300_temperature_policy import M300TemperaturePolicy, target_limit

class Heater:
    min_temp=5.
    def __init__(self,maximum):self.max_temp=maximum;self.target_temp=0.;self.calls=[]
    def set_temp(self,value):self.target_temp=value;self.calls.append(('set',value))
    def alter_target(self,value):self.target_temp=value;self.calls.append(('alter',value))

def fixture(hotmax=270.,bedmax=120.):
    hot,bed=Heater(hotmax),Heater(bedmax)
    g=NS(register_command=Mock())
    collection=NS(lookup_heater=lambda n:{'extruder':hot,'heater_bed':bed}[n])
    objects={'gcode':g,'heaters':collection}
    printer=NS(command_error=RuntimeError,lookup_object=lambda n:objects[n],register_event_handler=Mock())
    config=NS(get_printer=lambda:printer,getfloat=lambda name,default,**kw:default,error=RuntimeError)
    return M300TemperaturePolicy(config),hot,bed

class TemperaturePolicyR3(unittest.TestCase):
    def test_limits_are_distinct_from_sensor_shutdown(self):
        p,h,b=fixture();p._connect()
        self.assertEqual((h.max_temp,b.max_temp),(270.,120.))
        self.assertEqual((target_limit(h),target_limit(b)),(270.,105.))
        self.assertEqual(p.get_status(0.)['target_limits'],{'extruder':270.,'heater_bed':105.})
    def test_bed_boundaries_and_off_for_both_methods(self):
        p,h,b=fixture();p._connect()
        for method in ('set_temp','alter_target'):
            f=getattr(b,method)
            for val in (0,5,60,100,104.999,105):f(val);self.assertEqual(b.target_temp,val)
            for val in (105.0001,110,120,121,-1,1,float('nan'),float('inf'),-float('inf'),True,'105'):
                last=b.target_temp;count=len(b.calls)
                with self.subTest(method=method,val=val):
                    with self.assertRaises(RuntimeError):f(val)
                    self.assertEqual(b.target_temp,last);self.assertEqual(len(b.calls),count)
            f(0);self.assertEqual(b.target_temp,0)
    def test_hotend_ceiling_never_increased(self):
        p,h,b=fixture();p._connect()
        for val in (170,215,240,260,265,270):h.set_temp(val)
        for val in (270.001,285,290,300,380):
            with self.assertRaises(RuntimeError):h.set_temp(val)
        self.assertEqual(h.target_temp,270)
    def test_preserves_existing_lower_limits(self):
        p,h,b=fixture(250,95);p._connect()
        self.assertEqual(target_limit(h),250);self.assertEqual(target_limit(b),95)
        with self.assertRaises(RuntimeError):h.set_temp(251)
        with self.assertRaises(RuntimeError):b.set_temp(96)
    def test_legacy_unbound_helpers_keep_native_limit(self):
        self.assertEqual(target_limit(Heater(240)),240)
    def test_connect_idempotent_and_no_double_calls(self):
        p,h,b=fixture();p._connect();f=b.set_temp;p._connect()
        self.assertIs(f,b.set_temp);b.set_temp(105);self.assertEqual(b.calls,[('set',105)])
    def test_preflight_checks_all_heaters_before_mutation(self):
        p,h,b=fixture();b.target_temp=60
        with self.assertRaises(RuntimeError):p._connect()
        self.assertFalse(hasattr(h,'m300_target_max'));self.assertFalse(p.bound)
    def test_heater_off_is_not_lost_when_wrapped_by_service(self):
        p,h,b=fixture();p._connect();original=b.set_temp
        b.set_temp=lambda value:original(value)
        b.set_temp(105);b.set_temp(0);self.assertEqual(b.target_temp,0)
        with self.assertRaises(RuntimeError):b.set_temp(106)
    def test_pid_alter_target_cycle_allowed_without_silent_clipping(self):
        p,h,b=fixture();p._connect()
        for val in (105.,102.5,105.,102.5,0.):b.alter_target(val)
        self.assertEqual([v for m,v in b.calls],[105.,102.5,105.,102.5,0.])
    def test_status_before_connect(self):
        p,h,b=fixture();self.assertFalse(p.get_status(0)['bound'])

class NativeIntegrationR3(unittest.TestCase):
    def test_m83_and_m82_same_extrusion_with_matching_coordinates(self):
        from test_native_oem_services import Harness
        h=Harness();h.homed='xyz';h.hotend.temperature=h.hotend.target=240.;h.run('G90\nM83\nG92 E0')
        start=h.position[3];h.run('G1 E1 F60\nG1 E1 F60');relative=h.position[3]-start
        h.run('G90\nM82\nG92 E0');start=h.position[3]
        h.run('G1 E1 F60\nG1 E2 F60');absolute=h.position[3]-start
        self.assertAlmostEqual(relative,2.);self.assertAlmostEqual(absolute,2.)
    def test_saved_parser_state_restores_relative_extrusion(self):
        from test_native_oem_services import Harness
        h=Harness();h.homed='xyz';h.hotend.temperature=h.hotend.target=240.;h.run('G90\nM83\nSAVE_GCODE_STATE NAME=R3')
        h.run('M82\nRESTORE_GCODE_STATE NAME=R3 MOVE=0')
        start=h.position[3];h.run('G1 E1 F60\nG1 E1 F60');self.assertAlmostEqual(h.position[3]-start,2.)
    def test_start_rejects_bed_above_105_before_any_preparation(self):
        from test_print_control import Harness
        h=Harness();self.addCleanup(h.close);h.bed.m300_target_max=105.
        before=(h.hotend.target,h.bed.target,list(h.position))
        with self.assertRaises(Exception):h.run('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=106')
        self.assertEqual(h.c.state,'IDLE');self.assertIsNone(h.c.operation)
        self.assertEqual(before,(h.hotend.target,h.bed.target,list(h.position)))
        self.assertFalse(any(e[0]=='native_pause' for e in h.events))
    def test_mesh_profile_and_service_temperatures_are_not_replaced_with_maxima(self):
        text=(Path(__file__).resolve().parents[1]/'payload/m300_operations.cfg').read_text()
        self.assertIn("OP=LOAD TEMP={params.TEMP|default(240)",text)
        self.assertIn("OP=LEVEL TEMP={params.TEMP|default(260)",text)
    def test_oled_offers_105_and_not_110_or_120(self):
        from test_native_menu import fixture
        m,objects=fixture();m.page='temperature_BED';m._return_page='maintenance'
        m.job.bed=NS(min_temp=5.,max_temp=120.,m300_target_max=105.)
        rows=m.rows(0)[1];values=[a[2] for text,a in rows if a and a[0]=='temp']
        self.assertIn(105,values);self.assertNotIn(110,values);self.assertNotIn(120,values)

if __name__=='__main__':unittest.main()
