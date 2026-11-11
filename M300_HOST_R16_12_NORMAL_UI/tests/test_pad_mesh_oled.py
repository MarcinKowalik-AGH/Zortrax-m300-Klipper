"""Native pad measurement borrows the OLED; presentation never controls probing."""
from types import SimpleNamespace as NS
import unittest

from payload.m300_pad_mesh import GEOMETRY_DEFAULTS, M300PadMesh, geometry_points
from payload.m300_ui_m11_state import require_rows
from test_activity_graphics import right_icon
from test_procedure_return import motion
from test_settings_information import session


def pad(h):
    mesh = M300PadMesh.__new__(M300PadMesh)
    mesh.state,mesh.phase,mesh.busy='IDLE','IDLE',False
    mesh.run_id,mesh.report,mesh.last_attempt=None,None,None
    mesh.points_measured,mesh.last_error=0,''
    mesh.targets=dict(hotend=240.,bed=60.)
    mesh.geometry=dict(GEOMETRY_DEFAULTS)
    mesh.points=geometry_points(mesh.geometry)
    mesh.printer=NS(lookup_object=lambda name,default=None:default,send_event=h.emit)
    h.objects['m300_pad_mesh']=mesh
    def update(phase='HEATING',points=0,token='a'*24):
        mesh.phase,mesh.run_id,mesh.points_measured=phase,token,points
        mesh.state=phase if phase in ('IDLE','COMPLETE','FAILED') else 'PROBING'
        mesh.busy=mesh.state=='PROBING'
        if phase=='COMPLETE':mesh.report=dict(profile='m300_pads',run_id=token)
        mesh._notify_view()
        h.p._tick(h.now)
    return mesh,update


class PadMeshOLEDTests(unittest.TestCase):
    def test_remote_start_shows_all_four_animation_frames_without_web_prompts_or_control_io(self):
        with session() as h:
            h.oled._show_status()
            mesh,update=pad(h)
            events=list(h.events)
            targets=h.hotend.target,h.bed.target
            update()
            self.assertEqual((h.menu.page,h.oled.page),('bed_mesh','m04'))
            self.assertEqual(h.p.view(h.now)['owner'],'m300_pad_mesh')
            _,rows=h.menu.rows(h.now)
            self.assertIn(('Heating nozzle / bed',None),rows)
            self.assertIn(('Nozzle: 240 C',None),rows)
            self.assertTrue(require_rows(rows))
            frames=[]
            for index in range(4):
                now=h.now+index*.5
                h.oled._render(now)
                self.assertEqual(h.ui.last_sprite,'activity:bed_mesh')
                frame=right_icon(h.oled._render_wire)
                self.assertEqual(frame,h.ui.oem_sprites.get('activity:bed_mesh',now)[2])
                frames.append(frame)
            self.assertEqual(len(set(frames)),4)
            self.assertEqual((h.hotend.target,h.bed.target),targets)
            self.assertEqual([event for event in h.events if event[0]!='timer'],
                             [event for event in events if event[0]!='timer'])
            self.assertFalse(any('action:prompt_' in line for line in h.lines))

    def test_nested_native_homing_cannot_steal_the_measurement_or_its_return_origin(self):
        with session() as h:
            h.oled._show_status()
            mesh,update=pad(h)
            child,home=motion(h)
            update()
            origin=h.menu._procedure_return['origin']
            update('HOMING')
            home(operation='HOME_ALL')
            home('COMPLETE',operation='HOME_ALL')
            self.assertEqual(h.p.view(h.now)['owner'],'m300_pad_mesh')
            self.assertEqual(h.menu.page,'bed_mesh')
            self.assertIs(h.menu._procedure_return['origin'],origin)
            update('STABILIZING')
            update('PROBING',points=7)
            self.assertIn(('Measuring 8 / 25',None),h.menu.rows(h.now)[1])
            self.assertAlmostEqual(h.p.view(h.now)['progress'],7./25)
            update('COMPLETE',points=25)
            self.assertEqual((h.menu.page,h.oled.page),('main','status'))
            self.assertFalse(any('action:prompt_' in line for line in h.lines))

    def test_oled_start_restores_clicked_row_and_history_after_completion(self):
        with session() as h:
            mesh,update=pad(h)
            h.gcode.register_command('BED_MESH',None)
            h.gcode.register_command('BED_MESH',lambda cmd:update())
            h.menu.page='bed_mesh'
            h.ui.history.stack[:]=['main','klipper']
            rows=h.menu.rows(h.now)[1]
            selected=next(i for i,(_,action) in enumerate(rows)
                          if action==('native_gcode','BED_MESH'))
            h.oled.selection=selected
            before=len(h.callbacks)
            h.oled._select(h.now)
            h.callbacks.pop(before)(h.now)
            self.assertEqual(h.menu._procedure_return['origin']['selection'],selected)
            update('COMPLETE',points=25)
            self.assertEqual((h.menu.page,h.oled.selection),('bed_mesh',selected))
            self.assertEqual(h.ui.history.stack,['main','klipper'])

    def test_manual_brightness_navigation_is_not_overwritten_by_later_points_or_completion(self):
        with session() as h:
            h.oled._show_status()
            mesh,update=pad(h)
            update()
            h.menu._navigate('setting_led_brightness')
            h.oled.selection=9
            h.nvm.set_setting('led_brightness',9)
            update('HOMING')
            update('PROBING',points=13)
            update('COMPLETE',points=25)
            self.assertEqual((h.menu.page,h.oled.selection),('setting_led_brightness',9))
            self.assertEqual(h.nvm.get_setting('led_brightness'),9)

    def test_back_leaves_the_presentation_without_cancelling_or_reopening_this_run(self):
        with session() as h:
            h.oled._show_status()
            mesh,update=pad(h)
            update()
            action=h.menu.rows(h.now)[1][0][1]
            self.assertEqual(action,('procedure_return','m300_pad_mesh','a'*24))
            h.menu.select(action,h.now)
            self.assertTrue(mesh.busy)
            self.assertEqual(h.oled.page,'status')
            update('HOMING')
            update('PROBING',points=3)
            self.assertEqual(h.oled.page,'status')
            update('COMPLETE',points=25)
            self.assertEqual(h.oled.page,'status')

    def test_rejected_measurement_keeps_its_reason_visible_until_back(self):
        with session() as h:
            h.oled._show_status()
            mesh,update=pad(h)
            update('PROBING',points=24)
            mesh.last_error='Bed span 0.8025 exceeds 0.5000 mm'
            update('FAILED',points=25)
            self.assertEqual(h.menu.page,'bed_mesh')
            self.assertIn('0.5000',' '.join(label for label,_ in h.menu.rows(h.now)[1]))
            h.oled._render(h.now)
            self.assertEqual(h.ui.last_sprite,'0x0801be48')
            self.assertEqual(h.p.view(h.now)['actions'],[])
            h.menu.select(h.menu.rows(h.now)[1][0][1],h.now)
            self.assertEqual(h.oled.page,'status')

    def test_idle_geometry_preview_never_takes_over_the_panel(self):
        with session() as h:
            h.oled._show_status()
            mesh,update=pad(h)
            h.p._tick(h.now)
            mesh.geometry['edge_margin']=16.
            mesh.points=geometry_points(mesh.geometry)
            h.p._tick(h.now)
            self.assertEqual(h.oled.page,'status')
            self.assertIsNone(h.menu._procedure_return)
            self.assertFalse(any('action:prompt_' in line for line in h.lines))


if __name__=='__main__':unittest.main()
