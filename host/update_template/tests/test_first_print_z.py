"""User-qualified Z variant; modeled hardware, never a physical printer test."""
import math
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_display
import m300_first_print_config as migration
import m300_profile as profile
import install
from payload.m300_native_motion import M300NativeMotion
from test_normal_operations import motion_fixture
from test_native_z_release import CoarseHome
from test_native_leveling import Harness


class ContactClearanceTests(unittest.TestCase):
    def make(self, value):
        motion=motion_fixture();motion.clearance=value
        motion.toolhead.set_position([150.,158.,0.,17.]);motion.events.clear()
        return motion

    def test_default_five_is_unchanged(self):
        m=self.make(5.);m.home(axes='xyz')
        self.assertEqual([e[1][2] for e in m.events if e[0]=='move' and e[1][2] is not None],[5.,5.])

    def test_configured_two_applies_to_initial_and_final_clearance(self):
        m=self.make(2.);m.home(axes='xyz')
        self.assertEqual([e[1][2] for e in m.events if e[0]=='move' and e[1][2] is not None],[2.,2.])
        self.assertEqual(m.result['initial_clearance']['commanded_distance_mm'],2.)
        self.assertEqual(m.get_status(0)['z_initial_clearance_mm'],2.)
        self.assertEqual(m.toolhead.get_position()[3],17.)

    def test_two_requires_pc7_open_before_any_xy(self):
        m=self.make(2.);m.precision.endstop.query_endstop=Mock(return_value=True)
        with self.assertRaisesRegex(RuntimeError,'NO_RELEASE'):m.home(axes='xyz')
        self.assertEqual([e for e in m.events if e[0]=='home'],[])
        self.assertEqual([e[1][2] for e in m.events if e[0]=='move'],[2.])
        self.assertNotIn('z',m.homed)

    def test_two_does_not_exceed_upper_limit(self):
        m=self.make(2.);m.toolhead.set_position([150.,158.,314.,17.])
        with self.assertRaisesRegex(RuntimeError,'CLEARANCE'):m.home(axes='xy')
        self.assertEqual(m.events,[])
        self.assertNotIn('z',m.homed)

    def test_known_clear_low_position_targets_two_not_another_two(self):
        m=self.make(2.);m.homed=set('xyz');m.toolhead.set_position([150.,158.,1.5,17.])
        m.ensure_xy_clearance(lambda:m._check(m.token))
        self.assertEqual(m.toolhead.get_position()[2],2.)
        self.assertTrue(m.ensure_xy_clearance(lambda:m._check(m.token))['clearance_reused'])
        self.assertEqual(len(m.events),1)

    def test_second_pass_uses_configured_two(self):
        for scale in (400,800):
            with self.subTest(scale=scale):
                h=CoarseHome(scale,release_at=2.);h.motion.clearance=2.;h.run()
                self.assertTrue(h.session_ended)
                self.assertEqual(h.motion.native_z_checks[-1]['retreat_mm'],2.)
                self.assertTrue(h.motion.native_z_checks[-1]['pc7_open'])
                self.assertEqual(h.h.position[2],0.)

    def test_second_pass_stuck_stops_without_extra_search(self):
        h=CoarseHome(release_at=float('inf'));h.motion.clearance=2.
        with self.assertRaisesRegex(RuntimeError,'NO_RELEASE'):h.run()
        self.assertEqual(h.starts,1)
        self.assertEqual(h.motion.native_z_checks[-1]['retreat_mm'],2.)

    def test_clearance_constructor_minimum_and_nan(self):
        class Config:
            error=ValueError
            def __init__(self,value):
                self.value=value
                self.printer=NS(get_reactor=lambda:NS(),lookup_object=lambda name:Mock(),
                                load_object=lambda *a:Mock(),register_event_handler=Mock())
            def get_printer(self):return self.printer
            def getfloatlist(self,name,default,**kw):return default
            def getfloat(self,name,default,**kw):
                value=self.value if name=='z_contact_clearance' else default
                if 'minval' in kw and value<kw['minval']:raise ValueError(name)
                return value
        for value in (0.,1.,1.999,float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError):M300NativeMotion(Config(value))
        for value in (2.,5.):self.assertEqual(M300NativeMotion(Config(value)).clearance,value)

    def test_negative_z_geometry_needs_six_point_five(self):
        h=Harness();h.job._axis_bounds=lambda:([0.,0.,-.5],[300.,305.,315.])
        h.c.safe_z=5.;h.c.search_margin=1.;h.c.approach_distance=6.
        with self.assertRaisesRegex(RuntimeError,'approach_distance'):h.c._geometry()
        h.c.approach_distance=6.5
        self.assertEqual(h.c._geometry()['safe_z'],5.)
        self.assertEqual(h.c._geometry()['approach_distance'],6.5)

    def test_reported_mesh_move_is_inside_qualified_range(self):
        physical_z=.28+(4.630914-5.)
        self.assertAlmostEqual(physical_z,-.089086,places=6)
        self.assertLess(physical_z,0.)
        self.assertGreaterEqual(physical_z,-.5)
        # This calculation is not a measured clearance or approval of other beds.


class QualifiedConfigurationTests(unittest.TestCase):
    CONFIG=('[mcu]\nserial: /dev/ttyS1\nbaud: 1500000\n'
            '[stepper_x]\nposition_max: 300\n[stepper_y]\nposition_max: 305\n'
            '[stepper_z]\nposition_min: 0\nposition_max: 315\nrotation_distance: 4\n'
            '[m300_motion]\nmode: native\nz_contact_clearance: 5\n'
            '[m300_calibration]\nsafe_z: 5\napproach_distance: 6.0\nprobe_search_margin: 1\n'
            '[m300_print_control]\npurge_height: 0.28\n'
            '#*# <---------------------- SAVE_CONFIG ---------------------->\n'
            '#*# [bed_mesh m300_pads]\n#*# points = -0.4497, 0.0965\n')

    def setup_install(self):
        from test_install import InstallerTests
        h=InstallerTests(methodName='runTest');h.setUp();self.addCleanup(h.tearDown)
        h.config.write_text(self.CONFIG)
        return h

    def planned(self,text=None):
        p=Path('/tmp/m300-test-config/printer.cfg');tree={p:text or self.CONFIG}
        return p,tree,{p:tree[p].encode()}

    def test_flag_is_required_to_lower_z_or_clearance(self):
        h=self.setup_install();changes=install.plan(h.root,h.config)
        content=dict((p,new) for p,old,new in changes).get(h.config,h.config.read_bytes()).decode()
        self.assertIn('position_min: 0',content);self.assertIn('z_contact_clearance: 5',content)

    def test_known_profile_updates_only_requested_options(self):
        p,tree,desired=self.planned();migration.apply_to_plan(desired,p,tree);text=desired[p].decode()
        self.assertIn('position_min: -0.5',text);self.assertIn('z_contact_clearance: 2',text)
        self.assertIn('approach_distance: 6.5',text);self.assertIn('safe_z: 5',text)
        self.assertIn('purge_height: 0.28',text);self.assertIn('position_max: 305',text)
        self.assertIn('baud: 1500000',text);self.assertIn('rotation_distance: 4',text)
        self.assertEqual(profile.split_saved(text)[1],profile.split_saved(tree[p])[1])

    def test_repeat_is_idempotent(self):
        p,tree,desired=self.planned();migration.apply_to_plan(desired,p,tree);once=dict(desired)
        migration.apply_to_plan(desired,p,{p:desired[p].decode()});self.assertEqual(desired,once)

    def test_included_settings_updated_in_their_own_file(self):
        p=Path('/tmp/m300-test-config/printer.cfg');q=p.parent/'services/settings.cfg'
        body=self.CONFIG.split('[m300_motion]',1)
        tree={p:body[0]+'[include services/settings.cfg]\n',q:'[m300_motion]'+body[1]}
        desired={k:v.encode() for k,v in tree.items()};migration.apply_to_plan(desired,p,tree)
        self.assertIn(b'position_min: -0.5',desired[p]);self.assertNotIn(b'z_contact_clearance',desired[p])
        self.assertIn(b'z_contact_clearance: 2',desired[q]);self.assertEqual(desired[q].count(b'[m300_motion]'),1)

    def test_duplicate_sections_refused(self):
        p,tree,desired=self.planned(self.CONFIG+'\n')
        tree[p]=self.CONFIG.split('#*#',1)[0]+'[stepper_z]\nposition_min: 0\n'
        desired[p]=tree[p].encode();before=dict(desired)
        with self.assertRaisesRegex(ValueError,'one existing'):migration.apply_to_plan(desired,p,tree)
        self.assertEqual(desired,before)

    def test_duplicate_options_refused(self):
        p,tree,desired=self.planned(self.CONFIG.replace('position_min: 0','position_min: 0\nposition_min: -0.5'))
        with self.assertRaisesRegex(ValueError,'Duplicate'):migration.apply_to_plan(desired,p,tree)

    def test_unknown_custom_values_refused_without_mutation(self):
        for old,new in [('position_min: 0','position_min: -1'),('safe_z: 5','safe_z: 10'),
                        ('approach_distance: 6.0','approach_distance: 8'),
                        ('probe_search_margin: 1','probe_search_margin: 0'),
                        ('z_contact_clearance: 5','z_contact_clearance: 7')]:
            with self.subTest(new=new):
                p,tree,desired=self.planned(self.CONFIG.replace(old,new));before=dict(desired)
                with self.assertRaisesRegex(ValueError,'Unrecognized'):migration.apply_to_plan(desired,p,tree)
                self.assertEqual(before,desired)

    def test_nan_and_inf_refused(self):
        for value in ('nan','inf','abc'):
            p,tree,desired=self.planned(self.CONFIG.replace('position_min: 0','position_min: '+value))
            with self.assertRaises(ValueError):migration.apply_to_plan(desired,p,tree)

    def test_missing_section_refused(self):
        p,tree,desired=self.planned(self.CONFIG.replace('[m300_motion]','[unrelated]'))
        with self.assertRaisesRegex(ValueError,'one existing'):migration.apply_to_plan(desired,p,tree)

    def test_saved_setting_conflict_refused(self):
        p,tree,desired=self.planned(self.CONFIG+'#*# [stepper_z]\n#*# position_min = 0\n')
        with self.assertRaisesRegex(ValueError,'SAVE_CONFIG'):migration.apply_to_plan(desired,p,tree)

    def test_experimental_safe_three_restored_to_five(self):
        p,tree,desired=self.planned(self.CONFIG.replace('safe_z: 5','safe_z: 3'))
        migration.apply_to_plan(desired,p,tree);self.assertIn(b'safe_z: 5',desired[p])

    def test_installer_apply_and_exact_rollback(self):
        h=self.setup_install();original=h.config.read_bytes()
        changes=install.plan(h.root,h.config,qualified_first_print_z=True)
        receipt=install.apply(h.root,h.config,changes)
        self.assertIn('z_contact_clearance: 2',h.config.read_text())
        self.assertEqual(install.plan(h.root,h.config,qualified_first_print_z=True),[])
        install.rollback(receipt,h.root,h.config);self.assertEqual(original,h.config.read_bytes())

    def test_ordinary_upgrade_preserves_already_qualified_configuration(self):
        h=self.setup_install();changes=install.plan(h.root,h.config,qualified_first_print_z=True)
        install.apply(h.root,h.config,changes);self.assertEqual(install.plan(h.root,h.config),[])

    def test_plan_only_does_not_write(self):
        h=self.setup_install();before=h.config.read_bytes()
        changes=install.plan(h.root,h.config,qualified_first_print_z=True)
        self.assertTrue(changes);self.assertEqual(before,h.config.read_bytes())

    def test_failed_transaction_rolls_back(self):
        h=self.setup_install();before=h.config.read_bytes()
        changes=install.plan(h.root,h.config,qualified_first_print_z=True)
        original=install.atomic_write;calls=[]
        def fail_once(path,data):
            calls.append(path)
            if len(calls)==3:raise OSError('modeled disk error')
            return original(path,data)
        with patch.object(install,'atomic_write',side_effect=fail_once):
            with self.assertRaises(OSError):install.apply(h.root,h.config,changes)
        self.assertEqual(before,h.config.read_bytes())

    def test_organizing_config_retains_single_section_and_mesh(self):
        h=self.setup_install();h.config.write_text('[m300_mcu]\nnative_control: True\n'+h.config.read_text())
        saved=profile.split_saved(h.config.read_text())[1]
        changes=install.plan(h.root,h.config,organize_config=True,qualified_first_print_z=True)
        install.apply(h.root,h.config,changes);tree=profile.read_tree(h.config)
        all_text='\n'.join(tree.values())
        self.assertEqual(all_text.count('[m300_motion]'),1)
        self.assertIn('z_contact_clearance: 2',all_text)
        self.assertEqual(profile.split_saved(h.config.read_text())[1],saved)

if __name__=='__main__':unittest.main()
