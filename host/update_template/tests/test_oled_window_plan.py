"""Check the actual OLED transport with and without the idle window planner."""
import unittest

from payload.m300_oled_transport import (FastOledStream, diff_regions, fast_frame_operations,
                                         optimized_frame_operations)


class OledWindowPlanTests(unittest.TestCase):
    def setUp(self):
        self.before = bytes(8192)
        after = bytearray(self.before)
        after[0:2] = after[1022:1024] = b'\xff\xff'
        self.after = bytes(after)
        self.regions = diff_regions(self.before, self.after)
        self.baseline = tuple(op for window in self.regions
                              for op in fast_frame_operations(self.after, *window))
        self.optimized = optimized_frame_operations(self.before, self.after, self.regions)

    def stream_for_frame(self, *, optimize_windows=True, active=False, urgent=True):
        stream = FastOledStream(optimize_windows=optimize_windows)
        stream.enabled = stream.ready = True
        stream.active_work = active
        stream.previous = self.before
        stream.request(self.after, urgent=urgent)
        return stream

    def test_candidate_reduces_payload_without_extra_dma_or_spi_work(self):
        def sizes(ops):
            return sum(len(args[3]) for _, args, _ in ops), sum(args[2] for _, args, _ in ops)

        payload, wire = sizes(self.optimized)
        base_payload, base_wire = sizes(self.baseline)
        self.assertLess(payload, base_payload)
        self.assertLessEqual(wire, base_wire)
        self.assertLessEqual(len(self.optimized), len(self.baseline))
        self.assertEqual(optimized_frame_operations(self.after, self.after, ()), ())

    def test_disabled_background_and_active_work_use_baseline(self):
        for options in ({'optimize_windows': False}, {'active': True}, {'urgent': False}):
            with self.subTest(options=options):
                stream = self.stream_for_frame(**options)
                actual = []
                for index, _ in enumerate(self.baseline):
                    now = 1. + index * .002
                    kind, token, args = stream.step(now)
                    self.assertTrue(stream.ack(token, now))
                    actual.append((kind, args, 0.))
                self.assertEqual(tuple(actual), self.baseline)
                self.assertEqual(stream.optimized_frames, 0)

    def test_optimized_frame_commits_only_after_its_last_ack(self):
        stream = self.stream_for_frame()
        for index, (kind, args, _) in enumerate(self.optimized):
            sent_kind, token, sent_args = stream.step(1.)
            self.assertEqual((sent_kind, sent_args), (kind, args))
            if index < len(self.optimized) - 1:
                self.assertTrue(stream.ack(token, 1.))
        self.assertIsNone(stream.step(1.))
        self.assertEqual(stream.previous, self.before)
        self.assertTrue(stream.ack(token, 1.))
        self.assertIsNone(stream.step(1.))
        self.assertEqual(stream.previous, self.after)
        self.assertEqual(stream.optimized_frames, 1)
