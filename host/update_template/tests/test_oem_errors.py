"""Real native dispatcher + shared menu/OLED models; no physical fault injection."""
from contextlib import contextmanager
from types import SimpleNamespace as NS
import unittest

from test_settings_information import session
from payload.m300_error_codes import CODES, KINDS, classify, TIMER, LINK, PLATFORM, SENSOR, SHUTDOWN
from payload.m300_errors import M300Errors
from tests.reference.native_gcode import CommandError
from payload.m300_leveling_oem import width


@contextmanager
def errors_session(abi=1):
    with session() as h:
        h.writes, h.config_callbacks, h.responses = [], [], {}
        h.objects['mcu'] = NS(register_config_callback=h.config_callbacks.append,
            get_constants=lambda:dict(M300_ERROR_ABI=abi),
            lookup_command=lambda fmt:NS(send=lambda args:h.writes.append((fmt, args))),
            register_serial_response=lambda cb,fmt:h.responses.__setitem__(fmt,cb))
        h.errors = M300Errors(h.config)
        h.objects['m300_errors'] = h.errors
        h.errors._build_config();h.errors._ready()
        h.callbacks.clear();h.lines.clear();h.writes.clear()
        def flush():
            while h.callbacks:
                h.callbacks.pop(0)(h.now)
        h.flush_errors = flush
        yield h


class OEMErrorsTests(unittest.TestCase):
    def test_complete_catalogue_has_21_codes_and_readable_oled_text(self):
        self.assertEqual(set(CODES), {2,3,4,10,11,12,13,14,15,30,31,32,33,34,35,40,41,42,75,76,101})
        for record in (*CODES.values(), *KINDS.values()):
            self.assertEqual(len(record['hint']), 2)
            for text in (record['oled'], *record['hint']):
                self.assertLessEqual(width(text), 188, text)

    def test_native_causes_are_not_assigned_fabricated_oem_codes(self):
        for text, expected in (('Timer too close', TIMER),
                ("Lost communication with MCU 'mcu'", LINK),
                ('M300 guard fault platform_connector_PE15', PLATFORM),
                ('MCU ADC out of range', SENSOR)):
            self.assertEqual(classify(text, fatal=True), (0, expected))

    def test_known_oem_reasons_preserve_model_temperature_and_probe_distinctions(self):
        cases = {'Header CRC mismatch':3, 'required firmware is newer than audited M300 1.3.1':40,
            'Wrong model family for classic M300: 11':76, 'No models on SD card':101,
            'Heater extruder not heating at expected rate':10,
            'Unexpected extruder temperature drop':13, 'hotend maximum temperature':11,
            'heater_bed overheat':12, 'bed thermistor error':14, 'extruder thermistor error':15,
            'Check small platform connector':30, 'Check large platform connector':31,
            'main extruder cable':32, 'perforated plate contacts':33,
            'Endstop stepper_x still triggered after retract':34,
            'extruder gear did not rotate smoothly':35,
            'Calibration failed':41, 'PC7 is closed':42,
            'Please use a newer Z-Suite version':75, 'SD card timeout':4, 'SD card read error':2}
        for text, code in cases.items():
            with self.subTest(text=text):
                self.assertEqual(classify(text)[0], code)
                if code in (10,11,12,13,14,15):
                    # Procedure context must not hide the real thermal cause.
                    self.assertEqual(classify('M300 calibration: ' + text,
                                              source='m300_calibration')[0], code)

    def test_input_preconditions_and_unconfirmed_jam_are_not_diagnosed_as_faults(self):
        for text in ('home XYZ before probing', 'heat the clean nozzle to at least 180 C',
                     'Expired Settings view; refresh before choosing', 'filament might be jammed',
                     'Requested temperature is out of range', 'M300 homing cancelled'):
            self.assertIsNone(classify(text))

    def test_native_dispatcher_error_emits_original_and_shared_code(self):
        with errors_session() as h:
            h.gcode.register_command('FAIL_NATIVE_X', lambda cmd: (_ for _ in ()).throw(
                cmd.error('Endstop stepper_x still triggered after retract')))
            with self.assertRaises(CommandError):h.run('FAIL_NATIVE_X')
            h.flush_errors()
            self.assertEqual(h.errors.current['code'], 34)
            self.assertTrue(any(line.startswith('!! Endstop stepper_x') for line in h.lines))
            self.assertTrue(any('prompt_begin ZORTRAX M300 - Error #034' in line for line in h.lines))
            self.assertEqual(h.oled.message[0], 'Error #034')
            self.assertTrue(any(args == [34, 0, 0] for _, args in h.writes))

    def test_all_catalogue_entries_are_safe_to_view_without_error_or_uart(self):
        with errors_session() as h:
            before = len(h.events)
            for code in CODES:
                h.run('ZORTRAX_ERROR_SHOW CODE=%d' % code)
                self.assertEqual(h.oled.message[0], 'Error #%03d' % code)
                sprite = h.ui.notice_sprite(*h.oled.message, h.now)
                self.assertIsNotNone(sprite)
                self.assertEqual(h.ui.last_sprite, 'activity:' + CODES[code]['icon'])
            self.assertTrue(any('Back|ZORTRAX_UI_SHOW PAGE=error_catalog|info' in line for line in h.lines))
            self.assertIsNone(h.errors.current)
            self.assertFalse(h.errors.history)
            self.assertFalse(h.writes)
            self.assertFalse(any(e[0] in ('move', 'heat', 'fan') for e in h.events[before:]))

    def test_error_notice_has_priority_over_native_print_context(self):
        with errors_session() as h:
            h.objects['m300_print_ui'] = NS(render=lambda *a,**kw:b'print',
                present_status=lambda *a:None)
            h.errors.record('Endstop stepper_x still triggered after retract', source='native')
            h.flush_errors();h.oled._render(h.now)
            self.assertEqual(h.oled._render_key[0], 'notice')
            self.assertEqual(h.oled._render_key[1][0], 'Error #034')

    def test_error_menu_and_web_use_same_catalogue_and_commands(self):
        with errors_session() as h:
            _, rows = h.settings.rows('information', h.now)
            self.assertNotIn(('Errors', ('page', 'errors')), rows)
            _, rows = h.settings.rows('help', h.now)
            self.assertIn(('Errors', ('page', 'errors')), rows)
            h.menu.page = 'errors'
            title, rows = h.menu.rows(h.now)
            self.assertEqual(title, 'Errors')
            self.assertEqual(rows[0], ('Back', ('page', 'help')))
            self.assertIn(('Code catalogue', ('page', 'error_catalog')), rows)
            _, rows = h.settings.rows('error_catalog', h.now)
            self.assertEqual(len(rows), 22)
            h.settings.show('error_catalog')
            token = h.settings._view_id()
            h.settings.action(token, 1)
            self.assertEqual(h.oled.message[0], 'Error #002')
            self.assertIsNone(h.errors.current)
            h.run('ZORTRAX_UI_SHOW PAGE=error_catalog')
            self.assertEqual(h.menu.page, 'error_catalog')
            self.assertIsNone(h.oled.message)

    def test_notice_ack_requires_current_identity_and_never_resumes_or_arms(self):
        with errors_session() as h:
            h.errors.record('Header CRC mismatch', source='models')
            first = h.errors.current['id']
            h.errors.record('Wrong model family for classic M300', source='models')
            with self.assertRaisesRegex(CommandError, 'Expired error notice'):
                h.errors.acknowledge(first)
            token = h.errors.current['id']
            h.events.clear();h.writes.clear()
            h.errors.acknowledge(token)
            self.assertIsNone(h.errors.current)
            self.assertEqual(h.writes, [('m300_error_set code=%hu kind=%c fatal=%c', [0, 0, 0])])
            self.assertFalse(any(e[0] in ('move', 'heat', 'fan') for e in h.events))

    def test_fatal_error_cannot_be_acknowledged_or_replaced_by_command_errors(self):
        with errors_session() as h:
            record = h.errors.record('Timer too close', source='klipper', fatal=True)
            h.errors.record('Header CRC mismatch', source='models')
            with self.assertRaisesRegex(CommandError, 'Safety latch remains active'):
                h.errors.acknowledge(record['id'])
            self.assertEqual(h.errors.current, record)

    def test_analyze_shutdown_keeps_actual_cause_and_only_sends_metadata(self):
        with errors_session() as h:
            h.shutdown = True
            h.errors._shutdown('MCU shutdown', {'reason':'Stepper too far in past'})
            h.flush_errors()
            record = h.errors.current
            self.assertEqual(record['code'], 0)
            self.assertEqual(record['kind'], 3)
            self.assertEqual(record['reason'], 'Stepper too far in past')
            self.assertTrue(record['fatal'])
            self.assertTrue(all(fmt.startswith(('m300_error_set ', 'm300_error_query')) for fmt, _ in h.writes))
            self.assertIsNone(h.oled.message)

    def test_mcu_specific_fault_upgrades_generic_shutdown_but_not_to_255(self):
        with errors_session() as h:
            h.errors._shutdown('MCU shutdown', {'reason':'M300 local guard latched'})
            h.errors._mcu_response(dict(code=11, kind=7, fatal=1, source=2, native_id=23, revision=1))
            h.flush_errors()
            self.assertEqual(h.errors.current['code'], 11)
            h.errors.record('M300 guard fault 255 (klipper_shutdown)', source='mcu', fatal=True)
            self.assertEqual(h.errors.current['code'], 11)

    def test_mcu_generic_shutdown_does_not_hide_verify_heater_cause(self):
        with errors_session() as h:
            h.errors._shutdown('Heater extruder not heating at expected rate', {})
            h.errors._mcu_response(dict(code=0, kind=1, fatal=1, source=2, native_id=23, revision=1))
            h.flush_errors()
            self.assertEqual(h.errors.current['code'], 10)
            self.assertEqual(h.errors.current['reason'], 'Heater extruder not heating at expected rate')

    def test_matching_mcu_metadata_does_not_replace_original_failure_explanation(self):
        with errors_session() as h:
            h.errors._shutdown('Heater extruder not heating at expected rate', {})
            h.errors._mcu_response(dict(code=10, kind=0, fatal=1, source=1, native_id=23, revision=2))
            h.flush_errors()
            self.assertEqual(h.errors.current['reason'], 'Heater extruder not heating at expected rate')
            self.assertEqual(h.errors.mcu_state['native_id'], 23)

    def test_file_validation_source_cannot_be_confused_with_a_filename(self):
        for text in ('Cannot open Timer too close.gcode', 'CRC mismatch in hotend overheat.zcode'):
            self.assertEqual(classify(text, source='m300_models'), (3, 0))

    def test_original_fault_owner_cannot_replace_shared_error_prompt(self):
        with errors_session() as h:
            h.errors.record('Calibration failed', source='m300_calibration')
            h.flush_errors()
            h.p._prompt(dict(state='FAULT', owner='m300_calibration', view_id='failed-phase'))
            self.assertEqual(h.lines.count('// action:prompt_begin ZORTRAX M300 - Error #041'), 1)
            self.assertEqual(h.p.last_prompt, 'failed-phase')

    def test_fault_owner_before_queued_publish_opens_the_same_error_only_once(self):
        with errors_session() as h:
            h.errors.record('Probe triggered prior to movement', source='m300_motion')
            h.p._prompt(dict(state='FAULT', owner='m300_motion', view_id='failed-home'))
            h.flush_errors()
            self.assertEqual(h.lines.count('// action:prompt_begin ZORTRAX M300 - Error #042'), 1)
            self.assertEqual(len(h.errors.history), 1)
            self.assertEqual(len(h.writes), 1)

    def test_explicit_refresh_reopens_notice_but_later_owner_updates_do_not(self):
        with errors_session() as h:
            h.errors.record('Probe triggered prior to movement', source='m300_motion')
            h.flush_errors()
            h.gcode.respond_raw('// action:prompt_end')
            h.p._prompt(dict(state='FAULT', owner='m300_motion', view_id='failed-home'))
            self.assertEqual(h.lines.count('// action:prompt_begin ZORTRAX M300 - Error #042'), 1)
            h.run('ZORTRAX_ERROR_SHOW')
            self.assertEqual(h.lines.count('// action:prompt_begin ZORTRAX M300 - Error #042'), 2)

    def test_ack_before_queued_publish_does_not_reopen_a_cleared_error(self):
        with errors_session() as h:
            record = h.errors.record('Probe triggered prior to movement', source='m300_motion')
            h.errors.acknowledge(record['id'])
            h.lines.clear();h.flush_errors()
            self.assertEqual(h.lines, [])
            self.assertIsNone(h.errors.current)

    def test_new_error_identity_is_published_after_previous_notice_was_shown(self):
        with errors_session() as h:
            h.errors.record('Probe triggered prior to movement', source='m300_motion')
            h.flush_errors()
            h.errors.record('Endstop stepper_x still triggered after retract', source='m300_motion')
            h.flush_errors()
            self.assertEqual(h.lines.count('// action:prompt_begin ZORTRAX M300 - Error #042'), 1)
            self.assertEqual(h.lines.count('// action:prompt_begin ZORTRAX M300 - Error #034'), 1)

    def test_duplicate_reports_do_not_flood_uart_or_history(self):
        with errors_session() as h:
            for _ in range(100):
                h.errors.record('Header CRC mismatch', source='models')
                h.errors.get_status(h.now)
            self.assertEqual(len(h.errors.history), 1)
            self.assertEqual(len(h.writes), 1)
            self.assertEqual(len(h.callbacks), 1)

    def test_history_is_bounded_and_disconnect_stops_metadata_writes(self):
        with errors_session() as h:
            for i in range(50):h.errors.record('Header CRC mismatch %d' % i, source='models')
            self.assertEqual(len(h.errors.history), 32)
            h.errors._disconnect();h.writes.clear()
            h.errors.record('SD card timeout', source='m300_sd')
            self.assertFalse(h.writes)
            self.assertEqual(h.errors.current['code'], 4)

    def test_old_mcu_keeps_host_diagnostics_and_reports_upgrade_requirement(self):
        with errors_session(abi=0) as h:
            h.errors.record('Header CRC mismatch', source='models')
            h.flush_errors()
            self.assertTrue(h.errors.get_status(h.now)['mcu_upgrade_required'])
            self.assertFalse(h.writes)
            self.assertEqual(h.oled.message[0], 'Error #003')

    def test_error_state_drives_rgb_until_notice_is_acknowledged(self):
        with errors_session() as h:
            h.errors.record('Header CRC mismatch', source='models')
            self.assertEqual(h.m.status_led_rgb(h.now), (1, 0, 0))
            h.now += 5
            self.assertEqual(h.m.status_led_rgb(h.now), (0, 1, 0))
            h.errors.acknowledge(h.errors.current['id'])
            self.assertEqual(h.m.status_led_rgb(h.now), (0, 1, 0))

    def test_prompt_text_cannot_inject_buttons_and_failure_reason_is_retained(self):
        with errors_session() as h:
            h.errors.record('Header CRC mismatch\n|RUN DANGEROUS', source='models')
            h.flush_errors()
            self.assertIn('RUN DANGEROUS', h.errors.current['reason'])
            self.assertFalse(any('prompt_button' in line for line in h.lines))
            self.assertTrue(any('Cause: Header CRC mismatch /RUN DANGEROUS' in line for line in h.lines))


if __name__ == '__main__':
    unittest.main()
