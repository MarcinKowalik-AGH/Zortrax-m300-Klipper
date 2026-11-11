"""Display-only re-claim with cancelled DMA, late ACKs and native queue order."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

import test_display
from payload.m300_oled import M300OLED
from tests.reference.m300_oled import M300OLED as PreviousOLED


def fixture():
    h = test_display.Harness()
    calls = []
    objects = {}
    o = M300OLED.__new__(M300OLED)
    o.printer = NS(lookup_object=lambda name, default=None: objects.get(name, default),
                   command_error=RuntimeError)
    o.reactor = NS(monotonic=lambda: h.now)
    o.stream, o.fast, o.connected, o.cq = h.stream, True, True, object()
    o.generation, o._input_epoch = 1, 0
    o._presented_context, o._presented_actions = 'old view', ('old action',)
    o._render_key = o._render_wire = 'old view'
    o.encoder = NS(reset=Mock())
    o._clear_job_view, o._clear_filament_view = Mock(), Mock()
    o._render = lambda now: o.stream.request(bytes([47])*8192)
    o._link = lambda: None
    def claim(command_queue=None):
        # The MCU cancels its entire DMA FIFO; none of its old ACKs will
        # arrive. The shared native queue also orders any unsent old writes
        # before this boundary, and all new initialization after it.
        calls.append(('claim', command_queue))
    objects['m300_lifecycle'] = NS(claim=claim)
    return h, o, calls


def pending_window(h):
    h.stream.request(bytes([99])*8192, urgent=True)
    pending = []
    for _ in range(4):
        op = h.once(acknowledge=False)
        assert op is not None
        pending.append(op[1])
    return pending


class OLEDReclaimTests(unittest.TestCase):
    def test_previous_adapter_waits_for_acknowledgements_cancelled_by_claim(self):
        h, o, calls = fixture()
        pending_window(h)
        PreviousOLED._reinitialize(o, h.now)
        self.assertEqual(calls, [('claim', None)])
        self.assertTrue(h.base.restart_requested)
        with self.assertRaisesRegex(TimeoutError, 'OLED ACK timeout'):
            h.stream.step(h.now+2.)

    def test_reclaim_discards_only_old_display_work_and_completes_full_init(self):
        h, o, calls = fixture()
        old_tokens = pending_window(h)
        last_token = h.base.token
        o._reinitialize(h.now)
        self.assertEqual(calls, [('claim', o.cq)])
        self.assertFalse(h.base.restart_requested)
        self.assertFalse(h.base.inflight)
        self.assertEqual(h.base.token, last_token)
        for token in old_tokens:
            self.assertFalse(h.stream.ack(token, h.now))
        first = h.once(acknowledge=False)
        self.assertEqual(first[:2], ('control', (last_token+1)&65535))
        self.assertTrue(h.stream.ack(first[1], h.now))
        h.pump()
        self.assertTrue(h.base.ready)
        self.assertEqual(h.base.previous, bytes([47])*8192)
        self.assertEqual(o.generation, 2)
        self.assertEqual(o._input_epoch, 1)
        self.assertIsNone(o._presented_actions)
        o.encoder.reset.assert_called_once_with()

    def test_recovery_from_expired_lease_can_replace_an_uncertain_window(self):
        h, o, calls = fixture()
        pending_window(h)
        with self.assertRaises(TimeoutError):
            h.stream.step(h.now+2.)
        h.now+=2.
        o._reinitialize(h.now, lifecycle_recovery=True)
        h.pump()
        self.assertEqual(calls, [('claim', o.cq)])
        self.assertTrue(h.base.ready)
        self.assertEqual(o.page, 'status')

    def test_manual_reinit_cannot_clear_a_latched_display_failure(self):
        h, o, calls = fixture()
        h.stream.stop('MCU OLED DMA fault', 'reset_required')
        with self.assertRaisesRegex(RuntimeError, 'FIRMWARE_RESTART'):
            o._reinitialize(h.now)
        self.assertFalse(calls)
        self.assertEqual(h.base.state, 'reset_required')

    def test_reclaim_during_contrast_transfer_discards_its_cancelled_data(self):
        h, o, calls = fixture()
        h.stream.set_mode(test_display.DIM)
        op = h.once(acknowledge=False)
        self.assertEqual(op[2][3], bytes([0xc1]))
        o._reinitialize(h.now)
        self.assertFalse(h.stream.ack(op[1], h.now))
        self.assertEqual(calls, [('claim', o.cq)])
        h.pump()
        self.assertTrue(h.base.ready)
        self.assertEqual(h.stream.display_mode, test_display.AWAKE)

    def test_frame_timeout_retains_the_missing_tokens_before_queue_is_cleared(self):
        h, o, calls = fixture()
        tokens = pending_window(h)
        with self.assertRaises(TimeoutError):
            h.stream.step(h.now+2.)
        context = h.base.timeout_context
        self.assertEqual([p['token'] for p in context['pending']], tokens)
        self.assertEqual(context['owner'], 'frame')
        self.assertFalse(context['restart_requested'])
        self.assertEqual(context['sent']-context['acked'], 4)
        self.assertFalse(h.base.inflight)

    def test_contrast_timeout_retains_the_power_operation_and_mode(self):
        h, o, calls = fixture()
        h.stream.set_mode(test_display.OFF)
        op = h.once(acknowledge=False)
        with self.assertRaises(TimeoutError):
            h.stream.step(h.now+2.)
        self.assertEqual(h.base.timeout_context['owner'], 'display_power')
        self.assertEqual(h.base.timeout_context['pending'][0]['token'], op[1])
        self.assertEqual(h.base.timeout_context['desired'], test_display.OFF)
        self.assertFalse(h.base.enabled)


if __name__ == '__main__':
    unittest.main()
