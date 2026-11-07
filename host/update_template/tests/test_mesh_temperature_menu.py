"""Mesh temperature defaults, Klipper grouping and distinct homing animations."""
import unittest

import m300_profile
from setup_fluidd import category, merge_groups
import test_pad_mesh
from test_pad_mesh_oled import pad
from test_procedure_return import motion
from test_settings_information import session


class MeshTemperatureMenuTests(unittest.TestCase):
    def test_2532_degree_idle_nozzle_uses_the_260_mesh_default_without_changing_g28_policy(self):
        mesh, case = test_pad_mesh.PadMeshTests().preflight_case('xyz')
        mesh.hotend_temperature = 260.
        case.temps.update(hotend=(253.2,0.), bed=(60.,60.))
        mesh._preflight()
        self.assertEqual(mesh.targets,dict(hotend=260.,bed=60.))
        self.assertEqual(mesh.motion.z_home_hotend_target,180.)

    def test_explicit_mesh_target_and_hotter_working_temperature_are_retained(self):
        for actual,current,override,expected in ((25.,0.,185.,185.),
                (270.,270.,None,270.),(275.,0.,None,275.)):
            mesh,case=test_pad_mesh.PadMeshTests().preflight_case('xyz')
            mesh.hotend_temperature=260.
            case.temps['hotend']=(actual,current)
            mesh.temperature_params={} if override is None else {'HOTEND_TEMP':override}
            mesh._preflight()
            self.assertEqual(mesh.targets['hotend'],expected)

    def test_mesh_default_migration_preserves_other_services_and_custom_values(self):
        for old in ('180','180.0','1.8e2'):
            source='[m300_pad_mesh]\nhotend_temperature: '+old+'\ncenter_x: 155\n'
            result=m300_profile.convert_text(source)
            self.assertIn('hotend_temperature: 260',result)
            self.assertIn('center_x: 155',result)
            self.assertEqual(m300_profile.convert_text(result),result)
        for custom in ('185','240','260','280'):
            source='[m300_pad_mesh]\nhotend_temperature: '+custom+'\n'
            self.assertEqual(m300_profile.convert_text(source),source)
        source='[m300_motion]\nmode: native\nz_home_hotend_target: 180\n'
        self.assertEqual(m300_profile.convert_text(source),source)

    def test_mesh_moves_to_klipper_group_without_unhiding_or_recoloring_the_macro(self):
        before=dict(categories=[dict(id='z',name='ZORTRAX M300')],stored=[
            dict(name='ZORTRAX_BED_MESH',categoryId='z',visible=False,color='purple')])
        after,assigned=merge_groups(before,['ZORTRAX_BED_MESH','ZORTRAX_LEVEL'])
        target=next(c['id'] for c in after['categories'] if c['name']=='Klipper')
        self.assertEqual(after['stored'][0],dict(name='ZORTRAX_BED_MESH',categoryId=target,visible=False,color='purple'))
        self.assertEqual(assigned['ZORTRAX_BED_MESH'],'Klipper')
        self.assertEqual(category('ZORTRAX_LEVEL'),'ZORTRAX M300')
        self.assertEqual(merge_groups(after,list(assigned))[0],after)

    def test_mesh_oled_entry_and_idle_back_belong_to_klipper(self):
        with session() as h:
            pad(h)
            h.menu.page='klipper'
            self.assertIn(('Bed mesh (25 points)',('page','bed_mesh')),h.menu.rows(h.now)[1])
            for page in ('zortrax','maintenance'):
                h.menu.page=page
                self.assertFalse(any(action==('page','bed_mesh') for _,action in h.menu.rows(h.now)[1]))
            h.menu.page='bed_mesh'
            self.assertEqual(h.menu.rows(h.now)[1][0],('Back',('page','klipper')))

    def test_xy_z_all_animate_in_both_menu_previews_and_active_native_procedures(self):
        for operation,key in (('HOME_XY','homing-xy'),('HOME_Z','homing-z'),('HOME_ALL','homing-all')):
            with self.subTest(operation=operation),session() as h:
                h.menu.page='maintenance'
                _,rows=h.menu.rows(h.now)
                command='ZORTRAX_'+operation
                selected=next(i for i,(_,action) in enumerate(rows) if action==('native_gcode',command))
                frames=[h.ui.get_oem_sprite('m04',rows,selected,i*.5)[2] for i in range(4)]
                self.assertEqual(h.ui.last_sprite,key)
                self.assertEqual(len(set(frames)),4)
                status,update=motion(h)
                update(operation=operation)
                _,rows=h.menu.rows(h.now)
                h.events.clear()
                active=[h.ui.get_oem_sprite('m04',rows,0,i*.5)[2] for i in range(4)]
                self.assertEqual(h.ui.last_sprite,key)
                self.assertEqual(active,frames)
                self.assertFalse(any(event[0] in ('move','heat','fan') for event in h.events))
