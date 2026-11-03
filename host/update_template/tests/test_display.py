import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from payload.m300_display_stream import DisplayStream, AWAKE, DIM, OFF
from payload.m300_display import M300Display

spec = importlib.util.spec_from_file_location(
    'reference_transport', ROOT / 'tests/reference/m300_oled_transport.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
render_spec = importlib.util.spec_from_file_location(
    'payload.m300_oled_render', ROOT / 'tests/reference/m300_oled_render.py')
renderer = importlib.util.module_from_spec(render_spec)
sys.modules[render_spec.name] = renderer
render_spec.loader.exec_module(renderer)


class Harness:
    def __init__(self, fast=True, normal=159):
        self.base = (transport.FastOledStream() if fast else transport.OledStream())
        self.stream = DisplayStream(self.base, normal=normal)
        self.now = 0.
        self.trace = []
        self.base.request(bytes([17]) * 8192)
        self.stream.start(self.now)
        self.pump()
        self.trace.clear()

    def once(self, acknowledge=True):
        op = self.stream.step(self.now)
        if op:
            kind, token, args = op
            self.trace.append(op)
            if acknowledge:
                assert self.stream.ack(token, self.now)
        self.now += .001
        return op

    def pump(self, mode=None):
        for _ in range(30000):
            self.once()
            s = self.stream
            if (self.base.ready and self.base.operations is None and not s.pending
                    and not s._local['transaction'] and not s._local['ops']
                    and s._local['wake_frame'] is None
                    and (s.display_mode == OFF or s._local.get('contrast', 159)
                         == (s._local['normal'] if s.display_mode == AWAKE
                             else s._local['dim']))
                    and (mode is None or s.display_mode == mode)
                    and (s.display_mode == OFF or self.base.previous == self.base.latest)):
                return
        raise AssertionError('Display stream did not settle')

    def commands(self):
        result = []
        for kind, _, args in self.trace:
            if kind == 'write' and args[0] == 0:
                result.extend(args[1])
            elif kind == 'burst' and args[0] == 0:
                assert args[1] == 0
                result.extend(args[3])
        return result


class StreamTests(unittest.TestCase):
    def test_contrast_change_during_transaction_remembers_value_sent(self):
        h = Harness()
        h.stream.set_mode(DIM)
        h.stream.set_dim_override(80)
        self.assertIsNotNone(h.once())  # Send C1.
        self.assertIsNotNone(h.once())  # Send the queued contrast value.
        h.stream.set_dim_override(40)
        h.once()
        self.assertEqual(h.stream.display_contrast, 80)
        h.once()
        h.once()
        self.assertEqual(h.stream.display_contrast, 40)
        self.assertEqual(h.commands(), [0xc1, 0xc1])

    def test_dim_does_not_reset_gate_or_change_frame(self):
        for fast in (True, False):
            with self.subTest(fast=fast):
                h = Harness(fast)
                frame, count = h.base.previous, h.base.completed_frames
                h.stream.set_mode(DIM)
                h.pump(DIM)
                self.assertEqual(h.commands(), [0xc1])
                self.assertEqual(h.base.previous, frame)
                self.assertEqual(h.base.completed_frames, count)
                self.assertNotIn('control', [x[0] for x in h.trace])
                self.assertEqual(h.base.sent, h.base.acked)

    def test_idle_off_and_fresh_frame_before_wake(self):
        for fast in (True, False):
            with self.subTest(fast=fast):
                h = Harness(fast)
                h.stream.set_mode(OFF)
                h.pump(OFF)
                self.assertEqual(h.commands(), [0xae])
                h.trace.clear()
                new_frame = bytes([77]) * 8192
                h.stream.request(new_frame)
                for _ in range(50):
                    self.assertIsNone(h.once())
                self.assertEqual(h.trace, [])
                h.stream.set_mode(AWAKE)
                h.pump(AWAKE)
                cmds = h.commands()
                self.assertEqual(cmds[0], 0xc1)
                self.assertIn(0x5c, cmds)
                self.assertEqual(cmds[-1], 0xaf)
                self.assertLess(cmds.index(0x5c), cmds.index(0xaf))
                self.assertEqual(h.base.previous, new_frame)
                self.assertNotIn('control', [x[0] for x in h.trace])

    def test_change_waits_for_native_frame_and_dma_ack(self):
        h = Harness()
        h.stream.request(bytes([99]) * 8192, urgent=True)
        for _ in range(4):
            h.once(acknowledge=False)
        self.assertTrue(h.base.inflight)
        h.stream.set_mode(DIM)
        self.assertIsNone(h.once(acknowledge=False))
        self.assertNotIn(0xc1, h.commands())
        for token, _, _ in list(h.base.inflight):
            h.stream.ack(token, h.now)
        h.pump(DIM)
        self.assertEqual(h.commands()[-1], 0xc1)
        self.assertEqual(h.base.previous, bytes([99]) * 8192)

    def test_mismatched_ack_cannot_apply_mode(self):
        h = Harness()
        h.stream.set_mode(OFF)
        op = h.once(acknowledge=False)
        self.assertFalse(h.stream.ack((op[1] + 1) & 65535, h.now))
        self.assertEqual(h.stream.display_mode, AWAKE)
        h.stream.ack(op[1], h.now)
        h.pump(OFF)

    def test_timeout_does_not_resume_or_drop_into_new_session(self):
        h = Harness()
        h.stream.set_mode(OFF)
        op = h.once(acknowledge=False)
        with self.assertRaises(TimeoutError):
            h.stream.step(h.now + 2.)
        self.assertFalse(h.base.enabled)
        self.assertEqual(h.base.state, 'reset_required')
        self.assertFalse(h.stream.ack(op[1], h.now + 2.))
        h.stream.set_mode(AWAKE)
        self.assertIsNone(h.stream.step(h.now + 3.))

    def test_token_wrap_preserves_native_token_owner(self):
        h = Harness()
        h.base.token = 65535
        h.stream.set_mode(DIM)
        h.pump(DIM)
        self.assertEqual([x[1] for x in h.trace], [0, 1])
        self.assertEqual(h.base.token, 1)

    def test_wake_during_pending_off_is_not_lost(self):
        h = Harness()
        h.stream.set_mode(OFF)
        off = h.once(acknowledge=False)
        h.stream.set_mode(AWAKE)
        h.stream.ack(off[1], h.now)
        h.pump(AWAKE)
        self.assertEqual(h.commands()[0], 0xae)
        self.assertEqual(h.commands()[-1], 0xaf)

    def test_reinit_finishes_contrast_data_before_reset(self):
        h = Harness()
        h.stream.set_mode(DIM)
        contrast = h.once(acknowledge=False)
        h.stream.start(h.now)
        self.assertFalse(h.base.ready)
        h.stream.ack(contrast[1], h.now)
        h.pump(AWAKE)
        self.assertEqual(h.trace[1][2][0], 1)
        self.assertIn('control', [x[0] for x in h.trace[2:]])

    def test_active_work_budget_applies_to_control_bytes(self):
        h = Harness()
        h.base.active_work = True
        h.base.work_credit = 0.
        h.base.credit_at = h.now
        h.stream.set_mode(DIM)
        self.assertIsNone(h.stream.step(h.now))
        self.assertGreater(h.stream.next_wakeup(h.now), h.now)
        h.pump(DIM)

    def test_full_frame_ram_data_cannot_be_interrupted_by_dim(self):
        h = Harness()
        h.stream.request(bytes(range(256)) * 32, urgent=True)
        h.once()
        h.stream.set_mode(DIM)
        h.pump(DIM)
        cmds = h.commands()
        self.assertEqual(cmds[-1], 0xc1)
        self.assertEqual(h.base.previous, bytes(range(256)) * 32)


class Reactor:
    NOW, NEVER = 0., 1.e30
    def __init__(self):
        self.now = 0.
    def monotonic(self):
        return self.now
    def register_timer(self, cb):
        return cb
    def update_timer(self, *args):
        pass


class Object:
    def __init__(self, **status):
        self.status = status
    def get_status(self, now):
        return dict(self.status)


class Config:
    def __init__(self, printer):
        self.printer = printer
    def get_printer(self):
        return self.printer
    def getfloat(self, name, default, **kwargs):
        return default
    def getint(self, name, default, **kwargs):
        return default


class Printer:
    def __init__(self):
        self.reactor = Reactor()
        self.events = {}
        self.commands = {}
        self.api_calls = []
        self.panel_calls = []
        self.pending_events = None
        self.oled = types.SimpleNamespace(stream=transport.FastOledStream(),
            encoder=types.SimpleNamespace(update=lambda *a: self.pending_events),
            timer=object(), render_at=0.)
        self.oled._render = lambda now: self.oled.stream.request(bytes([17]) * 8192)
        self.endpoints = {
            'gcode/script': lambda req: self.api_calls.append(req),
            'objects/query': lambda req: 'query',
            'gcode/restart': lambda req: 'restart',
            'gcode/firmware_restart': lambda req: 'firmware_restart'}
        self.objects = {
            'gcode': types.SimpleNamespace(register_command=self.register_command),
            'webhooks': types.SimpleNamespace(_endpoints=self.endpoints),
            'm300_oled': self.oled,
            'print_stats': Object(state='standby'),
            'idle_timeout': Object(state='Ready'),
            'extruder': Object(target=0.),
            'heater_bed': Object(target=0.),
            'm300_motion': types.SimpleNamespace(
                get_status=lambda now: {'busy': False, 'state': 'IDLE'},
                panel_update=lambda *a, **kw: self.panel_calls.append((a, kw)))}
    def get_reactor(self):
        return self.reactor
    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)
    def load_object(self, config, name):
        return self.objects[name]
    def register_command(self, name, handler, **kwargs):
        self.commands[name] = handler
    def register_event_handler(self, event, cb):
        self.events.setdefault(event, []).append(cb)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.p = Printer()
        self.query = self.p.endpoints['objects/query']
        self.module = M300Display(Config(self.p))
        self.module._ready()
        self.assertIsNone(self.module.error)

    def at(self, seconds):
        self.p.reactor.now = seconds
        self.module._tick(seconds)

    def go_off(self):
        self.at(300.)
        b = self.module.stream._base
        self.p.oled._render(300.)
        b.enabled = b.ready = True
        b.previous = self.module.notice_wire
        self.module.stream._local['mode'] = DIM
        self.at(300.)
        self.at(310.)

    def test_idle_notice_after_300_seconds_then_off_after_visible_notice(self):
        self.at(299.)
        self.assertEqual(self.module.stream.requested_mode, AWAKE)
        self.at(300.)
        self.assertEqual(self.module.phase, 'ENTERING_SLEEP')
        self.go_off()
        self.assertEqual(self.module.stream.requested_mode, OFF)

    def test_moon_fades_over_acknowledged_notice_and_then_turns_off(self):
        self.at(300.)
        stream = self.module.stream
        stream._base.ready = True
        stream._base.previous = self.module.notice_wire
        stream._local['mode'] = DIM
        self.at(300.5)
        start = stream._target_contrast()
        self.at(305.5)
        self.assertLess(stream._target_contrast(), start)
        stream._local['pending'] = (123, 311., 0.)
        self.at(310.25)
        self.assertEqual(stream._target_contrast(), 1)
        self.assertEqual(self.module._notice_shown_at, 300.5)
        self.at(310.5)
        self.assertEqual(stream.requested_mode, OFF)

    def test_printing_and_paused_dim_after_300_seconds(self):
        for state in ('printing', 'paused'):
            self.p.objects['print_stats'].status['state'] = state
            self.at(301.)
            self.assertEqual(self.module.stream.requested_mode, DIM)

    def test_idle_timeout_printing_flag_does_not_fake_active_machine(self):
        self.p.objects['idle_timeout'].status['state'] = 'Printing'
        self.p.objects['toolhead'] = types.SimpleNamespace(
            check_busy=lambda now: (100., 101., True))
        self.at(301.)
        self.assertEqual(self.module.phase, 'ENTERING_SLEEP')

    def test_native_queued_movement_is_work(self):
        self.p.objects['toolhead'] = types.SimpleNamespace(
            check_busy=lambda now: (101., 100., False))
        self.at(301.)
        self.assertEqual(self.module.stream.requested_mode, DIM)

    def test_heating_and_active_procedure_stay_dim(self):
        self.p.objects['extruder'].status['target'] = 200.
        self.at(301.)
        self.assertEqual(self.module.stream.requested_mode, DIM)
        self.p.objects['extruder'].status['target'] = 0.
        self.p.objects['m300_filament'] = Object(busy=True)
        self.at(302.)
        self.assertEqual(self.module.stream.requested_mode, DIM)

    def test_finish_changes_dim_to_notice_without_resetting_activity(self):
        self.p.objects['print_stats'].status['state'] = 'printing'
        self.at(301.)
        self.p.objects['print_stats'].status['state'] = 'complete'
        self.at(302.)
        self.assertEqual(self.module.phase, 'ENTERING_SLEEP')
        self.assertEqual(self.module.last_activity, 0.)

    def test_external_operator_command_wakes_and_is_forwarded_once(self):
        self.go_off()
        request = types.SimpleNamespace(get_str=lambda key: 'M106 S0')
        self.p.endpoints['gcode/script'](request)
        self.assertEqual(self.module.stream.requested_mode, AWAKE)
        self.assertEqual(self.p.api_calls, [request])

    def test_automatic_object_polling_never_wakes(self):
        self.go_off()
        self.assertIs(self.p.endpoints['objects/query'], self.query)
        for _ in range(10):
            self.p.endpoints['objects/query'](None)
        self.assertEqual(self.module.stream.requested_mode, OFF)

    def test_comment_only_script_does_not_wake(self):
        self.go_off()
        self.p.endpoints['gcode/script'](
            types.SimpleNamespace(get_str=lambda key: '; comment\n '))
        self.assertEqual(self.module.stream.requested_mode, OFF)

    def test_unattended_print_does_not_count_as_operator_activity(self):
        self.p.objects['print_stats'].status['state'] = 'printing'
        for seconds in range(400):
            # virtual_sdcard dispatches internally, without the API endpoint.
            self.at(float(seconds))
        self.assertEqual(self.module.stream.requested_mode, DIM)
        self.assertEqual(self.module.last_activity, 0.)

    def test_wake_press_hold_release_consumes_entire_gesture(self):
        self.go_off()
        base = dict(delta=0, presses=1, releases=0, shorts=0, longs=0, pressed=True)
        for delta in (base, dict(base, presses=0, longs=1),
                      dict(base, presses=0, releases=1, shorts=1, pressed=False)):
            self.p.pending_events = delta
            events = self.p.oled.encoder.update({}, self.p.reactor.now)
            self.assertTrue(all(events[k] == 0 for k in
                                ('delta', 'presses', 'releases', 'shorts', 'longs')))
        self.assertEqual(self.module.stream.requested_mode, AWAKE)

    def test_rotation_from_off_wakes_without_hidden_navigation(self):
        self.go_off()
        self.p.pending_events = dict(delta=3, pressed=False)
        events = self.p.oled.encoder.update({}, self.p.reactor.now)
        self.assertEqual(events['delta'], 0)

    def test_dim_click_keeps_normal_action(self):
        self.p.objects['print_stats'].status['state'] = 'printing'
        self.at(301.)
        self.p.pending_events = dict(delta=0, shorts=1, pressed=False)
        events = self.p.oled.encoder.update({}, 301.)
        self.assertEqual(events['shorts'], 1)
        self.assertEqual(self.module.stream.requested_mode, AWAKE)

    def test_stale_panel_cannot_wake(self):
        self.go_off()
        self.p.pending_events = dict(delta=1, pressed=False)
        self.p.oled.encoder.update({}, self.p.reactor.now - 3.)
        self.assertEqual(self.module.stream.requested_mode, OFF)

    def test_invisible_view_cannot_grant_jog_but_release_is_delivered(self):
        self.go_off()
        self.p.objects['m300_motion'].panel_update({'pressed': False}, 301., 2,
                                                  view_current=True)
        args, kw = self.p.panel_calls[-1]
        self.assertFalse(kw['view_current'])
        self.assertFalse(args[0]['pressed'])

    def test_command_error_wakes(self):
        self.at(301.)
        self.module._command_error()
        self.assertEqual(self.module.stream.requested_mode, AWAKE)

    def test_stop_cannot_issue_display_commands_or_rearm_timer(self):
        self.at(301.)
        last = self.module.last_activity
        self.module._stop()
        self.module.activity('late_command')
        self.assertEqual(self.module.last_activity, last)
        self.assertEqual(self.module._tick(400.), self.p.reactor.NEVER)

    def test_native_machine_state_never_changes(self):
        before = {k: dict(v.status) for k, v in self.p.objects.items()
                  if isinstance(v, Object)}
        self.at(301.)
        self.module.activity('encoder')
        self.assertEqual(before, {k: dict(v.status) for k, v in self.p.objects.items()
                                  if isinstance(v, Object)})


if __name__ == '__main__':
    unittest.main()
