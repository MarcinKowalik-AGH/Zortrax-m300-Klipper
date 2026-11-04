"""Exercise the shipped DMA planner and its frame acknowledgement boundary."""
import unittest

from payload.m300_oled_transport import (FastOledStream, diff_regions, diff_window,
                                         fast_frame_operations, _fast_update_operations)


class OledRlePlanTests(unittest.TestCase):
    def test_compressible_rectangle_beats_raw_preferred_tiles(self):
        before = bytes(8192)
        after = bytearray(before)
        after[0:2] = after[1022:1024] = b'\xff\xff'
        after = bytes(after)
        self.assertEqual(len(diff_regions(before, after)), 2)
        self.assertEqual(list(_fast_update_operations(before, after)),
                         list(fast_frame_operations(after, *diff_window(before, after))))

    def test_tiles_still_win_for_widely_separated_updates(self):
        before = bytes(8192)
        after = b'\xff\xff' + before[2:-2] + b'\xff\xff'
        tiles = diff_regions(before, after)
        self.assertEqual(len(tiles), 2)
        expected = [op for window in tiles for op in fast_frame_operations(after, *window)]
        self.assertEqual(list(_fast_update_operations(before, after)), expected)
        self.assertEqual(list(_fast_update_operations(after, after)), [])

    def test_dma_sends_selected_blocks_and_commits_after_final_ack(self):
        before = bytes(8192)
        after = bytearray(before)
        after[0:2] = after[1022:1024] = b'\xff\xff'
        after = bytes(after)
        expected = list(fast_frame_operations(after, *diff_window(before, after)))
        stream = FastOledStream()
        stream.enabled = stream.ready = True
        stream.previous = before
        stream.request(after, urgent=True)
        for index, (kind, args, delay) in enumerate(expected):
            actual_kind, token, actual_args = stream.step(1.)
            self.assertEqual((actual_kind, actual_args), (kind, args))
            if index < len(expected) - 1:
                self.assertTrue(stream.ack(token, 1.))
        self.assertIsNone(stream.step(1.))
        self.assertEqual(stream.previous, before)
        self.assertTrue(stream.ack(token, 1.))
        self.assertIsNone(stream.step(1.))
        self.assertEqual(stream.previous, after)
        self.assertEqual(stream.completed_frames, 1)
