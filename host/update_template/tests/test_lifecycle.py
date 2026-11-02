"""One-time host-start recovery, separate from hardware fault acknowledgement."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

import test_display
from payload.m300_lifecycle import M300Lifecycle


class NativeRestartRequested(Exception):
    pass


def fixture(fault=0, armed=0, configured=0, inputs=62, enabled=True,
            native=True, fileoutput=False, start_reason='startup', start_args=None):
    args = start_args if start_args is not None else {'start_reason': start_reason}
    state = dict(configured=configured, armed=armed, fault=fault, inputs=inputs)
    query = NS(send=Mock(return_value=state))
    helper = NS(_restart_method='command',
                _check_restart=Mock(side_effect=NativeRestartRequested()))
    mcu = NS(is_fileoutput=lambda: fileoutput,
             get_constants=lambda: {'M300_MODEL': 'M300_CLASSIC', 'M300_ABI': 1},
             check_valid_response=lambda fmt: True,
             register_config_callback=Mock(),
             lookup_query_command=Mock(return_value=query),
             _conn_helper=NS(get_restart_helper=lambda: helper))
    bounded = Mock(side_effect=lambda label, operation: operation())
    board = NS(native_control=native, get_mcu=lambda: mcu,
               startup_transport=NS(_bounded=bounded))
    gcode = NS(request_restart=Mock(), is_printer_ready=False, register_command=Mock())
    original_restart = gcode.request_restart
    reactor = NS(monotonic=lambda: 10., register_timer=Mock(), update_timer=Mock(),
                 NEVER=1.e30)
    events = []
    printer = NS(get_reactor=lambda: reactor, lookup_object=lambda name, *args: gcode,
                 load_object=lambda config, name: board, get_start_args=lambda: args,
                 register_event_handler=lambda name, cb: events.append((name, cb)),
                 config_error=RuntimeError, command_error=RuntimeError)
    config = NS(get_printer=lambda: printer, getboolean=lambda name, default: enabled)
    life = M300Lifecycle(config)
    return NS(life=life, args=args, state=state, query=query, helper=helper,
              mcu=mcu, bounded=bounded, gcode=gcode, original_restart=original_restart,
              board=board, events=events)


class StartupReconnectTests(unittest.TestCase):
    def test_cold_start_reads_once_without_reset(self):
        f = fixture()
        f.life._startup_identify()
        f.query.send.assert_called_once_with()
        f.helper._check_restart.assert_not_called()
        self.assertEqual(f.life.startup_reconnect['decision'], 'NO_OLD_ACTIVE_SESSION')
        self.assertFalse(f.life.connected)

    def test_heartbeat_latch_requests_native_restart_and_records_reason(self):
        f = fixture(fault=1, configured=1)
        with self.assertRaises(NativeRestartRequested):
            f.life._startup_identify()
        f.helper._check_restart.assert_called_once()
        record = f.args['m300_startup_reconnect']
        self.assertEqual(record['trigger'], 'heartbeat_loss')
        self.assertEqual(record['previous_guard']['fault'], 1)
        self.assertFalse(f.life.connected)

    def test_fast_service_restart_invalidates_the_old_armed_session(self):
        f = fixture(configured=1, armed=1)
        with self.assertRaises(NativeRestartRequested):
            f.life._startup_identify()
        self.assertEqual(f.args['m300_startup_reconnect']['trigger'], 'previous_host_session')

    def test_other_faults_never_request_a_reset(self):
        for fault in (2, 3, 4, 5, 6, 7, 8, 9, 100, 254, 255):
            with self.subTest(fault=fault):
                f = fixture(configured=1, fault=fault)
                f.life._startup_identify()
                f.helper._check_restart.assert_not_called()
                self.assertEqual(f.life.startup_reconnect['decision'],
                                 'HARDWARE_OR_EXPLICIT_SHUTDOWN_REQUIRES_OPERATOR')

    def test_present_platform_connector_fault_blocks_heartbeat_recovery(self):
        f = fixture(configured=1, fault=1, inputs=63)
        f.life._startup_identify()
        f.helper._check_restart.assert_not_called()

    def test_explicitly_disabled_policy_does_not_query_or_reset(self):
        f = fixture(configured=1, fault=1, enabled=False)
        f.life._startup_identify()
        f.mcu.lookup_query_command.assert_not_called()
        f.helper._check_restart.assert_not_called()

    def test_lab_board_retains_explicit_recovery(self):
        f = fixture(configured=1, fault=1, native=False)
        f.life._startup_identify()
        f.mcu.lookup_query_command.assert_not_called()

    def test_fileoutput_does_not_invent_a_uart_recovery(self):
        f = fixture(configured=1, fault=1, fileoutput=True)
        f.life._startup_identify()
        f.mcu.lookup_query_command.assert_not_called()
        self.assertEqual(f.life.startup_reconnect['decision'], 'FILEOUTPUT_NO_UART')

    def test_restart_from_an_error_does_not_become_firmware_restart(self):
        f = fixture(configured=1, fault=1, start_reason='restart')
        f.life._startup_identify()
        f.mcu.lookup_query_command.assert_not_called()
        f.gcode.request_restart('restart')
        f.original_restart.assert_called_once_with('restart')

    def test_explicit_firmware_restart_does_not_schedule_an_extra_reset(self):
        f = fixture(configured=1, fault=1, start_reason='firmware_restart')
        f.life._startup_identify()
        f.mcu.lookup_query_command.assert_not_called()
        f.helper._check_restart.assert_not_called()

    def test_consumed_attempt_cannot_loop_in_the_same_host_process(self):
        f = fixture(configured=1, fault=1)
        with self.assertRaises(NativeRestartRequested):
            f.life._startup_identify()
        second = fixture(configured=1, fault=1, start_args=f.args)
        second.life._startup_identify()
        second.helper._check_restart.assert_not_called()
        second.query.send.assert_not_called()
        self.assertEqual(second.life.startup_reconnect['decision'], 'ATTEMPT_ALREADY_USED')

    def test_query_failure_is_reported_without_a_reset(self):
        f = fixture()
        f.query.send.side_effect = RuntimeError('response timeout')
        with self.assertRaisesRegex(RuntimeError, 'response timeout'):
            f.life._startup_identify()
        f.helper._check_restart.assert_not_called()
        self.assertEqual(f.life.startup_reconnect['decision'], 'QUERY_FAILED')

    def test_wrong_mcu_or_missing_protocol_is_not_reset(self):
        for supported in (False, True):
            f = fixture(configured=1, fault=1)
            f.mcu.get_constants = lambda: {'M300_MODEL': 'OTHER', 'M300_ABI': 1}
            if supported:
                f.mcu.get_constants = lambda: {'M300_MODEL': 'M300_CLASSIC', 'M300_ABI': 1}
                f.mcu.check_valid_response = lambda fmt: False
            f.life._startup_identify()
            f.query.send.assert_not_called()
            f.helper._check_restart.assert_not_called()

    def test_uart_requires_the_native_command_reset_method(self):
        f = fixture(configured=1, fault=1)
        f.helper._restart_method = 'arduino'
        with self.assertRaisesRegex(RuntimeError, 'restart_method: command'):
            f.life._startup_identify()
        f.helper._check_restart.assert_not_called()

    def test_malformed_or_inconsistent_guard_is_not_reset(self):
        for changes in ({'fault': True}, {'armed': 2}, {'inputs': -1},
                        {'configured': None}, {'armed': 1, 'fault': 1}):
            with self.subTest(changes=changes):
                f = fixture(configured=1, fault=1)
                f.state.update(changes)
                with self.assertRaisesRegex(RuntimeError, 'invalid startup guard'):
                    f.life._startup_identify()
                f.helper._check_restart.assert_not_called()

    def test_successful_fresh_ready_reports_the_prior_reason(self):
        f = fixture(configured=1, fault=1)
        with self.assertRaises(NativeRestartRequested):
            f.life._startup_identify()
        f.args['start_reason'] = 'firmware_restart'
        fresh = fixture(start_args=f.args)
        fresh.life._startup_identify()
        fresh.life.claimed = True
        fresh.life._ready()
        status = fresh.life.get_status(10.)
        self.assertEqual(status['startup_reconnect']['decision'], 'RECOVERED')
        self.assertEqual(status['startup_reconnect']['previous_guard']['fault'], 1)
        self.assertFalse(status['automatic_action_resume'])
        self.assertFalse(status['automatic_hardware_fault_clear'])
        fresh.helper._check_restart.assert_not_called()

    def test_ready_restart_keeps_the_existing_native_reset_mapping(self):
        f = fixture()
        f.gcode.is_printer_ready = True
        f.gcode.request_restart('restart')
        f.original_restart.assert_called_once_with('firmware_restart')


if __name__ == '__main__':
    unittest.main()
