# Marcin Kowalik <mkowalik@agh.edu.pl>
"""RC17 plate selection through the native LOAD command and original AUTO macro."""
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from test_print_control import Harness
from payload.m300_nvm import HostNVM, M300NVM


def connect_preference(h, path, machine='m300'):
    store = HostNVM(str(path), machine, 'stock')
    nvm = NS(store=store, printer=h.printer, mesh_profile=store.load_mesh_profile(),
             mesh_profile_error=None, executor=NS(submit=lambda fn, *args: fn(*args)),
             get_setting=lambda name, default=None: default)
    nvm.remember_mesh_profile = lambda name: M300NVM.remember_mesh_profile(nvm, name)
    h.objects['m300_nvm'] = nvm
    h.objects['bed_mesh'].pmgr.get_profiles = lambda: {'m300_pads': {}, 'Blue-2': {}}
    return nvm


class MeshSelectionTests(unittest.TestCase):
    def harness(self):
        h = Harness()
        self.addCleanup(h.close)
        return h

    def test_native_load_and_restart_choose_same_named_plate_even_after_clear(self):
        h = self.harness()
        path = Path(h.temp.name) / 'settings.json'
        connect_preference(h, path)
        h.stop_worker()
        h.run('BED_MESH_PROFILE LOAD=Blue-2')
        self.assertEqual(h.c.active_mesh_profile, 'Blue-2')
        self.assertEqual(h.c.selected_mesh_profile, 'Blue-2')
        self.assertFalse(path.exists())  # Earlier host settings formats stay readable.
        fresh = self.harness()
        connect_preference(fresh, path)
        self.assertIsNone(fresh.c.active_mesh_profile)
        fresh.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        fresh.stop_worker()
        fresh.control_until('IDLE')
        self.assertEqual(fresh.c.get_status(fresh.now)['active_mesh_profile'], 'Blue-2')
        self.assertIn(('mesh', 'Blue-2'), fresh.events)
        self.assertIsNone(HostNVM(str(path), 'different-machine', 'stock').load_mesh_profile())

    def test_unknown_or_missing_selection_is_rejected_before_start(self):
        h = self.harness()
        nvm = connect_preference(h, Path(h.temp.name) / 'settings.json')
        nvm.mesh_profile = 'Removed'
        with self.assertRaisesRegex(h.printer.command_error, 'Removed is unavailable'):
            h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60')
        self.assertEqual(h.events, [])
        h.file_command('ZORTRAX_PRINT_START EXTRUDER_TEMP=240 BED_TEMP=60 MESH=NONE')
        h.stop_worker()
        h.control_until('IDLE')
        self.assertIsNone(h.c.active_mesh_profile)
        self.assertEqual(nvm.mesh_profile, 'Removed')

    def test_auto_migrates_unique_or_active_named_profile(self):
        h = self.harness()
        bed = h.objects['bed_mesh']
        bed.pmgr.get_profiles = lambda: {'Blue': {}, 'Steel': {}}
        with self.assertRaisesRegex(h.printer.command_error, 'select a saved bed mesh'):
            h.c._resolve_start_mesh('AUTO')
        h.load_mesh('Steel')
        self.assertEqual(h.c._resolve_start_mesh('AUTO'), 'Steel')
        h.set_mesh(None)
        bed.pmgr.get_profiles = lambda: {'Blue': {}}
        self.assertEqual(h.c._resolve_start_mesh('AUTO'), 'Blue')

    def test_console_cannot_replace_mesh_during_native_file(self):
        h = self.harness()
        with self.assertRaisesRegex(h.printer.command_error, 'active mesh'):
            h.run('BED_MESH_PROFILE LOAD=m300_pads')
        self.assertIsNone(h.c.active_mesh_profile)
