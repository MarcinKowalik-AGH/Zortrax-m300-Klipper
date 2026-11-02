import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import types
import unittest

import test_display as fixture
from payload.m300_display_oem import (
    ENTERING_TEXT, MOON_SHA256, load_moon, sleep_wire)
from payload.m300_display_stream import AWAKE, DIM, OFF
from payload.m300_display import M300Display


class OEMAssetTests(unittest.TestCase):
    def test_exact_audited_moon_and_english_text(self):
        width, height, raw = load_moon()
        self.assertEqual((width, height, len(raw)), (50, 50, 1250))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), MOON_SHA256)
        self.assertEqual(ENTERING_TEXT, 'Entering sleep mode')

    def test_original_sprite_pixels_survive_framebuffer_packing(self):
        sprite = load_moon()
        f = fixture.renderer.Frame()
        f.original_sprite(sprite)
        for y in range(50):
            for x in range(50):
                p = y * 50 + x
                expected = (sprite[2][p // 2] >> (4 if p % 2 == 0 else 0)) & 15
                self.assertEqual(f.get_pixel(202 + x, 7 + y), expected)
        self.assertEqual(len(sleep_wire(fixture.renderer.Frame, sprite)), 8192)

    def test_changed_or_unverified_artwork_is_rejected(self):
        original = fixture.ROOT / 'payload/m300_display_moon.json'
        d = json.loads(original.read_text())
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'moon.json'
            d['descriptor'] = '0x0801c958'
            p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):
                load_moon(p)

    def test_source_hash_is_not_a_substitute_for_frame_hash(self):
        d = json.loads((fixture.ROOT / 'payload/m300_display_moon.json').read_text())
        import base64
        import zlib
        d['frames'][0]['zlib_b64'] = base64.b64encode(
            zlib.compress(bytes(1250))).decode()
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'moon.json'
            p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):
                load_moon(p)


class SleepPolicyTests(fixture.PolicyTests):
    # Additional cases use the same initialized M300Display fixture. Parent
    # cases run only in their original suite, avoiding duplicate test counts.
    pass


for _name in dir(fixture.PolicyTests):
    if _name.startswith('test_'):
        setattr(SleepPolicyTests, _name, None)


def test_notice_waits_for_actual_frame_ack(self):
    self.at(300.)
    self.at(900.)
    self.assertEqual(self.module.phase, 'ENTERING_SLEEP')
    self.assertIsNone(self.module._notice_shown_at)
    self.assertNotEqual(self.module.stream.requested_mode, OFF)


def test_notice_waits_for_pending_dma_and_contrast(self):
    self.at(300.)
    b = self.module.stream._base
    b.enabled = b.ready = True
    b.previous = self.module.notice_wire
    b.inflight.append((123, 302., 0.))
    self.at(300.1)
    self.assertIsNone(self.module._notice_shown_at)
    b.inflight.clear()
    self.at(300.2)
    self.assertIsNone(self.module._notice_shown_at)  # contrast not applied
    self.module.stream._local['mode'] = DIM
    self.at(300.3)
    self.assertEqual(self.module._notice_shown_at, 300.3)
    self.at(310.2)
    self.assertEqual(self.module.phase, 'ENTERING_SLEEP')
    self.at(310.4)
    self.assertEqual(self.module.phase, OFF)


def test_notice_render_does_not_present_menu_actions(self):
    self.at(300.)
    self.p.oled._presented_actions = ('unseen action',)
    self.p.oled._render(300.)
    self.assertEqual(self.module.stream.latest, self.module.notice_wire)
    self.assertIsNone(self.p.oled._presented_actions)
    self.assertIsNone(self.p.oled._presented_context)


def test_transport_reinitialization_restarts_visible_notice_duration(self):
    self.at(300.)
    b = self.module.stream._base
    b.ready = b.enabled = True
    b.previous = self.module.notice_wire
    self.module.stream._local['mode'] = DIM
    self.at(301.)
    self.assertEqual(self.module._notice_shown_at, 301.)
    b.previous = None
    self.at(309.)
    self.assertIsNone(self.module._notice_shown_at)
    b.previous = self.module.notice_wire
    self.at(315.)
    self.assertEqual(self.module.phase, 'ENTERING_SLEEP')
    self.at(324.9)
    self.assertEqual(self.module.phase, 'ENTERING_SLEEP')
    self.at(325.1)
    self.assertEqual(self.module.phase, OFF)


def test_click_cancels_notice_and_does_not_select(self):
    self.at(300.)
    self.p.pending_events = dict(shorts=1, pressed=False)
    events = self.p.oled.encoder.update({}, 300.)
    self.assertEqual(events['shorts'], 0)
    self.assertEqual(self.module.phase, AWAKE)
    self.assertTrue(self.module._presentation_wait)


def test_internal_work_start_replaces_notice_with_progress(self):
    self.at(300.)
    self.p.objects['m300_filament'] = fixture.Object(busy=True, state='HEATING')
    self.at(301.)
    self.assertEqual(self.module.phase, DIM)
    self.p.oled._render(301.)
    self.assertNotEqual(self.module.stream.latest, self.module.notice_wire)


def test_no_repeated_notice_after_off(self):
    self.go_off()
    self.at(320.)
    self.at(900.)
    self.assertEqual(self.module.phase, OFF)


def test_manual_printer_sleep_is_observed_but_not_executed(self):
    self.p.objects['m300_maintenance'] = fixture.Object(state='SLEEP')
    self.at(1.)
    self.assertEqual(self.module.phase, 'ENTERING_SLEEP')
    self.module.activity('encoder')
    self.at(2.)
    self.assertEqual(self.module.phase, AWAKE)
    self.assertEqual(self.p.objects['m300_maintenance'].status['state'], 'SLEEP')
    self.assertEqual(self.p.objects['extruder'].status['target'], 0.)
    self.assertEqual(self.p.objects['heater_bed'].status['target'], 0.)


def test_sleep_notice_is_never_shown_over_active_print(self):
    self.p.objects['print_stats'].status['state'] = 'printing'
    self.at(300.)
    self.p.oled._render(300.)
    self.assertEqual(self.module.phase, DIM)
    self.assertNotEqual(self.module.stream.latest, self.module.notice_wire)


def test_ui_stays_guarded_until_real_view_is_acknowledged(self):
    self.at(300.)
    self.module.stream._base.previous = self.module.notice_wire
    self.module.activity('operator_command')
    self.assertTrue(self.module._presentation_wait)
    b = self.module.stream._base
    b.enabled = b.ready = True
    self.module._sync_presentation()
    self.assertTrue(self.module._presentation_wait)
    self.p.oled._render(300.)
    b.previous = b.latest
    b.operations = None
    self.module._sync_presentation()
    self.assertFalse(self.module._presentation_wait)


def test_unknown_service_status_does_not_blank_a_possible_operation(self):
    self.p.objects['m300_filament'] = fixture.Object()
    self.at(300.)
    self.assertEqual(self.module.phase, DIM)


def test_diagnostic_exposes_notice_and_never_claims_hardware_pass(self):
    self.at(300.)
    s = self.module.get_status(300.)
    self.assertEqual(s['notice'], ENTERING_TEXT)
    self.assertEqual(s['oem_moon_descriptor'], '0x0801d908')
    self.assertFalse(s['hardware_verified'])
    self.assertTrue(s['screen_only'])


for _name, _fn in list(globals().items()):
    if _name.startswith('test_') and callable(_fn):
        setattr(SleepPolicyTests, _name, _fn)


class StartupContrastTests(unittest.TestCase):
    def test_custom_normal_contrast_applies_on_first_start(self):
        h = fixture.Harness(normal=80)
        self.assertEqual(h.stream._local['contrast'], 80)
        self.assertEqual(h.stream.display_mode, AWAKE)

    def test_custom_contrast_survives_full_reinit(self):
        h = fixture.Harness(normal=80)
        h.stream.start(h.now)
        h.pump(AWAKE)
        self.assertEqual(h.stream._local['contrast'], 80)

    def test_previous_release_negative_control_reproduces_ignored_contrast(self):
        from tests.reference.previous_display.m300_display_stream import (
            DisplayStream as OldStream)
        base = fixture.transport.FastOledStream()
        old = OldStream(base, normal=80)
        base.request(bytes(8192))
        old.start(0.)
        writes = []
        for i in range(30000):
            now = i * .001
            op = old.step(now)
            if op:
                writes.append(op)
                self.assertTrue(old.ack(op[1], now))
            if base.ready and base.operations is None and not old.pending:
                break
        self.assertTrue(base.ready)
        # Initialization sets 0x9f; the old adapter sends no correction to 80.
        self.assertEqual(old._local['normal'], 80)
        self.assertNotIn('contrast', old._local)
        corrected = fixture.Harness(normal=80)
        self.assertEqual(corrected.stream._local['contrast'], 80)


class CurrentOLEDIntegration(unittest.TestCase):
    def test_real_r9_panel_cancels_notice_without_opening_unseen_menu(self):
        p = fixture.Printer()
        p.reactor.register_async_callback = lambda cb: cb(p.reactor.now)
        p.sent_events = []
        p.send_event = lambda *args: p.sent_events.append(args)
        oled_type = importlib.import_module('tests.reference.m300_oled').M300OLED
        o = oled_type.__new__(oled_type)
        o.__dict__.update(p.oled.__dict__)
        o.printer, o.reactor = p, p.reactor
        o.encoder = fixture.transport.EncoderSnapshots(4, validated=True)
        o.generation, o._input_epoch = 1, 0
        o.connected = o.fast = True
        o.page, o.selection, o.message = 'status', 0, None
        o.job_token = o.cancel_token = o.filament_token = None
        o.filament_phase_id = o.filament_cancel_token = None
        o._presented_actions = o._presented_context = None
        o._user_refresh_pending = False
        o._send_one = lambda now: None
        p.oled = p.objects['m300_oled'] = o
        display = M300Display(fixture.Config(p))
        display._ready()
        self.assertIsNone(display.error)
        b = display.stream._base
        b.ready = b.enabled = True
        b.operations = None
        def snapshot(seq, presses, releases, shorts, pressed):
            return dict(sequence=seq, position=0, nav_position=0, invalid=0,
                        presses=presses, releases=releases, shorts=shorts,
                        longs=0, pressed=pressed, **{'#receive_time': p.reactor.now})
        o._panel(snapshot(1, 0, 0, 0, False))
        p.reactor.now = 300.
        display._tick(300.)
        self.assertEqual(display.phase, 'ENTERING_SLEEP')
        o._panel(snapshot(2, 1, 0, 0, True))
        o._panel(snapshot(3, 1, 1, 1, False))
        self.assertEqual(display.phase, AWAKE)
        self.assertEqual(o.page, 'status')
        self.assertEqual(o.selection, 0)
        self.assertTrue(all(not e[2].get('shorts') for e in p.sent_events
                            if e[0] == 'm300:panel'))


if __name__ == '__main__':
    unittest.main()
