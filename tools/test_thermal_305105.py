"""Software regression only: heaters and hardware are modeled."""
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile,unittest
from test_temperature_policy_r3 import fixture
from payload.m300_temperature_policy import target_limit
from payload.m300_mcu import raw_limits,HOT_RAW_MAX,BED_RAW_MIN,BED_RAW_MAX
import m300_thermal_config

class Thermal305105Tests(unittest.TestCase):
 def test_operating_and_measured_limits(self):
  p,h,b=fixture(310,120);p._connect()
  self.assertEqual((target_limit(h),target_limit(b)),(305,105));self.assertEqual((h.max_temp,b.max_temp),(310,120))
  status=p.get_status(0);self.assertEqual(status['hardware_validation'],'USER_REPORTED_2026-11-11');self.assertFalse(status['automated_hardware_test'])
 def test_set_and_pid_targets_boundary(self):
  p,h,b=fixture(310,120);p._connect()
  for heater,limit in [(h,305),(b,105)]:
   for method in ('set_temp','alter_target'):
    fn=getattr(heater,method)
    for t in [0,25,limit-1,limit]:fn(t);self.assertEqual(heater.target_temp,t)
    for t in [limit+.001,limit+1,400,float('inf'),float('nan'),-1,True,'305']:
     before=len(heater.calls)
     with self.subTest(method=method,t=t):
      with self.assertRaises(RuntimeError):fn(t)
      self.assertEqual(len(heater.calls),before)
    fn(0)
 def test_lower_native_temperature_remains_respected(self):
  p,h,b=fixture(290,100);p._connect();self.assertEqual(target_limit(h),290);self.assertEqual(target_limit(b),100)
 def test_existing_mcu_raw_envelope_admits_305_with_shutdown_310(self):
  limits=raw_limits(5*.005/3.270,310*.005/3.270)
  self.assertEqual(HOT_RAW_MAX,1941);self.assertLessEqual(limits[1],HOT_RAW_MAX)
  self.assertLess(305*.005/3.270*4095,limits[1]);self.assertEqual((BED_RAW_MIN,BED_RAW_MAX),(1741,3941))
 def test_oled_has_305_not_310(self):
  from test_native_menu import fixture as menu_fixture
  m,objects=menu_fixture();m.page='temperature_HOTEND';m._return_page='maintenance';m.job.hotend=NS(min_temp=5.,max_temp=310.,m300_target_max=305.)
  values=[a[2] for text,a in m.rows(0)[1] if a and a[0]=='temp'];self.assertIn(305,values);self.assertNotIn(310,values)
 def test_normal_start_pause_resume_end_305_105(self):
  from test_print_control import Harness
  h=Harness();self.addCleanup(h.close);h.hotend.max_temp=310;h.hotend.m300_target_max=305;h.bed.max_temp=120;h.bed.m300_target_max=105
  h.hotend.temperature=305;h.bed.temperature=105
  h.run('ZORTRAX_PRINT_START EXTRUDER_TEMP=305 BED_TEMP=105');h.stop_worker();h.control_until('IDLE')
  self.assertIn(('native_resume',),h.events);self.assertEqual((h.hotend.target,h.bed.target),(305,105))
  h.pause_print();h.run('RESUME');h.control_until('IDLE');self.assertEqual((h.hotend.target,h.bed.target),(305,105))
  h.run('ZORTRAX_PRINT_END');h.stop_worker();h.control_until('IDLE');self.assertEqual((h.hotend.target,h.bed.target),(0,0))
 def test_start_invalid_temp_before_heat_and_motion(self):
  from test_print_control import Harness
  for hot,bed in [(305.01,105),(400,105),(305,105.01)]:
   h=Harness();self.addCleanup(h.close);h.hotend.max_temp=310;h.hotend.m300_target_max=305;h.bed.max_temp=120;h.bed.m300_target_max=105
   before=(h.hotend.target,h.bed.target,list(h.position))
   with self.assertRaises(Exception):h.run('ZORTRAX_PRINT_START EXTRUDER_TEMP=%s BED_TEMP=%s'%(hot,bed))
   self.assertEqual((h.hotend.target,h.bed.target,list(h.position)),before);self.assertIsNone(h.c.operation)

class Configuration305105Tests(unittest.TestCase):
 def setUp(self):
  self.hot='[extruder]\nsensor_type: M300_HOTEND_STOCK_LINEAR_LAB\nmax_temp: 270\npid_kp: 15.123\nrotation_distance: 26.133\n'
  self.bed='[heater_bed]\nsensor_type: M300_BED_STOCK_TABLE_LAB\nmax_temp: 120\npid_kp: 60.123\n'
 def test_transform_preserves_pid_wiring_and_motion(self):
  a,seen=m300_thermal_config.transform(self.hot+self.bed);self.assertEqual(seen,['extruder','heater_bed']);self.assertIn('max_temp: 310',a)
  self.assertIn('pid_kp: 15.123',a);self.assertIn('rotation_distance: 26.133',a);self.assertEqual(m300_thermal_config.transform(a)[0],a)
 def test_include_plan_and_saved_config(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'printer.cfg';hot=Path(d)/'head.cfg';bed=Path(d)/'bed.cfg'
   footer='#*# <---------------------- SAVE_CONFIG ---------------------->\n#*# [extruder]\n#*# pid_kp = 15.123\n'
   original={root:'[include head.cfg]\n[include bed.cfg]\n'+footer,hot:self.hot,bed:self.bed};desired={p:t.encode() for p,t in original.items()}
   m300_thermal_config.apply_to_plan(desired,root,original);self.assertIn(b'max_temp: 310',desired[hot]);self.assertTrue(desired[root].endswith(footer.encode()))
   self.assertLess(desired[root].index(b'[m300_temperature_policy]'),desired[root].index(b'#*#'))
   old=dict(desired);m300_thermal_config.apply_to_plan(desired,root,original);self.assertEqual(old,desired)
 def test_existing_policy_updates_in_place(self):
  a,seen=m300_thermal_config.transform(self.hot+self.bed+'[m300_temperature_policy]\nhotend_target_max: 270\nbed_target_max: 100\n')
  self.assertEqual(a.count('[m300_temperature_policy]'),1);self.assertIn('hotend_target_max: 305',a);self.assertIn('bed_target_max: 105',a)
 def test_unknown_sensor_is_not_relabelled(self):
  with self.assertRaises(ValueError):m300_thermal_config.transform(self.hot.replace('M300_HOTEND_STOCK_LINEAR_LAB','PT1000'))
 def test_full_installer_plan_apply_rollback(self):
  from test_install import InstallerTests
  import install
  h=InstallerTests(methodName='runTest');h.setUp();self.addCleanup(h.tearDown)
  original='[mcu]\nserial: /dev/ttyS1\n'+self.hot+self.bed;h.config.write_text(original)
  changes=install.plan(h.root,h.config,thermal_305105=True);receipt=install.apply(h.root,h.config,changes)
  self.assertIn('max_temp: 310',h.config.read_text());self.assertIn('hotend_target_max: 305',h.config.read_text())
  self.assertEqual(install.plan(h.root,h.config,thermal_305105=True),[])
  install.rollback(receipt,h.root,h.config);self.assertEqual(h.config.read_text(),original)

if __name__=='__main__':unittest.main()
