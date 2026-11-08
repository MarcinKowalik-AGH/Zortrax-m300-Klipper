"""Native bed service, shared rendering, settings and safe cancellation."""
from types import SimpleNamespace as NS
import unittest

import test_native_oem_services as oem
import test_settings_information as settings
from payload.m300_activity_graphics import procedure_symbol, menu_symbol
from payload.m300_oem_procedure_ui import describe
import m300_profile


class PlatformHeatTests(unittest.TestCase):
    def setUp(self):self.h=oem.Harness()

    def test_macro_heats_only_the_platform_without_requiring_homing(self):
        h=self.h;h.hotend.target=210.;h.run('ZORTRAX_HEAT_PLATFORM TEMP=65')
        self.assertEqual((h.hotend.target,h.bed.target),(210.,65.));self.assertEqual(h.homed,'')
        self.assertFalse(any(e[0]=='move' for e in h.events))
        view=h.p.view(h.now);self.assertEqual(view['title'],'Heat the platform')
        self.assertEqual(view['target_bed'],65.);self.assertEqual(view['target_hotend'],210.)

    def test_wait_confirm_is_at_bed_temperature_and_rejects_stale_phase(self):
        h=self.h;h.run('ZORTRAX_HEAT_PLATFORM');h.bed.temperature=80.;h.step()
        self.assertEqual(h.m.state,'HEATING')
        h.bed.temperature=60.;h.until(h.m,'WAIT_CONFIRM');token,phase=h.m.token,h.m.phase_id
        with self.assertRaises(h.printer.command_error):h.m.confirm(token,phase-1)
        h.m.confirm(token,phase)
        self.assertEqual(h.m.state,'COMPLETE');self.assertEqual(h.bed.target,0.)
        h.assert_restored(self)

    def test_cancel_turns_bed_off_and_preserves_unrelated_hotend_target(self):
        h=self.h;h.hotend.target=210.;h.run('ZORTRAX_HEAT_PLATFORM TEMP=70')
        h.m.cancel();h.until(h.m,'CANCELLED')
        self.assertEqual((h.hotend.target,h.bed.target),(210.,0.));h.assert_restored(self)

    def test_invalid_temperatures_never_start_or_change_targets(self):
        h=self.h
        for value in ('nan','-1','0','999'):
            with self.subTest(value=value),self.assertRaises(h.printer.command_error):
                h.run('ZORTRAX_HEAT_PLATFORM TEMP='+value)
        self.assertEqual((h.hotend.target,h.bed.target),(0.,0.));self.assertEqual(h.m.state,'IDLE')

    def test_printing_or_paused_print_blocks_a_standalone_platform_service(self):
        h=self.h
        for state in ('printing','paused'):
            h.print_state=state
            with self.subTest(state=state),self.assertRaises(h.printer.command_error):
                h.run('ZORTRAX_HEAT_PLATFORM')

    def test_bed_animation_matches_heater_and_keeps_original_hotend_screen(self):
        h=self.h;h.run('ZORTRAX_HEAT_PLATFORM');status=h.m.get_status(h.now)
        self.assertEqual(procedure_symbol('m300_maintenance',status).key,'activity:heat_bed')
        self.assertTrue(procedure_symbol('m300_maintenance',status).animated)
        self.assertEqual(describe('m300_maintenance',status)['sprite'],'activity:heat_bed')
        self.assertIn('platform',describe('m300_maintenance',status)['text'])

    def test_full_platform_setting_is_shared_persistent_and_does_not_heat(self):
        with settings.session() as h:
            h.run('ZORTRAX_UI_SETTING NAME=full_platform_preheat VALUE=ENABLED')
            self.assertIs(h.nvm.get_setting('full_platform_preheat'),True)
            self.assertEqual(h.settings.active_rows('setting_full_platform_preheat'),(1,))
            h.settings.nvm.store.load()
            self.assertIs(h.nvm.get_setting('full_platform_preheat'),True)
            self.assertEqual((h.hotend.target,h.bed.target),(0.,0.))

    def test_start_macro_migration_updates_only_the_known_canonical_body(self):
        old=('''[gcode_macro START_PRINT]
gcode:
    {% set hotend = params.EXTRUDER_TEMP|default(0)|float %}
    {% set bed = params.BED_TEMP|default(60)|float %}
    {% set mesh = params.MESH|default('m300_pads') %}
    ZORTRAX_PRINT_START EXTRUDER_TEMP={hotend} BED_TEMP={bed} MESH={mesh}
''')
        new=m300_profile.convert_text(old)
        self.assertIn("default('AUTO')",new);self.assertEqual(m300_profile.convert_text(new),new)
        custom=old+'    M118 My custom action\n'
        self.assertEqual(m300_profile.convert_text(custom),custom)

    def test_platform_heat_preserves_an_active_bed_mesh_without_moving(self):
        h=self.h;mesh=NS(get_mesh=lambda:object())
        h.objects['bed_mesh']=mesh;h.gmove.move_transform=mesh
        h.run('ZORTRAX_HEAT_PLATFORM');h.bed.temperature=60.;h.until(h.m,'WAIT_CONFIRM')
        h.m.confirm(h.m.token,h.m.phase_id)
        self.assertIs(h.gmove.move_transform,mesh)
        self.assertFalse(any(e[0]=='move' for e in h.events));self.assertEqual(h.bed.target,0.)


if __name__=='__main__':unittest.main()
