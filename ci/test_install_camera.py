#!/usr/bin/env python3
# Marcin Kowalik <mkowalik@agh.edu.pl>
# test_install_camera.py - Testuje opcjonalną kamerę bez dostępu do drukarki i usług systemowych.
"""Camera opt-in, nginx selection, device filtering and transactional recovery."""
from contextlib import ExitStack
import io
import json
from email.message import Message
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

import install_camera as camera


SITE = '''# server { listen 99; }
server {
    listen 80;
    location / { return 200 "4480 # {not a server}"; }
}
server {
    listen 4480;
    listen [::]:4480;
    root /home/klipper/fluidd;
    location /server/ { proxy_pass http://127.0.0.1:7125; }
}
'''


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root/'m300_camera.conf'
        self.text = camera.template()
        self.value = camera.configuration(self.text)
        self.unit = self.root/'m300-camera.service'
        self.site = self.root/'nginx.conf'
        self.site.write_text(SITE)

    def test_default_plan_has_no_external_calls_or_writes(self):
        with patch.object(camera, 'run') as run, patch.object(camera, 'urlopen') as network, \
                patch.object(camera, 'apply') as apply, patch('sys.stdout', new_callable=io.StringIO) as out:
            camera.main(['--data', str(self.root/'missing-data')])
        self.assertFalse(json.loads(out.getvalue())['camera']['enabled'])
        run.assert_not_called()
        network.assert_not_called()
        apply.assert_not_called()
        self.assertFalse((self.root/'missing-data').exists())

    def test_config_validation_catches_typos_ports_and_unsupported_formats(self):
        self.assertEqual(camera.configuration(self.text.replace('fluidd_port: 4480', 'fluidd_port: 80'))['fluidd_port'], 80)
        for old, new in (('enabled: False', 'enable: False'), ('fps: 10', 'fps: 0'),
                         ('format: auto', 'format: H264'), ('port: 8088', 'port: 4480'),
                         ('resolution: 640x480', 'resolution: 0x480'),
                         ('device: auto', 'device: /etc/passwd')):
            with self.subTest(new=new), self.assertRaises(ValueError):
                camera.configuration(self.text.replace(old, new))

    def test_nginx_changes_selected_site_only_and_is_idempotent(self):
        updated = camera.nginx_route(SITE, 4480, 8088)
        self.assertEqual(updated.split('server {')[1], SITE.split('server {')[1])
        self.assertEqual(updated.count('location ^~ /m300-camera/'), 1)
        self.assertIn('proxy_pass http://127.0.0.1:8088/;', updated)
        self.assertEqual(camera.nginx_route(updated, 4480, 8088), updated)
        changed = camera.nginx_route(updated, 4480, 8099)
        self.assertNotIn(':8088/', changed)
        self.assertEqual(changed.count(camera.BEGIN), 1)

    def test_ambiguous_or_unmanaged_nginx_route_is_refused(self):
        for text in (SITE+'server { listen 4480; }',
                     SITE.replace('root /home/klipper/fluidd;',
                                  'location /m300-camera/ { return 404; }'),
                     SITE.replace('root /home/klipper/fluidd;', camera.BEGIN)):
            with self.subTest(text=text), self.assertRaises(ValueError):
                camera.nginx_route(text, 4480, 8088)

    def test_service_uses_loopback_video_group_and_low_priority(self):
        self.value['device'] = '/dev/v4l/by-id/usb-Test-video-index0'
        unit = camera.service(self.value, '/usr/bin/ustreamer', 'MJPEG', 'klipper')
        for expected in ('User=klipper', 'SupplementaryGroups=video', '--host=127.0.0.1',
                         '--format=MJPEG', '--slowdown', 'Nice=10', 'CPUWeight=20'):
            self.assertIn(expected, unit)
        self.assertNotIn('klipper.service', unit)
        self.assertNotIn('moonraker', unit)

    def test_pixel_format_prefers_camera_mjpeg_and_rejects_unknown_format(self):
        with patch.object(camera, 'run', return_value="[0]: 'MJPG' (Motion-JPEG)\n[1]: 'YUYV'"):
            self.assertEqual(camera.capture_format('/dev/video0', 'auto'), 'MJPEG')
        with patch.object(camera, 'run', return_value="[0]: 'YUYV'"):
            self.assertEqual(camera.capture_format('/dev/video0', 'auto'), 'YUYV')
            with self.assertRaisesRegex(ValueError, 'does not support'):
                camera.capture_format('/dev/video0', 'MJPEG')

    def test_metadata_and_non_character_device_are_not_selected(self):
        with patch.object(Path, 'is_char_device', return_value=True), \
                patch.object(camera, 'run', return_value='Metadata Capture'):
            with self.assertRaisesRegex(ValueError, 'Expected one USB capture'):
                camera.choose_device('/dev/video99')
        with patch.object(Path, 'is_char_device', return_value=True), \
                patch.object(camera, 'run', return_value='Capabilities: 0x1\n Video Capture\nDevice Caps: 0x2\n Metadata Capture'):
            with self.assertRaisesRegex(ValueError, 'Expected one USB capture'):
                camera.choose_device('/dev/video99')
        with patch.object(Path, 'is_char_device', return_value=False), patch.object(camera, 'run') as run:
            with self.assertRaises(ValueError):
                camera.choose_device('/dev/video99')
            run.assert_not_called()

    def test_video_check_requires_capture_snapshot_and_mjpeg_stream(self):
        visited = []

        class Response(io.BytesIO):
            def __init__(self, content, content_type):
                super().__init__(content)
                self.headers = Message()
                self.headers['Content-Type'] = content_type

        def request(url, **kwargs):
            visited.append(url)
            if url.endswith('/state'):
                return Response(b'{"result":{"source":{"online":true}}}', 'application/json')
            if url.endswith('/snapshot'):
                return Response(b'\xff\xd8JPEG data', 'image/jpeg')
            if url.endswith('/stream'):
                return Response(b'--frame\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8'+b'x'*256,
                                'multipart/x-mixed-replace; boundary=frame')
            raise AssertionError(url)

        with patch.object(camera, 'urlopen', side_effect=request):
            camera.verify_video(self.value)
        self.assertEqual(len(visited), 4)
        self.assertIn('http://127.0.0.1:4480/m300-camera/stream', visited)
        with patch.object(camera, 'urlopen', return_value=Response(
                b'{"result":{"source":{"online":false}}}', 'application/json')), \
                patch.object(camera.time, 'monotonic', side_effect=[0, 0, 20]), \
                patch.object(camera.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'offline'):
                camera.verify_video(self.value)

    def test_existing_webcam_uid_and_user_rotation_are_preserved(self):
        old = dict(name=camera.NAME, source='database', stream_url=camera.ROUTE+'stream',
                   uid='stable-camera-id', rotation=180)
        self.assertEqual(camera.existing_webcam([old]), old)
        payload = camera.webcam_payload(self.value, old)
        self.assertEqual(payload['uid'], old['uid'])
        self.assertNotIn('rotation', payload)  # Moonraker retains omitted user fields.
        self.assertEqual(payload['aspect_ratio'], '4:3')
        with self.assertRaises(ValueError):
            camera.existing_webcam([dict(old, source='config')])
        with self.assertRaises(ValueError):
            camera.existing_webcam([dict(old, stream_url='/webcam/?action=stream')])

    def fixture(self, *, previous=False, fail_check=False, fail_api=False):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.config.write_text(self.text)
        self.value['enabled'] = True
        self.commands, self.api_calls, self.webcams = [], [], []
        if previous:
            self.unit.write_text(camera.OWNER+'\nprevious unit --port=8088"\n')
        self.previous_unit = self.unit.read_text() if previous else None
        failure_seen = False

        def execute(*args):
            nonlocal failure_seen
            self.commands.append(args)
            if args == ('sudo', 'nginx', '-t') and fail_check and not failure_seen:
                failure_seen = True
                raise subprocess.CalledProcessError(1, args)
            if args[:3] == ('sudo', 'rm', '--'):
                Path(args[3]).unlink()
            return ''

        def api(endpoint, payload=None, method=None):
            nonlocal fail_api
            self.api_calls.append((endpoint, payload, method))
            if endpoint == '/server/webcams/list':
                return {'webcams': self.webcams.copy()}
            if method == 'DELETE':
                self.webcams.clear()
                return {}
            if endpoint == '/server/webcams/item':
                old = self.webcams[0] if self.webcams else {}
                entry = dict(old, **payload)
                entry.setdefault('uid', 'generated-id')
                entry['source'] = 'database'
                self.webcams[:] = [entry]
                if fail_api:
                    fail_api = False  # Simulate response lost after server accepted the write.
                    raise URLError('lost response')
                return {'webcam': entry}
            raise AssertionError(endpoint)

        patches = dict(UNIT=self.unit, run=execute, moonraker=api,
                       nginx_site=lambda *a: self.site,
                       privileged_write=lambda path, text: path.write_text(text),
                       choose_device=lambda _: '/dev/v4l/by-id/usb-Test-video-index0',
                       capture_format=lambda *a: 'MJPEG',
                       is_state=lambda _: previous)
        for name, value in patches.items():
            stack.enter_context(patch.object(camera, name, value))
        self.verifier = stack.enter_context(patch.object(camera, 'verify_video'))

    def test_enable_verifies_video_before_registering_and_never_restarts_klipper(self):
        self.fixture()
        result = camera.apply(self.value, self.config, self.text)
        self.assertTrue(result['video_verified'])
        self.assertTrue(camera.configuration(self.config.read_text())['enabled'])
        self.assertIn('/dev/v4l/by-id/usb-Test-video-index0', self.config.read_text())
        self.assertTrue(self.webcams[0]['enabled'])
        self.verifier.assert_called_once()
        self.assertTrue(Path(result['backup']).is_dir())
        self.assertFalse(any('klipper.service' in call or 'moonraker.service' in call for call in self.commands))

    def test_nginx_failure_restores_config_and_removes_new_service(self):
        self.fixture(fail_check=True)
        with self.assertRaises(subprocess.CalledProcessError):
            camera.apply(self.value, self.config, self.text)
        self.assertEqual(self.site.read_text(), SITE)
        self.assertEqual(self.config.read_text(), self.text)
        self.assertFalse(self.unit.exists())
        self.verifier.assert_not_called()
        self.assertEqual(self.webcams, [])

    def test_capture_failure_restores_existing_service_and_state(self):
        self.fixture(previous=True)
        self.verifier.side_effect = ValueError('Camera capture is offline')
        with self.assertRaisesRegex(ValueError, 'offline'):
            camera.apply(self.value, self.config, self.text)
        self.assertEqual(self.unit.read_text(), self.previous_unit)
        self.assertEqual(self.site.read_text(), SITE)
        self.assertIn(('sudo', 'systemctl', 'enable', self.unit.name), self.commands)
        self.assertIn(('sudo', 'systemctl', 'start', self.unit.name), self.commands)
        self.assertEqual(self.webcams, [])

    def test_api_failure_after_server_write_restores_view_and_files(self):
        self.fixture(fail_api=True)
        with self.assertRaises(URLError):
            camera.apply(self.value, self.config, self.text)
        self.assertEqual(self.webcams, [])
        self.assertEqual(self.config.read_text(), self.text)
        self.assertEqual(self.site.read_text(), SITE)
        self.assertFalse(self.unit.exists())

    def test_disable_stops_service_without_camera_nginx_or_dependencies(self):
        self.fixture(previous=True)
        self.value['enabled'] = False
        self.webcams[:] = [dict(name=camera.NAME, uid='id', source='database', enabled=True,
                               stream_url=camera.ROUTE+'stream')]
        result = camera.apply(self.value, self.config, self.text)
        self.assertEqual(result['status'], 'CAMERA_DISABLED')
        self.assertEqual(self.commands, [('sudo', 'systemctl', 'disable', '--now', self.unit.name)])
        self.assertFalse(self.webcams[0]['enabled'])
        self.verifier.assert_not_called()
        self.assertEqual(self.site.read_text(), SITE)

    def test_disable_works_even_if_moonraker_is_down(self):
        self.fixture(previous=True)
        self.value['enabled'] = False
        with patch.object(camera, 'moonraker', side_effect=URLError('offline')), \
                patch('sys.stderr', new_callable=io.StringIO) as out:
            camera.apply(self.value, self.config, self.text)
        self.assertIn('could not be synchronized', out.getvalue())
        self.assertFalse(camera.configuration(self.config.read_text())['enabled'])

    def test_foreign_service_is_never_replaced_or_stopped(self):
        self.fixture()
        self.unit.write_text('unrelated service')
        for enabled in (True, False):
            self.value['enabled'] = enabled
            with self.assertRaisesRegex(ValueError, 'unmanaged'):
                camera.apply(self.value, self.config, self.text)
        self.assertEqual(self.commands, [])
        self.assertEqual(self.unit.read_text(), 'unrelated service')


if __name__ == '__main__':
    unittest.main(verbosity=2)
