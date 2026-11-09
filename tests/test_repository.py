"""Packaging boundaries and compatibility contracts for the public repository."""
import hashlib
import ast
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ci'))
from project import META, KIT, digest, fresh_directory, stage_host_update, upstream_archive


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepositoryContracts(unittest.TestCase):
    def test_unowned_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'user-work'
            path.mkdir()
            (path / 'keep').write_text('user file')
            with self.assertRaises(ValueError):
                fresh_directory(path)
            self.assertEqual((path / 'keep').read_text(), 'user file')

    def test_wrong_upstream_archive_is_rejected_without_download(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'upstream.zip'
            path.write_bytes(b'not the pinned upstream source')
            with self.assertRaises(ValueError):
                upstream_archive(path)

    def test_staged_host_payload_matches_canonical_source_and_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            stage = stage_host_update(Path(folder) / 'host')
            installer = load('staged_installer', stage / 'install.py')
            self.assertEqual(set(installer.NAMES), set(META['host_update_files']))
            # The footer helper alone cannot update an older status screen:
            # both sides of its import must be shipped by the real installer.
            self.assertTrue({'m300_klipper_status.py', 'm300_status_footer.py'} <= set(installer.NAMES))
            self.assertTrue({'m300_print_control.py','m300_job_state.py','m300_filament.py',
                             'm300_native_service.py','m300_procedures.py'} <= set(installer.NAMES))
            for name in installer.NAMES:
                self.assertEqual((stage / 'payload' / name).read_bytes(),
                                 (ROOT / 'host/klippy/extras' / name).read_bytes())
            self.assertGreater(installer.verify(), 30)

        # The OLED mirror is intentionally a fixed physical-size display
        # preview: resizing Fluidd's columns must not shrink its height.
        # The intrinsic 256x64 canvas is displayed at 344x86 (exact 4:1).
        # Narrow layouts scroll rather than warp the M300's native pixels.
        patch = (ROOT / 'frontend/fluidd/m300-leveling.patch').read_text()
        start = patch.index('diff --git a/src/components/widgets/thermals/M300OledPreview.vue')
        end = patch.index('diff --git a/src/util/m300-oled-preview.ts', start)
        preview = patch[start:end]
        for required in ('+      class="m300-oled-viewport pb-3"',
                         '+  overflow-x: auto;', '+  width: 344px;',
                         '+  min-width: 344px;', '+  height: 86px;',
                         '+  min-height: 86px;', '+  max-height: 86px;',
                         '+  image-rendering: pixelated;'):
            self.assertIn(required, preview)
        self.assertNotIn('+  width: 50%;', preview)
        self.assertNotIn('+  height: auto;', preview)

    def test_m300_container_round_trip_uses_application_offset(self):
        tool = load('container_roundtrip', KIT / 'tools/test01_m3b.py')
        image = struct.pack('<II', 0x20005000, 0x08008009) + bytes(56)
        packed = tool.pack(image)
        info = tool.inspect(packed)
        self.assertEqual(info['application_base'], '0x8008000')
        self.assertEqual(info['payload_sha256'], hashlib.sha256(image).hexdigest())
        self.assertFalse(info['bootloader_modified'])

    def test_changed_container_payload_is_rejected(self):
        tool = load('container_corrupt', KIT / 'tools/test01_m3b.py')
        image = struct.pack('<II', 0x20005000, 0x08008009) + bytes(56)
        corrupt = bytearray(tool.pack(image))
        corrupt[-1] ^= 1
        with self.assertRaises(ValueError):
            tool.inspect(corrupt)

    def test_inventure_offset_is_not_a_valid_small_m300_image(self):
        tool = load('container_wrong_mcu', KIT / 'tools/test01_m3b.py')
        with self.assertRaises(ValueError):
            tool.pack(struct.pack('<II', 0x20020000, 0x08010009) + bytes(56))

    def test_unmodified_oled_transport_parts_and_generic_renderer_match_reference(self):
        runtime = ROOT / 'host/klippy/extras'
        reference = ROOT / 'host/update_template/tests/reference'
        self.assertEqual(digest(runtime / 'm300_oled_render.py'),
                         digest(reference / 'm300_oled_render.py'))

        def classes(folder):
            module = ast.parse((folder / 'm300_oled_transport.py').read_text())
            result = {}
            for cls in (node for node in module.body if isinstance(node, ast.ClassDef)):
                if folder == runtime and cls.name == 'OledStream':
                    diagnostic = ast.parse('self.timeout_context = None').body[0]
                    for method in (n for n in cls.body if isinstance(n, ast.FunctionDef)
                                   and n.name in ('__init__', '_begin')):
                        matching = [n for n in method.body
                                    if ast.dump(n) == ast.dump(diagnostic)]
                        self.assertEqual(len(matching), 1)
                        method.body.remove(matching[0])
                if cls.name == 'FastOledStream':
                    # Window planning/diagnostics and cumulative ACK handling
                    # have dedicated behavior tests; the rest stays identical.
                    cls.body = [node for node in cls.body
                                if not isinstance(node, ast.FunctionDef)
                                or node.name not in ('__init__', 'step', 'ack')]
                result[cls.name] = ast.dump(cls)
            return result

        self.assertEqual(classes(runtime), classes(reference))

    def test_oled_spi_and_background_scheduler_are_unchanged(self):
        def methods(path, allow_benchmark=False):
            tree=ast.parse(path.read_text())
            node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='M300OLED')
            if allow_benchmark:
                constructor = next(n for n in node.body if isinstance(n, ast.FunctionDef)
                                   and n.name == '__init__')
                registration = ast.parse("self.gcode.register_command("
                                         "'ZORTRAX_OLED_RLE_BENCH', self.cmd_rle_bench)").body[0]
                matching = [n for n in constructor.body if ast.dump(n) == ast.dump(registration)]
                self.assertEqual(len(matching), 1)
                constructor.body.remove(matching[0])
                for source in ('self.mcu_oled_stats_time = None',
                               'self.ack_recoveries = 0',
                               'self.ack_recovery_active = False',
                               'self.ack_recovery_after = 0.'):
                    addition = ast.parse(source).body[0]
                    matching = [n for n in constructor.body if ast.dump(n) == ast.dump(addition)]
                    self.assertEqual(len(matching), 1)
                    constructor.body.remove(matching[0])
                # The OLED preview is a passive observer. Remove only
                # this exact constructor assignment before comparing
                # baseline OLED scheduling and SPI ownership.
                mirror_constructor = ast.parse(
                    'self._oled_preview = M300OLEDPreview()').body[0]
                matching = [n for n in constructor.body
                            if ast.dump(n) == ast.dump(mirror_constructor)]
                self.assertEqual(len(matching), 1)
                constructor.body.remove(matching[0])
                diagnostic = ast.parse('self.last_transport_failure = None').body[0]
                matching = [n for n in constructor.body if ast.dump(n) == ast.dump(diagnostic)]
                self.assertEqual(len(matching), 1)
                constructor.body.remove(matching[0])
                for item in ast.walk(constructor):
                    if isinstance(item, ast.Call):
                        item.keywords = [kw for kw in item.keywords if kw.arg != 'optimize_windows']
                status = next(n for n in node.body if isinstance(n, ast.FunctionDef)
                              and n.name == 'get_status')
                for item in ast.walk(status):
                    if isinstance(item, ast.Dict):
                        fields = [(key, value) for key, value in zip(item.keys, item.values)
                                  if not isinstance(key, ast.Constant)
                                  or key.value not in ('optimize_windows', 'optimized_frames',
                                                      'last_transport_failure','recovered_acks',
                                                      'ack_recoveries','ack_recovery_active',
                                                      'oled_preview')]
                        item.keys = [key for key, _ in fields]
                        item.values = [value for _, value in fields]
                        for key, value in fields:
                            if isinstance(key, ast.Constant) and key.value == 'host_revision':
                                self.assertEqual(value.value, '0.13.16.32-OLED-ACK-RECOVERY')
                                value.value = '0.13.9-OLED-R9-LIFECYCLE'
                # The status mirror may observe only the latest rendered
                # host frame (never a new render, MCU read or transport op).
                # Strip the two exact pure observer assignments and compare
                # every other field of get_status with the pinned baseline.
                status_mirror = ast.parse(
                    "mirror = getattr(self, '_oled_preview', None)\n"
                    "oled_preview = (mirror.get_status(\n"
                    " now, self.connected and self.stream.ready and self.stream.enabled,\n"
                    " getattr(self, '_render_wire', None))\n"
                    " if mirror is not None else None)\n").body
                for addition in status_mirror:
                    matching = [n for n in status.body if ast.dump(n) == ast.dump(addition)]
                    self.assertEqual(len(matching), 1)
                    status.body.remove(matching[0])
                # Remove only the exact fault-observer additions, then still
                # require equality of transport, scheduling and SPI lifecycle.
                observer = ast.parse("from .m300_error_codes import report\n"
                    "report(self.printer, 'OLED transport: ' + str(exc), source='m300_oled')\n"
                    "if snapshot['fault'] and not (self.mcu_oled_stats or {}).get('fault', 0):\n"
                    "    from .m300_error_codes import report\n"
                    "    report(self.printer, 'OLED DMA fault; MCU reset required', source='m300_oled')\n").body
                diagnostic = ast.parse("lifecycle = self.printer.lookup_object('m300_lifecycle', None)\n"
                    "self.last_transport_failure = {\n"
                    " 'host': self.stream.timeout_context,\n"
                    " 'mcu_oled': getattr(self, 'mcu_oled_stats', None),\n"
                    " 'lease': dict(lifecycle.state) if lifecycle is not None else None,\n"
                    " 'generation': self.generation, 'page': self.page,\n"
                    " 'display_mode': getattr(self.stream, 'display_mode', None)}\n"
                    "logging.error('M300_OLED_TIMEOUT %s',\n"
                    " json.dumps(self.last_transport_failure, sort_keys=True))\n").body
                recovery = ast.parse("if self.fast and self._recover_lost_ack(now):\n"
                                     "    return\n"
                                     "self.ack_recovery_active = False\n").body
                received = ast.parse("received = params.get('#receive_time')\n"
                    "self.mcu_oled_stats_time = (received if isinstance(received, (int, float))\n"
                    " and math.isfinite(received)\n"
                    " and 0. <= self.reactor.monotonic()-received <= 4. else None)\n").body
                completed = ast.parse("if getattr(self,'ack_recovery_active',False) and self.stream.ready and self.stream.enabled:\n"
                    "    self.ack_recovery_active = False\n"
                    "    logging.info('M300 OLED ACK recovery completed: count=%d',self.ack_recoveries)\n").body
                ready = ast.parse("self.mcu_oled_stats_time = None\n"
                                  "self.ack_recovery_active = False\n").body
                stop_mirror = ast.parse(
                    "mirror = getattr(self, '_oled_preview', None)\n"
                    "if mirror is not None:\n"
                    "    mirror.reset()\n").body
                for method_name, additions in (('_send_one', observer[:2]+diagnostic+recovery),
                                               ('_stats', observer[2:]+received+ready[-1:]),
                                               ('_tick',completed),('_ready',ready),
                                               ('_stop',ready[-1:]+stop_mirror)):
                    method = next(n for n in node.body if isinstance(n, ast.FunctionDef)
                                  and n.name == method_name)
                    expected = {ast.dump(n): 0 for n in additions}
                    class StripObserver(ast.NodeTransformer):
                        def visit(self, item):
                            key = ast.dump(item)
                            if key in expected:
                                expected[key] += 1
                                return None
                            return super().visit(item)
                    StripObserver().visit(method)
                    self.assertEqual(set(expected.values()), {1})
            return {n.name:ast.dump(n,include_attributes=False) for n in node.body
                    if isinstance(n,ast.FunctionDef)}
        old=methods(ROOT/'host/update_template/tests/reference/m300_oled.py')
        new=methods(ROOT/'host/klippy/extras/m300_oled.py', allow_benchmark=True)
        self.assertEqual(set(new), set(old) | {'cmd_rle_bench','_healthy_display_link',
                                             '_recover_lost_ack'})
        # _select additionally preserves the interactive OEM fan-menu cursor.
        # _reinitialize deliberately fixes cancelled-ACK/native-queue ordering;
        # test_oled_reclaim reproduces the old failure and checks the boundary.
        for name in old.keys()-{'_render','_panel','_select','_reinitialize'}:
            self.assertEqual(old[name],new[name],name)

    def test_published_host_and_mcu_sources_exclude_factory_dump_images(self):
        forbidden = {'.bin', '.elf', '.m3b', '.ivb', '.hex'}
        for folder in ('host', 'mcu'):
            for path in (ROOT / folder).rglob('*'):
                if path.is_file():
                    self.assertNotIn(path.suffix.lower(), forbidden, str(path))


if __name__ == '__main__':
    unittest.main()
