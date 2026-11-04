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

    def test_oled_renderer_packet_format_and_ack_lifecycle_are_unchanged(self):
        reference = ROOT / 'host/update_template/tests/reference'
        current = ROOT / 'host/klippy/extras'
        self.assertEqual(digest(current / 'm300_oled_render.py'),
                         digest(reference / 'm300_oled_render.py'))

        def transport(path):
            tree = ast.parse((path / 'm300_oled_transport.py').read_text())
            return {node.name: node for node in tree.body
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef))}

        old, new = transport(reference), transport(current)
        for name in ('OledStream', 'fast_blocks', 'fast_frame_operations', 'fast_init_operations'):
            self.assertEqual(ast.dump(old[name]), ast.dump(new[name]), name)
        for owner in (old, new):
            owner['FastOledStream'].body = [node for node in owner['FastOledStream'].body
                                          if getattr(node, 'name', None) != 'step']
        self.assertEqual(ast.dump(old['FastOledStream']), ast.dump(new['FastOledStream']))

    def test_oled_spi_lifecycle_and_background_scheduler_are_unchanged(self):
        def methods(path):
            tree=ast.parse(path.read_text())
            node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='M300OLED')
            return {n.name:ast.dump(n,include_attributes=False) for n in node.body
                    if isinstance(n,ast.FunctionDef)}
        old=methods(ROOT/'host/update_template/tests/reference/m300_oled.py')
        new=methods(ROOT/'host/klippy/extras/m300_oled.py')
        self.assertEqual(set(old),set(new))
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
