"""Lost return packets must not be mistaken for unexecuted OLED DMA writes."""
import importlib
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import test_display
from test_oled_reclaim import fixture, pending_window
from payload.m300_oled_transport import FastOledStream


def window(token=7903):
    stream=FastOledStream()
    stream.enabled=stream.ready=True
    stream.previous=bytes(8192)
    stream.request(bytes([63])*8192,urgent=True)
    stream.token=token
    stream.sent=stream.acked=token
    operations=[stream.step(1.) for _ in range(4)]
    return stream,[op[1] for op in operations]


class CumulativeACKTests(unittest.TestCase):
    def test_user_trace_missing_7904_7905_recovers_on_7906_and_7907(self):
        stream,tokens=window()
        self.assertEqual(tokens,[7904,7905,7906,7907])
        self.assertTrue(stream.ack(7906,1.1))
        self.assertEqual(stream.acked,7906)
        self.assertEqual([p[0] for p in stream.inflight],[7907])
        self.assertTrue(stream.ack(7907,1.2))
        self.assertEqual(stream.sent,stream.acked)
        self.assertEqual(stream.recovered_acks,2)
        self.assertEqual(stream.ignored_acks,0)
        self.assertTrue(stream.enabled)
        self.assertIsNone(stream.failure)

    def test_previous_host_reproduces_the_same_missing_packet_deadlock(self):
        previous=importlib.import_module('tests.reference.m300_oled_transport')
        stream,tokens=window()
        self.assertFalse(previous.FastOledStream.ack(stream,7906,1.1))
        self.assertFalse(previous.FastOledStream.ack(stream,7907,1.2))
        self.assertEqual(stream.ignored_acks,2)
        with self.assertRaisesRegex(TimeoutError,'OLED ACK timeout'):
            stream.step(2.01)

    def test_unknown_token_never_confirms_pending_operations(self):
        stream,tokens=window()
        for token in (tokens[0]-1,tokens[-1]+1,65535):
            self.assertFalse(stream.ack(token,1.1))
        self.assertEqual(stream.acked,7903)
        self.assertEqual(len(stream.inflight),4)

    def test_late_duplicate_cannot_confirm_a_new_window(self):
        stream,tokens=window()
        self.assertTrue(stream.ack(tokens[-1],1.1))
        next_op=stream.step(1.2)
        self.assertIsNotNone(next_op)
        for token in tokens:
            self.assertFalse(stream.ack(token,1.3))
        self.assertEqual([p[0] for p in stream.inflight],[next_op[1]])

    def test_fifo_confirmation_survives_unsigned_token_wrap(self):
        stream,tokens=window(65534)
        self.assertEqual(tokens,[65535,0,1,2])
        self.assertTrue(stream.ack(0,1.1))
        self.assertEqual([p[0] for p in stream.inflight],[1,2])
        self.assertTrue(stream.ack(2,1.2))
        self.assertFalse(stream.inflight)
        self.assertEqual(stream.recovered_acks,2)
        self.assertEqual(stream.sent,stream.acked)

    def test_initialization_control_delay_is_still_a_barrier(self):
        stream=FastOledStream()
        stream.start(1.)
        op=stream.step(1.)
        self.assertEqual(op[0],'control')
        self.assertIsNone(stream.step(1.001))
        self.assertFalse(stream.ack(op[1]+1,1.002))
        self.assertTrue(stream.ack(op[1],1.003))
        self.assertIsNone(stream.step(1.012))
        self.assertIsNotNone(stream.step(1.014))

    def test_missing_final_ack_is_not_fabricated(self):
        stream,tokens=window()
        self.assertTrue(stream.ack(tokens[-2],1.1))
        with self.assertRaises(TimeoutError):stream.step(2.01)
        self.assertEqual(stream.acked,7906)
        self.assertFalse(stream.enabled)

    def test_many_lost_ack_packets_preserve_exact_spi_writes_and_frame_commit(self):
        def transmit(drop):
            h=test_display.Harness()
            h.stream.request(bytes((i*19)%256 for i in range(8192)),urgent=True)
            trace=[];completed=[]
            before=h.base.completed_frames
            for _ in range(10000):
                for _ in range(4):
                    op=h.stream.step(h.now)
                    if not op:break
                    trace.append((op[0],op[2]));completed.append(op[1])
                if completed:
                    # MCU executes ALL writes in FIFO order. Drop the first
                    # three return ACKs of each window, not their SPI writes.
                    replies=completed[-1:] if drop else completed
                    for token in replies:self.assertTrue(h.stream.ack(token,h.now))
                    completed=[]
                h.now+=.001
                if h.base.completed_frames>before:
                    self.assertEqual(h.base.previous,h.base.latest)
                    self.assertEqual(h.base.sent,h.base.acked)
                    return trace,h.base.recovered_acks
            self.fail('Frame did not finish')
        full,_=transmit(False)
        damaged,recovered=transmit(True)
        self.assertEqual(damaged,full)
        self.assertGreater(recovered,100)


def healthy_panel():
    h,o,calls=fixture()
    o.printer.is_shutdown=lambda:False
    o.reactor.update_timer=Mock()
    o.reactor.NOW=0.
    o.timer='oled'
    o.page='m04'
    o.mcu_oled_stats=dict(fault=0,queued=0)
    o.mcu_oled_stats_time=h.now
    o.ack_recovery_active=False
    o.ack_recovery_after=0.
    o.ack_recoveries=0
    o.tick_count=0
    o.work_at=o.stats_at=o.query_at=o.render_at=h.now+10000.
    o.commands={kind:NS(send=Mock()) for kind in ('burst','control')}
    life=o.printer.lookup_object('m300_lifecycle')
    life.connected=life.claimed=True
    life.resyncing=False
    life.error=None
    life.state=dict(state=1,fault=0)
    return h,o,calls,life


def lose_last_ack(h,o):
    h.stream.set_mode(test_display.OFF)
    op=h.once(acknowledge=False)
    assert op is not None
    h.now+=1.1
    o.mcu_oled_stats_time=h.now
    o._send_one(h.now)
    return op


class DisplayOnlyRecoveryTests(unittest.TestCase):
    def test_last_lost_ack_reinitializes_display_without_printer_error_or_reset(self):
        h,o,calls,life=healthy_panel()
        with patch('payload.m300_error_codes.report') as report:
            old=lose_last_ack(h,o)
            self.assertEqual(calls,[('claim',o.cq)])
            self.assertTrue(o.ack_recovery_active)
            self.assertEqual(o.ack_recoveries,1)
            self.assertFalse(h.stream.ack(old[1],h.now))
            h.pump()
            o._tick(h.now)
            self.assertFalse(o.ack_recovery_active)
            self.assertTrue(h.base.ready)
            self.assertIsNone(h.base.failure)
            self.assertEqual(o.generation,2)
            self.assertIsNone(o._presented_actions)
            report.assert_not_called()

    def test_new_failure_during_recovery_cannot_create_a_reset_loop(self):
        h,o,calls,life=healthy_panel()
        with patch('payload.m300_error_codes.report') as report:
            lose_last_ack(h,o)
            op=h.once(acknowledge=False)
            self.assertEqual(op[0],'control')
            h.now+=1.1
            o.mcu_oled_stats_time=h.now
            o._send_one(h.now)
            self.assertEqual(len(calls),1)
            self.assertEqual(o.ack_recoveries,1)
            self.assertFalse(h.base.enabled)
            self.assertFalse(o.ack_recovery_active)
            report.assert_called_once()

    def test_mcu_fault_arriving_during_recovery_stops_the_attempt(self):
        h,o,calls,life=healthy_panel()
        o.reactor.register_async_callback=lambda cb:cb(h.now)
        with patch('payload.m300_error_codes.report') as report:
            lose_last_ack(h,o)
            self.assertTrue(o.ack_recovery_active)
            o._stats(dict(blocks=80,wire=1000,queued=0,peak=4,fault=1,
                          spi_hz=4500000,max_busy_ticks=100,
                          **{'#receive_time':h.now}))
            self.assertFalse(o.ack_recovery_active)
            self.assertFalse(h.base.enabled)
            self.assertEqual(h.base.state,'reset_required')
            self.assertEqual(len(calls),1)
            report.assert_called_once()

    def test_repeated_loss_within_thirty_seconds_is_visible_not_a_reset_storm(self):
        h,o,calls,life=healthy_panel()
        with patch('payload.m300_error_codes.report') as report:
            lose_last_ack(h,o)
            h.pump();o._tick(h.now)
            lose_last_ack(h,o)
            self.assertEqual(len(calls),1)
            self.assertFalse(h.base.enabled)
            report.assert_called_once()

    def test_another_isolated_loss_after_cooldown_can_recover(self):
        h,o,calls,life=healthy_panel()
        with patch('payload.m300_error_codes.report') as report:
            lose_last_ack(h,o)
            h.pump();o._tick(h.now)
            h.now+=31.
            lose_last_ack(h,o)
            h.pump();o._tick(h.now)
            self.assertEqual(len(calls),2)
            self.assertEqual(o.ack_recoveries,2)
            self.assertTrue(h.base.ready)
            report.assert_not_called()

    def test_real_mcu_display_fault_blocks_automatic_and_manual_recovery(self):
        h,o,calls,life=healthy_panel()
        o.mcu_oled_stats['fault']=1
        with patch('payload.m300_error_codes.report') as report:
            lose_last_ack(h,o)
            self.assertFalse(calls)
            report.assert_called_once()
        with self.assertRaisesRegex(RuntimeError,'FIRMWARE_RESTART'):
            o._reinitialize(h.now)
        self.assertFalse(calls)

    def test_stale_missing_or_future_status_cannot_authorize_recovery(self):
        for age in (None,-.001,4.001):
            with self.subTest(age=age):
                h,o,calls,life=healthy_panel()
                o.mcu_oled_stats_time=None if age is None else h.now-age
                self.assertFalse(o._recover_lost_ack(h.now))
                self.assertFalse(calls)

    def test_shutdown_or_unhealthy_lease_does_not_recover_display(self):
        for change in ('shutdown','disconnected','unclaimed','resyncing','fault','error'):
            with self.subTest(change=change):
                h,o,calls,life=healthy_panel()
                if change=='shutdown':o.printer.is_shutdown=lambda:True
                elif change=='disconnected':life.connected=False
                elif change=='unclaimed':life.claimed=False
                elif change=='resyncing':life.resyncing=True
                elif change=='fault':life.state['fault']=1
                else:life.error='MCU display fault'
                self.assertFalse(o._recover_lost_ack(h.now))
                self.assertFalse(calls)

    def test_explicit_panel_reinit_can_recover_host_ack_timeout_without_firmware_reset(self):
        h,o,calls,life=healthy_panel()
        h.stream.stop('OLED ACK timeout; MCU reset required','reset_required')
        o._reinitialize(h.now)
        h.pump()
        self.assertTrue(h.base.ready)
        self.assertEqual(calls,[('claim',o.cq)])

    def test_exception_during_display_reclaim_stops_without_retrying_actuators(self):
        h,o,calls,life=healthy_panel()
        life.claim=Mock(side_effect=RuntimeError('serial queue unavailable'))
        self.assertFalse(o._recover_lost_ack(h.now))
        self.assertFalse(h.base.enabled)
        self.assertEqual(h.base.state,'reset_required')
        life.claim.assert_called_once_with(command_queue=o.cq)


if __name__=='__main__':
    unittest.main()
