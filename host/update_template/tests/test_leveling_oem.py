"""OEM reference pixels, shared prompts and actual OLED encoder dispatch."""
import base64
from collections import deque
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import zlib

import test_display
from test_native_leveling import Harness, homing
from payload.m300_leveling_oem import assets, describe, render, text, turn_unit
from payload.m300_oem_procedure_ui import describe as describe_service
from payload.m300_menu_ui import M300MenuUI
from payload.m300_oem_graphics import OEMGraphics
from payload.m300_oled import M300OLED
from payload.m300_procedures import M300Procedures
from payload.m300_native_motion import M300NativeMotion
from payload.m300_leveling_state import (LevelingState, stock_screw_turns,
    stock_front_delta, stock_front_accepted, stock_rear_accepted)


def presenter(h, language='EN'):
    p=M300Procedures.__new__(M300Procedures)
    p.printer=h.printer;p.reactor=h.reactor;p.timer='present';p.live=True
    p.epoch='modeled';p.revision=0
    p.identity=p.view_id=p.consumed=p.last_prompt=None
    p.changes={};p.last_keys={};p.started={}
    p.last_display=p.previous_display=None
    p.lines=[];p.gcode=NS(respond_raw=p.lines.append)
    h.objects['m300_procedures']=p
    ui=M300MenuUI.__new__(M300MenuUI)
    ui.language=lambda:language
    ui.procedures=p;ui.printer=h.printer;ui.oem_sprites=OEMGraphics()
    ui._leveling_frames=deque(maxlen=16)
    h.objects['m300_menu_ui']=ui
    return p,ui


class OEMLevelingTests(unittest.TestCase):
    def test_twenty_thousand_and_two_original_quarter_turn_vectors(self):
        fixture=json.loads((Path(__file__).parent/'reference/stock_quarter_turn_vectors.json').read_text())
        for profile in fixture['profiles']:
            scale=int(profile['steps_per_mm'])
            for delta,expected in enumerate(profile['quarter_turns_by_delta_raw'],profile['first_delta_raw']):
                self.assertEqual(stock_screw_turns(delta,scale)*4,expected,(scale,delta))

    def test_recovered_wizard_pair_and_confirmation_order_is_unchanged(self):
        machine=LevelingState(samples=1,stock_steps_per_mm=400,
                              directions={s:'CCW' for s in ('rear_left','rear_right','front')})
        token=machine.start(0.);machine.confirm(token,machine.phase_id,0.);machine.heated(token,0.)
        heights={0:160,1:0,4:0,3:20,2:160};events=[]
        for _ in range(30):
            if machine.state=='PROBING':
                p=machine.next_point;events.append(p)
                machine.measured(token,machine.phase_id,p,[heights[p]/400.],1.)
            elif machine.state=='ADJUST':
                ins=machine.instruction
                events.append((ins['screw'],ins['turns']))
                for p in ({'rear_left':[4],'rear_right':[3],'front':[0,1]}[ins['screw']]):
                    heights[p]=160
                machine.confirm(token,machine.phase_id,1.)
            else:break
        self.assertEqual(events,[0,1,4,3,('rear_left',1.),('rear_right',.75),3,4,('front',.5),1,0,2])
        self.assertEqual(machine.reference_raw,160)
        self.assertEqual(machine.state,'REVIEW')
        self.assertEqual(machine.corrections[0]['source_measurements'],machine.corrections[1]['source_measurements'])

    def test_signed_front_average_and_rear_front_tolerance_boundaries(self):
        self.assertEqual(stock_front_delta(-81,-78),-79)
        for scale in (400,800):
            for bound in (-scale//5,scale//10):
                self.assertTrue(stock_rear_accepted(bound,scale))
                self.assertFalse(stock_front_accepted(bound,scale))

    def test_one_hundred_ten_frames_match_original_register_c_pixels_in_all_five_languages(self):
        fixture=json.loads((Path(__file__).parent/'reference/leveling_oem_frames.json').read_text())
        sprites=OEMGraphics()
        self.assertEqual(len(fixture['frames']),110)
        for record in fixture['frames']:
            with self.subTest(language=record['language'],status=record['status']):
                expected=zlib.decompress(base64.b64decode(record['wire_zlib_b64']))
                self.assertEqual(hashlib.sha256(expected).hexdigest(),record['sha256'])
                status=record['status']
                screen=(describe_service(status['oem_owner'],status,record['language'])
                        if 'oem_owner' in status else describe(status,record['language']))
                actual=render(screen,sprites,test_display.renderer.Frame)
                self.assertEqual(actual,expected)

    def test_binary_descriptor_text_and_sprite_associations_are_explicit(self):
        expected={124:'0x801c434',125:'0x801fe50',126:'0x801ca28',127:'0x801ca28',128:'0x801ca28',
                  129:'0x801f0cc',130:'0x801fc6c',131:'0x801e90c',132:'0x801f4c0',
                  133:'0x801ed14',134:'0x801f8b4',136:'0x801fe34',137:'0x801c024'}
        for record in assets()['descriptors'].values():
            if record['text_id'] in expected:
                self.assertEqual(record['sprite'],expected[record['text_id']])
        self.assertEqual(text(124,'PL'),'UWAGA: Głowica będzie gorąca\npodczas poziomowania. Zalecamy\nużycie rękawic ochronnych')
        self.assertEqual(text(125,'EN'),'Please tighten three calibration\nknobs at the bottom of the\nplatform and press the button')

    def test_recovered_turn_labels_retain_front_wizard_special_case(self):
        for screw,turns,unit in (('rear_left',.75,'obrotu'),('rear_right',1.,'obrót'),
                                 ('rear_left',3.,'obroty'),('rear_right',5.,'obrotów'),
                                 ('front',.5,'obrót'),('front',1.25,'obrót'),('front',2.,'obroty')):
            self.assertEqual(turn_unit(dict(screw=screw,turns=turns),'PL'),unit)

    def test_every_operator_prompt_uses_the_exact_same_text_as_oled(self):
        for language in ('EN','PL','FR','DE','ES'):
            h=Harness();p,ui=presenter(h,language)
            h.c.start();h.until('WAIT_WARNING')
            states=[h.c.get_status(h.now)]
            for status in states+[dict(states[0],state='WAIT_TIGHTEN'),
                    dict(states[0],state='ADJUST',instruction=dict(screw='rear_left',action='LOOSEN',
                         delta_mm=-.4,turns=1.))]:
                h.c.get_status=lambda now,status=status:status
                view=p.view(h.now);p.lines.clear();p._prompt(view)
                visible=[line.removeprefix('// action:prompt_text ') for line in p.lines
                         if line.startswith('// action:prompt_text ')]
                self.assertEqual(visible,view['leveling_screen']['text'].split('\n'))
                self.assertFalse(any('Session ' in line or 'WAIT_' in line for line in visible))

    def test_native_panel_telemetry_compatibility_never_moves_or_homes(self):
        motion=M300NativeMotion.__new__(M300NativeMotion)
        motion.state='IDLE'
        for pressed in (True,False):
            self.assertIsNone(motion.panel_update({'pressed':pressed},123.,'old-lease',True))
        self.assertEqual(motion.__dict__,{'state':'IDLE'})

    def test_fault_prompt_survives_shutdown_with_all_actions_revoked(self):
        h=Harness();p,ui=presenter(h)
        h.c.start()
        h.objects['m300_filament']=NS(get_status=lambda now:dict(state='FAULT',session_token='older',
                                                phase_id=5,busy=False,ready=False))
        h.c.machine.terminate('NO_RELEASE: PC7 remains active',h.now,fault=True)
        p.invalidate()
        self.assertFalse(p.live)
        self.assertIn('// action:prompt_text Error #042 Pad probing failed.',p.lines)
        self.assertFalse(any(line.startswith('// action:prompt_button ') for line in p.lines))
        self.assertEqual(p.lines[-1],'// action:prompt_show')

    def test_real_oled_dispatch_requires_acknowledged_phase_and_rejects_delayed_click(self):
        with patch.dict('sys.modules',{'payload.homing':homing}):
            h=Harness();p,ui=presenter(h)
            display=test_display.Harness()
            o=M300OLED.__new__(M300OLED)
            o.printer=h.printer;o.reactor=h.reactor;o.stream=display.stream
            o.generation=1;o._input_epoch=0;o.page='m04';o.selection=0;o.message=None
            o.connected=o.fast=True;o._user_refresh_pending=False
            o._render_key=o._render_wire=o._presented_context=o._presented_actions=None
            o.job_token=o.cancel_token=o.filament_token=o.filament_phase_id=o.filament_cancel_token=None
            o.render_count=0;o.render_max_ms=0.;o.render_at=0.;o.timer='oled'
            o.encoder=test_display.transport.EncoderSnapshots(4,validated=True)
            menu=NS(page='procedure',generation=1,_motion_jog_token=None,
                    maintenance=NS(activity=lambda:None,click=lambda:None))
            menu.home=lambda:setattr(menu,'page','main')
            ui.menu=menu;ui.oled=o
            h.objects.update(m300_oled=o,m300_menu=menu)
            h.motion.panel_update=lambda *args,**kw:None
            h.reactor.register_async_callback=lambda cb:cb(h.now)
            h.c.start();h.until('WAIT_WARNING');o._render(h.now)
            def click(seq,count):
                o._panel(dict(sequence=seq,position=0,nav_position=0,invalid=0,
                    presses=count,releases=count,shorts=count,longs=0,pressed=False,
                    **{'#receive_time':h.now}))
            click(1,0);click(2,1)
            self.assertEqual(h.c.machine.state,'WAIT_WARNING')
            self.assertIsNone(ui.leveling_receipt(o.stream))
            display.pump()
            # Capture a click while the warning is visible, then change phase
            # via Fluidd before the queued native callback is delivered.
            queue=[];h.reactor.register_async_callback=queue.append
            click(3,2);old=p.view_id;p.action(old,'CONFIRM')
            self.assertEqual(h.c.machine.state,'WAIT_TIGHTEN')
            queue.pop()(h.now)
            self.assertEqual(h.c.machine.state,'WAIT_TIGHTEN')
            h.reactor.register_async_callback=lambda cb:cb(h.now)
            o._render(h.now);display.pump();click(4,3)
            self.assertEqual(h.c.machine.state,'PROBING')
            self.assertTrue(any(e[0]=='home' for e in h.events))


if __name__=='__main__':unittest.main()
