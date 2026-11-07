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

    def test_existing_oled_transport_and_generic_renderer_are_unchanged(self):
        runtime = ROOT / 'host/klippy/extras'
        reference = ROOT / 'host/update_template/tests/reference'
        self.assertEqual(digest(runtime / 'm300_oled_render.py'),
                         digest(reference / 'm300_oled_render.py'))

        def classes(folder):
            module = ast.parse((folder / 'm300_oled_transport.py').read_text())
            result = {}
            for cls in (node for node in module.body if isinstance(node, ast.ClassDef)):
                if cls.name == 'FastOledStream':
                    cls.body = [node for node in cls.body
                                if not isinstance(node, ast.FunctionDef)
                                or node.name not in ('__init__', 'step')]
                result[cls.name] = ast.dump(cls)
            return result

        self.assertEqual(classes(runtime), classes(reference))

    def test_oled_spi_lifecycle_and_background_scheduler_are_unchanged(self):
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
                for item in ast.walk(constructor):
                    if isinstance(item, ast.Call):
                        item.keywords = [kw for kw in item.keywords if kw.arg != 'optimize_windows']
                status = next(n for n in node.body if isinstance(n, ast.FunctionDef)
                              and n.name == 'get_status')
                for item in ast.walk(status):
                    if isinstance(item, ast.Dict):
                        fields = [(key, value) for key, value in zip(item.keys, item.values)
                                  if not isinstance(key, ast.Constant)
                                  or key.value not in ('optimize_windows', 'optimized_frames')]
                        item.keys = [key for key, _ in fields]
                        item.values = [value for _, value in fields]
                # Remove only the exact fault-observer additions, then still
                # require equality of transport, scheduling and SPI lifecycle.
                observer = ast.parse("from .m300_error_codes import report\n"
                    "report(self.printer, 'OLED transport: ' + str(exc), source='m300_oled')\n"
                    "if snapshot['fault'] and not (self.mcu_oled_stats or {}).get('fault', 0):\n"
                    "    from .m300_error_codes import report\n"
                    "    report(self.printer, 'OLED DMA fault; MCU reset required', source='m300_oled')\n").body
                for method_name, additions in (('_send_one', observer[:2]), ('_stats', observer[2:])):
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
        self.assertEqual(set(new), set(old) | {'cmd_rle_bench'})
        # _select additionally preserves the interactive OEM fan-menu cursor.
        for name in old.keys()-{'_render','_panel','_select'}:
            self.assertEqual(old[name],new[name],name)

    def test_published_host_and_mcu_sources_exclude_factory_dump_images(self):
        forbidden = {'.bin', '.elf', '.m3b', '.ivb', '.hex'}
        for folder in ('host', 'mcu'):
            for path in (ROOT / folder).rglob('*'):
                if path.is_file():
                    self.assertNotIn(path.suffix.lower(), forbidden, str(path))


if __name__ == '__main__':
    unittest.main()
