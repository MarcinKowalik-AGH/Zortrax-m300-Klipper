"""Approved artwork must advance in menus without new pixels or control I/O."""
import hashlib
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

from payload.m300_activity_graphics import ActivityGraphics, menu_symbol, procedure_symbol
from payload.m300_oem_graphics import OEMGraphics
from test_settings_information import session
from test_temperature_editor import enter, event, apply_pending

# Independently compared with the accepted RC3 build, not updated by this fix.
APPROVED = {
    'm300_activity_sprites.json': 'c64d5aa3dd4425b2c435c8bd97dd411a022dbd8cef93fe84490efdc0924703df',
    'm300_oem_sprites_131.json': '006058afcac0b9b888762a336935675bcac625b6f888e1fb10fca2872187c387',
    'm300_menu_sprites.json': 'baf8e39497f52a8d9f0957d4a2898bd27d103c545d14617cd1433b49b7cedf3a',
    'm300_cartesian_graphics.py': '43658b39a2dc360de259233c96aa71ead4bbfcbade46654c921d8292e8456721',
    'm300_klipper_logo.py': '42743be0d68327f9ca5df55753b5ce4158eed3b4c49fa92e1123ff57c54ed21a',
}


class MenuAnimationTests(unittest.TestCase):
    def test_approved_artwork_files_are_byte_identical(self):
        root = Path(__file__).resolve().parents[1] / 'payload'
        for name, sha in APPROVED.items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(), sha, name)

    def test_all_24_activity_sequences_keep_four_original_frames_and_period(self):
        graphics = ActivityGraphics()
        for name, spec in graphics.spec['symbols'].items():
            self.assertEqual(spec['frame_ms'], 500)
            frames = [graphics.get(name, i*.5)[2] for i in range(4)]
            self.assertEqual([hashlib.sha256(frame).hexdigest() for frame in frames],
                             [frame['sha256'] for frame in spec['frames']], name)
            self.assertEqual(len(set(frames)), 4, name)
            self.assertEqual(graphics.get(name, 2.)[2], frames[0])

    def test_menu_routes_render_the_approved_time_index_not_frame_zero(self):
        pages = ('main','zortrax','klipper','maintenance','material','settings',
                 'information','native_pid','native_moves','native_move_x',
                 'native_move_y','native_move_z','fans','bed_mesh',
                 'setting_oled_brightness','setting_led_brightness',
                 'setting_full_platform_preheat','setting_sound','setting_light_mode',
                 'setting_language','setting_sort_mode','setting_sleep_mode')
        with session() as h:
            h.objects['m300_pad_mesh'] = NS(get_status=lambda now:dict(state='IDLE',busy=False,result=None))
            events_before = list(h.events)
            targets = h.hotend.target, h.bed.target
            checked = changing = 0
            for page in pages:
                h.menu.page = page
                rows = h.menu.rows(h.now)[1]
                for selected in range(len(rows)):
                    images = []
                    for now in (0., .5, 1., 1.5, 2.):
                        actual = h.ui.get_oem_sprite('m04',rows,selected,now)
                        if actual is not None:
                            self.assertEqual(actual,h.ui.oem_sprites.get(h.ui.last_sprite,now),
                                             (page,selected,h.ui.last_sprite,now))
                            images.append(actual[2])
                    if images:
                        checked += 1
                        changing += len(set(images))>1
                        self.assertEqual(len(images),5)
            self.assertGreater(checked,80)
            self.assertGreater(changing,50)
            self.assertEqual((h.hotend.target,h.bed.target),targets)
            self.assertFalse(any(e[0] in ('heat','move','fan') for e in h.events[len(events_before):]))

    def test_temperature_and_brightness_full_render_changes_only_the_icon(self):
        for page,selected,y_start in (('temperature_HOTEND',31,0),('temperature_BED',21,0),
                                     ('setting_oled_brightness',8,7),('setting_led_brightness',8,7)):
            with self.subTest(page=page),session() as h:
                if page.startswith('temperature'):
                    enter(h,page[12:])
                else:
                    h.menu.page=page
                h.oled.selection=selected
                wires=[]
                for now in (0.,.5,1.,1.5,2.):
                    h.oled._render(now);wires.append(h.oled._render_wire)
                self.assertGreater(len(set(wires)),1)
                self.assertEqual(wires[0],wires[-1])
                for wire in wires[1:]:
                    for y in range(64):
                        self.assertEqual(wire[y*128:y*128+100],wires[0][y*128:y*128+100])
                self.assertEqual((h.hotend.target,h.bed.target),(0.,0.))

    def test_temperature_accepts_acknowledged_prior_animation_of_same_choice(self):
        for kind in ('HOTEND','BED'):
            with self.subTest(kind=kind),session() as h:
                parent=enter(h,kind);event(h,1)
                h.oled._render(h.now);h.panel_display.pump()
                previous=h.oled.stream.previous
                h.now+=.5;h.oled._render(h.now)  # New animation not ACKed yet.
                self.assertNotEqual(h.oled._render_wire,previous)
                self.assertEqual(h.ui.temperature_receipt(h.oled.stream),(h.menu.generation,h.oled.selection))
                event(h,2,shorts=1);apply_pending(h)
                self.assertEqual(h.hotend.target if kind=='HOTEND' else h.bed.target,
                                 200 if kind=='HOTEND' else 60)
                self.assertEqual((h.menu.page,h.oled.selection),('klipper',parent))

    def test_new_temperature_draft_cannot_reuse_ack_from_older_value(self):
        with session() as h:
            enter(h,'BED');event(h,1)
            h.now+=.5;h.oled._render(h.now)
            h.oled.selection+=1;h.oled._render(h.now)
            self.assertIsNone(h.ui.temperature_receipt(h.oled.stream))
            event(h,2,shorts=1)
            self.assertEqual(h.bed.target,0.)
            self.assertEqual(h.menu.page,'temperature_BED')

    def test_brightness_accepts_same_draft_ack_during_animation(self):
        with session() as h:
            h.menu.page='setting_led_brightness';h.oled.selection=8
            event(h,1);h.oled._render(h.now);h.panel_display.pump()
            previous=h.oled.stream.previous
            h.now+=.5;h.oled._render(h.now)
            self.assertNotEqual(previous,h.oled._render_wire)
            self.assertEqual(h.ui.brightness_receipt(h.oled.stream),(h.menu.generation,8))
            event(h,2,shorts=1)
            self.assertEqual(h.nvm.get_setting('led_brightness'),8)
            self.assertEqual((h.hotend.target,h.bed.target),(0.,0.))

    def test_brightness_new_value_requires_its_own_visible_receipt(self):
        with session() as h:
            h.menu.page='setting_oled_brightness';h.oled.selection=8
            h.oled._render(h.now);h.panel_display.pump()
            h.oled.selection=9;h.oled._render(h.now+.5)
            self.assertIsNone(h.ui.brightness_receipt(h.oled.stream))
            self.assertEqual(h.nvm.get_setting('oled_brightness'),16)

    def test_receipts_reject_page_epoch_generation_and_disconnected_stream(self):
        with session() as h:
            enter(h,'HOTEND')
            self.assertIsNotNone(h.ui.temperature_receipt(h.oled.stream))
            h.oled._input_epoch+=1
            self.assertIsNone(h.ui.temperature_receipt(h.oled.stream))
            h.oled._render(h.now);h.panel_display.pump()
            self.assertIsNotNone(h.ui.temperature_receipt(h.oled.stream))
            h.menu.generation+=1
            self.assertIsNone(h.ui.temperature_receipt(h.oled.stream))
            h.oled._render(h.now);h.panel_display.pump()
            h.oled.stream.ready=False
            self.assertIsNone(h.ui.temperature_receipt(h.oled.stream))
            h.oled.stream.ready=True;h.menu.page='temperature_BED'
            self.assertIsNone(h.ui.temperature_receipt(h.oled.stream))

        # A changed lower bound reinterprets an unchanged row index. The old
        # ACK cannot authorize that newly drawn temperature, even on this page.
        with session() as h:
            enter(h,'HOTEND');event(h,1)
            h.hotend.min_temp=181.
            h.oled._render(h.now+.5)
            self.assertIsNone(h.ui.temperature_receipt(h.oled.stream))
            event(h,2,shorts=1)
            self.assertEqual(h.hotend.target,0.)
            self.assertEqual(h.menu.page,'temperature_HOTEND')

    def test_receipt_storage_is_bounded_and_invalidation_clears_it(self):
        with session() as h:
            enter(h,'BED')
            for i in range(80):h.oled._render(i*.5)
            self.assertLessEqual(len(h.ui._temperature_frames),8)
            h.ui.invalidate()
            self.assertIsNone(h.ui.temperature_receipt(h.oled.stream))
            self.assertEqual(len(h.ui._temperature_frames),0)

    def test_single_frame_oem_assets_are_not_given_invented_animation(self):
        g=OEMGraphics();count=0
        for key,spec in g.frames.items():
            if len(spec['frames'])==1:
                self.assertEqual(g.get(key,0.),g.get(key,1.5));count+=1
        self.assertGreater(count,0)

    def test_live_fan_and_terminal_procedure_semantics_unchanged(self):
        self.assertFalse(menu_symbol('fan_test','m04',selected=1,fan=dict(busy=True,upper_enabled=False)).animated)
        self.assertTrue(menu_symbol('fan_test','m04',selected=1,fan=dict(busy=True,upper_enabled=True)).animated)
        self.assertIsNone(procedure_symbol('m300_maintenance',dict(state='COMPLETE',operation='HOTEND')))
        self.assertTrue(procedure_symbol('m300_maintenance',dict(state='HEATING',operation='HOTEND')).animated)

if __name__=='__main__':unittest.main()
