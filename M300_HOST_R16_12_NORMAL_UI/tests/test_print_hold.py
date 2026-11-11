"""The native print hold needs a continuous, acknowledged physical gesture."""
import unittest

from payload.m300_print_hold import HOLD_SECONDS, PrintHold


class PrintHoldTests(unittest.TestCase):
    def setUp(self):
        self.hold = PrintHold()
        self.view = ('printing', 'job-1', 7)

    def sample(self, t, *, down=True, active=True, view=True, now=None, **changes):
        events = dict(pressed=down, presses=0, releases=0, shorts=0, longs=0, delta=0)
        events.update(changes)
        return self.hold.update(events, t, t if now is None else now,
                                self.view if view is True else view, active=active)

    def test_fires_once_at_ten_seconds_and_consumes_the_release(self):
        self.assertEqual(self.sample(0., presses=1), (True, False))
        for i in range(1, 40):
            self.assertEqual(self.sample(i / 4, longs=int(i == 3)), (True, False))
        self.assertEqual(self.sample(HOLD_SECONDS), (True, True))
        self.assertEqual(self.sample(10.25), (True, False))
        self.assertEqual(self.sample(10.5, down=False, active=False, releases=1), (True, False))
        self.assertEqual(self.sample(10.75, down=False, active=False), (False, False))

    def test_old_hold_cannot_become_a_reprint_hold_when_view_changes(self):
        self.sample(0., presses=1)
        for i in range(1, 70):
            token = self.view if i < 36 else ('done', 'job-1', 7)
            self.assertFalse(self.sample(i / 4, view=token)[1])
        self.sample(17.5, down=False, releases=1, view=('done', 'job-1', 7))
        self.assertFalse(self.sample(17.75, presses=1, view=('done', 'job-1', 7))[1])
        for i in range(1, 41):
            self.assertEqual(self.sample(17.75 + i / 4, view=('done', 'job-1', 7))[1], i == 40)

    def test_unseen_and_wake_gestures_cannot_arm(self):
        # The wake guard zeroes press events but still reports physical down.
        self.sample(0., presses=0, view=None)
        for i in range(1, 45):
            self.assertFalse(self.sample(i / 4)[1])
        self.assertEqual(self.sample(11.25, down=False, releases=1), (True, False))
        # An actual press can also arrive before the new frame is acknowledged.
        self.sample(11.5, presses=1, view=None)
        for i in range(1, 45):
            self.assertFalse(self.sample(11.5 + i / 4)[1])

    def test_invalid_timestamps_and_missing_packets_invalidate_continuity(self):
        for lost in ('invalid', 'late', 'gap', 'reordered'):
            with self.subTest(lost=lost):
                self.hold.reset()
                self.sample(0., presses=1)
                for i in range(1, 39):
                    self.sample(i / 4)
                if lost == 'invalid':
                    self.hold.update(None, 9.75, 9.75, self.view)
                elif lost == 'late':
                    self.sample(9.75, now=10.75)
                elif lost == 'reordered':
                    self.sample(9.25)
                start = 11. if lost in ('gap', 'late') else 10.
                for i in range(45):
                    self.assertFalse(self.sample(start + i / 4)[1])

    def test_release_and_repress_in_one_snapshot_never_counts_as_continuous(self):
        self.sample(0., presses=1)
        for i in range(1, 40):
            self.sample(i / 4)
        self.assertFalse(self.sample(10., presses=1, releases=1)[1])
        for i in range(1, 45):
            self.assertFalse(self.sample(10. + i / 4)[1])

    def test_reconnect_requires_a_new_press(self):
        self.sample(0., presses=1)
        for i in range(1, 40):
            self.sample(i / 4)
        self.hold.reset()
        for i in range(45):
            self.assertFalse(self.sample(10. + i / 4)[1])

    def test_early_release_and_rotation_cannot_authorize_actions(self):
        self.sample(0., presses=1)
        self.assertEqual(self.sample(.25, down=False, releases=1, shorts=1), (True, False))
        self.sample(.5, presses=1)
        self.sample(.75, delta=1)
        for i in range(1, 45):
            self.assertFalse(self.sample(.75 + i / 4)[1])
