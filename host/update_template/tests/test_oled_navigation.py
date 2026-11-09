"""Event-driven menu preview: actual wait completion, bounds and no old frames."""
import base64
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import zlib

from test_oled_preview import decode_png
from test_settings_information import session
from payload.m300_oled import M300OLED
from payload.m300_oled_preview import M300OLEDPreview, WIRE_BYTES, MAX_WAITERS, WAIT_SECONDS


class Client:
    closed = False
    def is_closed(self): return self.closed


class Completion:
    def __init__(self, reactor):
        self.reactor = reactor
        self.result = None
    def complete(self, value): self.result = value
    def wait(self, deadline, default):
        self.reactor.deadlines.append(deadline)
        hook, self.reactor.hook = self.reactor.hook, None
        if hook is not None: hook()
        return self.result if self.result is not None else default


class Reactor:
    def __init__(self):
        self.now = 10.
        self.hook = None
        self.deadlines = []
    def monotonic(self): return self.now
    def completion(self): return Completion(self)


class Request:
    error = ValueError
    def __init__(self, connection, **params):
        self.client, self.params, self.result = connection, params, None
    def get_str(self, name, default=None): return self.params.get(name, default)
    def get_int(self, name, default=None): return self.params.get(name, default)
    def get_client_connection(self): return self.client
    def send(self, value): self.result = value


def pixels(value): return bytes([value]) * WIRE_BYTES


class OLEDNavigationTests(unittest.TestCase):
    def setUp(self):
        self.reactor = Reactor()
        self.endpoints = {}
        web = SimpleNamespace(register_endpoint=lambda path, cb: self.endpoints.__setitem__(path, cb))
        printer = SimpleNamespace(lookup_object=lambda name, default=None: web if name=='webhooks' else default)
        self.owner = SimpleNamespace(printer=printer, reactor=self.reactor, connected=True,
                                     stream=SimpleNamespace(ready=True, enabled=True), _render_wire=pixels(1))
        self.preview = M300OLEDPreview()
        self.preview.bind(self.owner)
        self.preview.observe_navigation(self.owner, 10., ('menu', 0))
        self.client = Client()

    def request(self, **params):
        data = dict(client='test-widget-1', epoch=self.preview._epoch,
                    navigation_revision=self.preview._navigation)
        data.update(params)
        return Request(self.client, **data)

    def move(self, index):
        self.owner._render_wire = pixels(index + 1)
        self.preview.observe_navigation(self.owner, self.reactor.now, ('menu', index))

    def assert_pixels(self, frame, expected):
        data = base64.b64decode(frame['image_base64'])
        scan = zlib.decompress(decode_png(data)[b'IDAT'])
        actual = b''.join(scan[y*129+1:(y+1)*129] for y in range(64))
        self.assertEqual(actual, pixels(expected))

    def test_registers_only_two_read_only_navigation_endpoints(self):
        self.assertEqual(set(self.endpoints), {'m300/oled_preview/wait', 'm300/oled_preview/cancel_wait'})
        self.preview.bind(self.owner)
        self.assertEqual(len(self.endpoints), 2)

    def test_first_request_gets_current_frame_without_status_timer(self):
        req = self.request(epoch='', navigation_revision=-1)
        self.preview._wait(req)
        self.assertTrue(req.result['changed'])
        self.assert_pixels(req.result['frame'], 1)
        self.assertEqual(self.reactor.deadlines, [])

    def test_single_detent_completes_pending_wait_at_same_event_time(self):
        first = self.preview.get_status(10., True, self.owner._render_wire)
        req = self.request()
        self.reactor.now = 10.001
        self.reactor.hook = lambda: self.move(1)
        self.preview._wait(req)
        self.assertTrue(req.result['changed'])
        self.assertEqual(self.reactor.now, 10.001)
        self.assertGreater(req.result['frame']['sequence'], first['sequence'])
        self.assert_pixels(req.result['frame'], 2)
        self.assertEqual(self.preview._waiters, {})

    def test_navigation_bypasses_125ms_image_throttle(self):
        before = self.preview.get_status(10., True, pixels(1))
        self.reactor.now = 10.01
        self.move(2)
        self.assertEqual(self.preview.get_status(10.01, True, pixels(3))['sequence'], before['sequence'])
        req = self.request(navigation_revision=0)
        self.preview._wait(req)
        self.assert_pixels(req.result['frame'], 3)

    def test_fast_first_to_last_keeps_latest_not_a_queue(self):
        def burst():
            for index in range(1, 16): self.move(index)
        req = self.request()
        self.reactor.hook = burst
        self.preview._wait(req)
        self.assert_pixels(req.result['frame'], 16)
        self.assertEqual(self.preview._navigation, 16)
        self.assertEqual(self.preview._waiters, {})

    def test_changes_while_browser_paints_are_returned_on_next_request(self):
        previous = self.preview._navigation
        for index in range(1, 9): self.move(index)
        req = self.request(navigation_revision=previous)
        self.preview._wait(req)
        self.assert_pixels(req.result['frame'], 9)
        self.assertEqual(self.reactor.deadlines, [])

    def test_animation_does_not_wake_navigation_wait(self):
        req = self.request()
        def animate():
            self.owner._render_wire = pixels(33)
            self.preview.observe_navigation(self.owner, 10.01, ('menu', 0))
        self.reactor.hook = animate
        self.preview._wait(req)
        self.assertEqual(req.result, {'changed': False})
        self.assertEqual(self.preview._navigation, 1)

    def test_periodic_animation_throttle_remains_unchanged(self):
        before = self.preview.get_status(10., True, pixels(1))
        self.assertEqual(self.preview.get_status(10.1, True, pixels(2))['sequence'], before['sequence'])
        self.assertGreater(self.preview.get_status(10.125, True, pixels(2))['sequence'], before['sequence'])

    def test_wait_heartbeat_has_bounded_deadline_and_releases_slot(self):
        req = self.request()
        self.preview._wait(req)
        self.assertEqual(req.result, {'changed': False})
        self.assertEqual(self.reactor.deadlines, [10. + WAIT_SECONDS])
        self.assertEqual(self.preview._waiters, {})

    def test_hide_cancels_only_the_matching_wait(self):
        req = self.request()
        self.reactor.hook = lambda: self.preview._cancel_wait(self.request())
        self.preview._wait(req)
        self.assertEqual(req.result, {'changed': False})
        self.assertEqual(self.preview._waiters, {})

    def test_cancel_from_another_api_connection_cannot_release_wait(self):
        req = self.request()
        def foreign():
            self.preview._cancel_wait(Request(Client(), client='test-widget-1'))
            self.assertIsNone(self.preview._waiters['test-widget-1'][0].result)
            self.move(1)
        self.reactor.hook = foreign
        self.preview._wait(req)
        self.assertTrue(req.result['changed'])

    def test_waiter_count_is_bounded(self):
        for index in range(MAX_WAITERS):
            self.preview._waiters[str(index)] = (Completion(self.reactor), self.client)
        with self.assertRaisesRegex(ValueError, 'Too many'):
            self.preview._wait(self.request())
        self.assertEqual(len(self.preview._waiters), MAX_WAITERS)

    def test_duplicate_client_does_not_overwrite_an_outstanding_wait(self):
        record = (Completion(self.reactor), self.client)
        self.preview._waiters['test-widget-1'] = record
        with self.assertRaisesRegex(ValueError, 'already pending'):
            self.preview._wait(self.request())
        self.assertIs(self.preview._waiters['test-widget-1'], record)

    def test_malformed_cursor_is_rejected_without_rendering_or_motion(self):
        for params in ({'client':''}, {'client':'a'*65}, {'client':'../gcode'},
                       {'navigation_revision':-2}, {'epoch':'x'*65}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.preview._wait(self.request(**params))
        self.assertEqual(self.preview._sequence, 0)

    def test_reset_invalidates_epoch_and_immediately_releases_wait(self):
        old_epoch = self.preview._epoch
        req = self.request()
        def disconnect():
            self.owner.connected = False
            self.owner._render_wire = None
            self.preview.reset()
        self.reactor.hook = disconnect
        self.preview._wait(req)
        self.assertNotEqual(req.result['frame']['epoch'], old_epoch)
        self.assertFalse(req.result['frame']['online'])
        self.assertEqual(req.result['frame']['image_base64'], '')

    def test_disconnected_api_client_is_not_given_a_new_image(self):
        req = self.request()
        def disconnect():
            self.client.closed = True
            self.move(1)
        self.reactor.hook = disconnect
        self.preview._wait(req)
        self.assertEqual(req.result, {'changed': False})

    def test_no_client_does_not_encode_images_during_navigation(self):
        for index in range(50): self.move(index)
        self.assertEqual(self.preview._sequence, 0)
        self.assertEqual(self.preview._image, '')

    def test_real_menu_renderer_publishes_last_selection_and_not_icon_ticks(self):
        with session() as h:
            mirror = h.oled._oled_preview = M300OLEDPreview()
            h.oled.stream.ready = h.oled.stream.enabled = True
            h.menu.page = 'maintenance'
            h.oled.selection = 0
            h.oled._render(h.now)
            first = mirror._navigation
            count = len(h.oled._rows(h.now)[1])
            h.oled.selection = count - 1
            h.oled._render(h.now + .001)
            self.assertEqual(mirror._navigation, first + 1)
            image = mirror._snapshot()
            data = zlib.decompress(decode_png(base64.b64decode(image['image_base64']))[b'IDAT'])
            self.assertEqual(b''.join(data[y*129+1:(y+1)*129] for y in range(64)), h.oled._render_wire)
            h.oled._render(h.now + .5)
            self.assertEqual(mirror._navigation, first + 1)

    def test_verified_beta15_modules_remain_supported_upgrade_baselines(self):
        path = Path(__file__).resolve().parents[1] / 'SUPPORTED_BASELINES.json'
        baselines = json.loads(path.read_text())
        for name, digest in {
            'm300_oled.py': '80383731e7f91b299e048188b1ff554508eb555d654bb7061bea39d694256888',
            'm300_oled_preview.py': '999dad8f13fdf3c471561cd00309d83004141c528f1c365243f5456768a55b46',
        }.items():
            self.assertIn(digest, baselines[name])

    def test_physical_renderer_is_identical_except_passive_observer(self):
        source = inspect.getsource(M300OLED._render)
        addition = """        # Navigation is published from the same completed host frame, without
        # waiting for objects/query, display ACKs, or an animation deadline.
        mirror = getattr(self, '_oled_preview', None)
        if mirror is not None:
            mirror.observe_navigation(self, now, (context, self.selection))
"""
        self.assertEqual(source.count(addition), 1)
        source = source.replace(addition, '')
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), 'b0074c1fbef3ce7851ef42901ad50bc9c9d801b8e65377232702549996c37445')


if __name__ == '__main__': unittest.main()
