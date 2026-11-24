# Marcin Kowalik <mkowalik@agh.edu.pl>
# test_restart_heartbeat.py - Sprawdza zachowanie nadzoru łączności podczas restartu hosta i ponownego połączenia.
"""Supervise the native drain, reset MCU on SAVE_CONFIG, stop on disconnect."""
from types import SimpleNamespace as NS
from unittest.mock import Mock
import unittest

from payload.m300_mcu import M300MCU, CLOCK_FREQ


def board():
    obj = M300MCU.__new__(M300MCU)
    obj.ready = obj.connected = obj.arm_session_confirmed = True
    obj.local_stop = False
    obj.arm_requested_at, obj.arm_request_clock = 99., 123
    obj.last_state_time = 99.9
    obj.reactor = NS(monotonic=lambda:100.,update_timer=Mock(),NEVER=1.e30)
    obj._timer = object()
    obj.printer = NS(is_shutdown=lambda:False, invoke_shutdown=Mock())
    obj._query_cmd = NS(send=Mock())
    obj.gates = 3
    obj.state = dict(configured=1,armed=1,fault=0,gates=3,adc_seen=3,inputs=62,
                     hot_age=100,bed_age=100,heartbeat_age=int(.249*CLOCK_FREQ),hot_raw=1000,bed_raw=3000)
    obj.guard_limits = dict(extruder=(32,1878),heater_bed=(1742,3911))
    obj._heartbeat_cmd = NS(send=Mock())
    return obj


class RestartHeartbeatTests(unittest.TestCase):
    def test_restart_keeps_heartbeat_during_drain_and_disconnect_stops_it(self):
        obj=board()
        obj._handle_restart()
        obj._heartbeat_cmd.send.assert_called_once_with()
        self.assertFalse(obj.local_stop)
        self.assertEqual(obj._tick(100.1),100.1+.25)
        self.assertEqual(obj._heartbeat_cmd.send.call_count,2)
        obj._handle_restart()  # A repeated request cannot extend the deadline.
        self.assertEqual(obj._restart_deadline,220.)
        obj._handle_disconnect()
        self.assertEqual(obj._tick(100.2),obj.reactor.NEVER)
        self.assertFalse(obj.arm_session_confirmed)

    def test_save_config_resets_mcu_and_restart_drain_has_finite_deadline(self):
        obj=board()
        self.assertEqual(obj.prepare_restart('restart'),'firmware_restart')
        self.assertEqual(obj.prepare_restart('firmware_restart'),'firmware_restart')
        self.assertEqual(obj.prepare_restart('exit'),'exit')
        obj._handle_restart()
        self.assertEqual(obj._tick(220.),obj.reactor.NEVER)
        obj.printer.invoke_shutdown.assert_called_once()
        self.assertFalse(obj.arm_session_confirmed)

    def test_shutdown_stale_status_latched_fault_and_stopped_host_never_send_a_final_heartbeat(self):
        for condition in ('shutdown','stale','fault','stopped','disconnected'):
            with self.subTest(condition=condition):
                obj=board()
                if condition=='shutdown':obj.printer.is_shutdown=lambda:True
                elif condition=='stale':obj.last_state_time=98.
                elif condition=='fault':obj.state['fault']=1
                elif condition=='stopped':obj.local_stop=True
                else:obj.connected=False
                obj._handle_restart()
                obj._heartbeat_cmd.send.assert_not_called()
                self.assertTrue(obj.local_stop)
                self.assertFalse(obj.ready or obj.arm_session_confirmed)

    def test_transport_failure_still_revokes_the_old_session(self):
        obj=board()
        obj._heartbeat_cmd.send.side_effect=RuntimeError('link lost')
        with self.assertLogs(level='ERROR'):
            obj._handle_restart()
        self.assertTrue(obj.local_stop)
        self.assertFalse(obj.ready or obj.arm_session_confirmed)

class NativeRestartDispatchTests(unittest.TestCase):
    def test_save_config_restart_resets_firmware_after_native_drain(self):
        from test_macro_dispatch import dispatcher
        g, printer, output = dispatcher()
        events=[]
        obj=board()
        toolhead=NS(get_last_move_time=lambda:12.,
                    dwell=lambda delay:events.append(('dwell',delay)),
                    wait_moves=lambda:events.append(('drained',)))
        printer.lookup_object=lambda name,default=None:obj if name=='m300_mcu' else toolhead
        printer.send_event=lambda *args:obj._handle_restart()
        printer.request_exit=lambda result:events.append(('exit',result))
        g.request_restart('restart')
        self.assertEqual(events,[('dwell',.5),('drained',),('exit','firmware_restart')])
        self.assertTrue(obj.ready)
