#!/usr/bin/env python3
"""Exercise the actual pinned native restart helper, without a UART or MCU."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace as NS
import sys
from unittest.mock import Mock


class RestartBoundary(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    sys.path[:0] = [str(args.root / 'klippy'), str(args.package), str(args.package / 'tests')]
    from mcu import MCURestartHelper, MCUConfigHelper, error
    from test_lifecycle import fixture

    rows = []
    for name, values in (
        ('lost_heartbeat', dict(configured=1, fault=1)),
        ('rapid_service_restart', dict(configured=1, armed=1)),
        ('fresh_cold_start', dict()),
        ('explicit_m112', dict(configured=1, fault=255)),
        ('explicit_disarm', dict(configured=1, fault=5)),
        ('adc_fault', dict(configured=1, fault=4)),
        ('platform_pin_after_link_loss', dict(configured=1, fault=1, inputs=63)),
    ):
        f = fixture(**values)
        exits = []
        f.life.printer.request_exit = exits.append
        native = MCURestartHelper.__new__(MCURestartHelper)
        native._printer, native._name, native._restart_method = f.life.printer, 'mcu', 'command'
        def pause(now):
            assert exits == ['firmware_restart']
            raise RestartBoundary()
        native._reactor = NS(monotonic=lambda: 10., pause=pause)
        f.mcu._conn_helper.get_restart_helper = lambda: native
        requested = False
        try:
            f.life._startup_identify()
        except RestartBoundary:
            requested = True
        expected = name in ('lost_heartbeat', 'rapid_service_restart')
        assert requested == expected and exits == (['firmware_restart'] if expected else []), name
        if requested:
            f.args['start_reason'] = 'firmware_restart'
            fresh = fixture(start_args=f.args)
            fresh.life._startup_identify()
            assert fresh.life.startup_reconnect['decision'] == 'POST_RESET_ATTACH'
            fresh.query.send.assert_not_called()
            fresh.helper._check_restart.assert_not_called()
        rows.append({'case': name, 'PASS': True, 'native_restart_requested': requested})

    # A reset which did not actually reset the MCU must stop in the native
    # configuration helper; it must not trigger an endless recovery loop.
    config = MCUConfigHelper.__new__(MCUConfigHelper)
    config._printer = NS(get_start_args=lambda: {'start_reason': 'firmware_restart'})
    config._name = 'mcu'
    restart = NS(check_restart_on_crc_mismatch=Mock(), check_restart_on_send_config=Mock())
    config._conn_helper = NS(get_restart_helper=lambda: restart)
    config._send_get_config = lambda: {'is_config': 1, 'crc': 0, 'move_count': 500}
    config._finalize_config = Mock()
    try:
        config._connect()
    except error as exc:
        assert 'Failed automated reset' in str(exc)
    else:
        raise AssertionError('A failed native reset did not stop startup')
    config._finalize_config.assert_not_called()
    restart.check_restart_on_crc_mismatch.assert_not_called()
    rows.append({'case': 'failed_reset_stops_before_configuration', 'PASS': True})
    # Exercise the real native G-code restart's event/dwell/exit ordering.
    # The last healthy heartbeat precedes revocation; none survives the drain.
    from gcode import GCodeDispatch
    from test_restart_heartbeat import board
    current = board()
    clock, order = [100.], []
    current.reactor.monotonic = lambda: clock[0]
    def final_heartbeat():
        assert current.ready and not current.local_stop
        order.append('heartbeat')
    current._heartbeat_cmd.send.side_effect = final_heartbeat
    def dwell(delay):
        assert delay == .5 and current.local_stop and not current.arm_session_confirmed
        clock[0] += delay
        assert current._tick(clock[0]) == current.reactor.NEVER
        order.append('drain')
    toolhead = NS(get_last_move_time=lambda:0., dwell=dwell, wait_moves=lambda:None)
    native = GCodeDispatch.__new__(GCodeDispatch)
    native.is_printer_ready = True
    native.printer = NS(lookup_object=lambda name:toolhead,
        send_event=lambda name,*args:current._handle_restart(*args),
        request_exit=lambda result:order.append(result))
    native.request_restart('restart')
    assert order == ['heartbeat', 'drain', 'restart'], order
    current._heartbeat_cmd.send.assert_called_once_with()
    rows.append({'case': 'native_restart_final_healthy_heartbeat', 'PASS': True})
    print(json.dumps({'status': 'PASS_NATIVE_HOST_RECONNECT_POLICY', 'cases': rows,
                      'actual_pinned_native_restart_helper': True,
                      'actual_pinned_native_config_helper': True,
                      'physical_UART': False, 'MCU_reset_executed': False,
                      'printer_heating_or_motion_executed': False}))


if __name__ == '__main__':
    main()
