"""Native menu contracts, including negative controls from shipped R15.5."""
from contextlib import nullcontext
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

import test_display  # initializes the unchanged renderer reference
from payload.m300_menu import M300Menu
from payload.m300_ui_m11_state import require_rows
from tests.reference import previous_m11_state, r155_menu


def fixture(native=True):
    m = M300Menu.__new__(M300Menu)
    m.generation, m.page, m.reason, m._busy = 7, 'maintenance', '', False
    m._confirm = None
    m._cal_view = m._material_view = (None, None)
    m._temperature = {'HOTEND': 200., 'BED': 60.}
    m._motion_jog_token = None
    m._labels = {}
    m.cycle = None
    m.job = NS(board=NS(native_control=native))
    m.scheduled, m.commands = [], []
    m.reactor = NS(register_callback=m.scheduled.append)
    m.gcode = NS(get_mutex=nullcontext, run_script_from_command=m.commands.append)
    m.maintenance = NS(activity=Mock(), start=Mock(), stop=Mock(),
                       get_status=lambda now: {'sleep': False})
    motion = NS(home=Mock(), arm_xy_clearance=Mock(),
                get_status=lambda now: {'state': 'IDLE', 'homed_axes': 'xy'})
    objects = {'m300_motion': motion}
    m.printer = NS(is_shutdown=lambda: False, command_error=RuntimeError,
                   lookup_object=lambda name, default=None: objects.get(name, default))
    m.t = lambda s: s
    m._error = lambda s: RuntimeError(s)
    return m, objects


class NativeMenuTests(unittest.TestCase):
    def test_oem_procedure_temperatures_are_independent_of_manual_heating(self):
        m,objects=fixture();m._temperature['HOTEND']=200.
        filament=NS(procedure_temperature=240.,start=Mock())
        calibration=NS(start=Mock())
        objects.update(m300_filament=filament,m300_calibration=calibration)
        m._cal_refresh=Mock()
        for operation in ('LOAD','UNLOAD'):
            m.select(('material',operation),100.)
            filament.start.assert_called_with(operation,temperature=240.)
        m.select(('cal_start',),100.)
        calibration.start.assert_called_once_with(None)
        self.assertEqual(m._temperature['HOTEND'],200.)
        self.assertEqual(m.commands,[])

    def test_old_menu_negative_control_has_no_native_command_path(self):
        self.assertFalse(hasattr(r155_menu.M300Menu, '_native_script'))
        self.assertTrue(hasattr(M300Menu, '_native_script'))

    def test_all_native_maintenance_actions_are_supported_by_presentation(self):
        m, _ = fixture()
        m.page='klipper'
        rows = m.rows(100.)[1]
        self.assertEqual(rows[0][0], 'Back')
        self.assertTrue(require_rows(rows))
        kinds = [a[0] for _, a in rows if a]
        for kind in ('motion_home_x', 'motion_home_y', 'motion_home_xy',
                     'motion_home_z', 'native_gcode'):
            self.assertIn(kind, kinds)
        self.assertNotIn('motion_home', kinds)

    def test_homing_names_and_order_are_consistent_in_both_menus(self):
        m, _ = fixture()
        for page in ('klipper', 'maintenance'):
            m.page=page
            labels=[name for name,_ in m.rows(100.)[1] if name.startswith('Home ')]
            self.assertEqual(labels,['Home X','Home Y','Home Z','Home XY','Home XYZ'])
            self.assertFalse(any('(180C)' in name or name=='Homing ALL'
                                 for name,_ in m.rows(100.)[1]))

    def test_maintenance_single_axes_use_the_same_macros_as_fluidd(self):
        m, _ = fixture()
        m.page = 'maintenance'
        rows=dict(m.rows(100.)[1])
        for label,command in (('Home X','ZORTRAX_HOME_X'),
                              ('Home Y','ZORTRAX_HOME_Y'),
                              ('Home Z','ZORTRAX_HOME_Z'),
                              ('Home XY','ZORTRAX_HOME_XY'),
                              ('Home XYZ','ZORTRAX_HOME_ALL')):
            with self.subTest(label=label):
                self.assertEqual(rows[label],('native_gcode',command))
                self.assertEqual(m._script_procedure(command)[1],
                                 {'Home X':'HOME_X','Home Y':'HOME_Y',
                                  'Home Z':'HOME_Z','Home XY':'HOME_XY',
                                  'Home XYZ':'HOME_ALL'}[label])

    def test_old_presentation_negative_control_rejects_split_homing_rows(self):
        m, _ = fixture()
        with self.assertRaises(ValueError):
            previous_m11_state.require_rows(m.rows(100.)[1])

    def test_split_homing_uses_existing_motion_owner_without_extra_move(self):
        for suffix, axes in [('x', 'x'), ('y', 'y'), ('xy', 'xy'), ('z', 'z')]:
            m, objects = fixture()
            m.select(('motion_home_' + suffix,), 100.)
            objects['m300_motion'].home.assert_called_once_with(axes=axes)
            self.assertEqual(m.commands, [])

    def test_heat_routes_to_native_heater_command_not_maintenance_lock(self):
        for kind, heater, target in [('HOTEND', 'extruder', 200),
                                     ('BED', 'heater_bed', 60)]:
            m, _ = fixture()
            m.select(('service', kind), 100.)
            self.assertEqual(m.commands, [])
            m.scheduled.pop()(100.)
            self.assertEqual(m.commands, [
                'SET_HEATER_TEMPERATURE HEATER=%s TARGET=%g' % (heater, target)])
            m.maintenance.start.assert_not_called()

    def test_part_fan_routes_to_native_m106(self):
        m, _ = fixture()
        m.select(('fan_set', 50.), 100.)
        m.scheduled.pop()(100.)
        self.assertEqual(m.commands, ['M106 S128'])

    def test_navigation_expires_queued_native_action(self):
        m, _ = fixture()
        m._native_script('M106 S255')
        m.generation += 1
        m.scheduled.pop()(100.)
        self.assertEqual(m.commands, [])

    def test_shutdown_expires_queued_native_action(self):
        m, _ = fixture()
        m._native_script('M106 S255')
        m.printer.is_shutdown = lambda: True
        m.scheduled.pop()(100.)
        self.assertEqual(m.commands, [])

    def test_rejected_native_jog_restores_parser_mode_without_move(self):
        m, _ = fixture()
        def dispatch(script):
            m.commands.append(script)
            if script.startswith('G91'):
                raise RuntimeError('Must home axis first')
        m.gcode.run_script_from_command = dispatch
        m._native_script('SAVE_GCODE_STATE NAME=M300_UI_NATIVE\nG91\nG1 X1 F3000')
        m.scheduled.pop()(100.)
        self.assertEqual(m.commands[-1],
                         'RESTORE_GCODE_STATE NAME=M300_UI_NATIVE MOVE=0')
        self.assertIn('Must home', m.reason)

    def test_native_movement_rows_use_standard_gcode(self):
        m, _ = fixture()
        for axis in 'xyz':
            m.page = 'native_move_' + axis
            rows = m.rows(100.)[1]
            self.assertEqual(rows[0][0], 'Back')
            scripts = [a[1] for _, a in rows if a and a[0] == 'native_gcode']
            self.assertEqual(len(scripts), 6)
            self.assertTrue(all('G91\nG1 ' + axis.upper() in s for s in scripts))
            self.assertTrue(all('FORCE_MOVE' not in s for s in scripts))

    def test_material_confirm_cannot_use_an_unpresented_new_phase(self):
        m, objects = fixture()
        facade = NS(act=Mock())
        objects['m300_material_ui'] = facade
        m._material_view = (3, 8)
        m.select(('material_action', 'CONFIRM', 3, 9), 100.)
        facade.act.assert_not_called()
        self.assertIn('material view changed', m.reason)

    def test_legacy_sleep_cannot_replace_native_controls(self):
        m, _ = fixture()
        m.page='klipper'
        m.maintenance.get_status = lambda now: {'sleep': True}
        title, rows = m.rows(100.)
        self.assertEqual(title, 'Klipper')
        self.assertTrue(any(a and a[0] == 'native_gcode' for _, a in rows))

    def test_native_mode_rejects_cached_lab_fan_service_action(self):
        m, _ = fixture()
        m.select(('service', 'FAN_HOTEND'), 100.)
        m.maintenance.start.assert_not_called()
        self.assertIn('native controls', m.reason)


if __name__ == '__main__':
    unittest.main()
