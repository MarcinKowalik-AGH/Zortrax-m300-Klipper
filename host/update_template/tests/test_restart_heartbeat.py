"""A planned native restart starts its drain with one healthy heartbeat."""
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
    obj.printer = NS(is_shutdown=lambda:False)
    obj.gates = 3
    obj.state = dict(configured=1,armed=1,fault=0,gates=3,adc_seen=3,inputs=62,
                     hot_age=100,bed_age=100,heartbeat_age=int(.249*CLOCK_FREQ),hot_raw=1000,bed_raw=3000)
    obj.guard_limits = dict(extruder=(32,1878),heater_bed=(1742,3911))
    obj._heartbeat_cmd = NS(send=Mock())
    return obj


class RestartHeartbeatTests(unittest.TestCase):
    def test_one_final_healthy_heartbeat_then_no_armed_session_or_periodic_sends(self):
        obj=board()
        obj._handle_restart()
        obj._heartbeat_cmd.send.assert_called_once_with()
        self.assertTrue(obj.local_stop)
        self.assertFalse(obj.ready or obj.arm_session_confirmed)
        self.assertIsNone(obj.arm_requested_at)
        obj.reactor.update_timer.assert_called_once_with(obj._timer,obj.reactor.NEVER)
        self.assertEqual(obj._tick(100.1),obj.reactor.NEVER)
        obj._handle_restart()
        obj._heartbeat_cmd.send.assert_called_once_with()

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
