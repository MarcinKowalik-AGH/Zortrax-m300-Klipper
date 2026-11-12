# SPDX-License-Identifier: GPL-3.0-or-later
"""Recognize a continuous knob hold without borrowing the MCU menu-long event."""
import math

HOLD_SECONDS = 10.
# The R14.5 panel emits 250 ms heartbeats even while the button is held.
PANEL_FRESHNESS = .75


class PrintHold:
    """Tie one physical button cycle to one acknowledged semantic view."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._claimed = False
        self._last_received = None
        self._started = None
        self._view = None

    def update(self, events, received_at, now, view, *, active=True, allow_short=False):
        """Return (consumed, fired) for each delivered encoder snapshot.

        `events` comes from EncoderSnapshots after the OLED wake guard.
        `view` is the acknowledged semantic identity or None. `active` is
        true on a page with a hold action, even before its first frame ACK.
        Keep calling on other pages to swallow any trailing release.
        """
        consumed = active or self._claimed
        previous = self._last_received
        if (events is None
                or type(received_at) not in (int, float)
                or not math.isfinite(received_at)
                or not 0. <= now - received_at <= PANEL_FRESHNESS
                or (previous is not None and received_at <= previous)):
            self._started = None
            return consumed, False
        self._last_received = received_at
        if events['pressed'] is not True:
            short = (allow_short and self._started is not None and view == self._view
                     and received_at - previous <= PANEL_FRESHNESS
                     and events['shorts'] == events['releases'] == 1
                     and not (events['presses'] or events['longs'] or events['delta']))
            self._claimed = False
            self._started = None
            return consumed and not short, False
        if not consumed:
            return False, False

        # A hidden/wake press still owns its release. Only a new press on an
        # acknowledged view can arm. Coalesced release/repress and rotation
        # make the gesture ambiguous. The short MCU long has no authority.
        new_press = (not self._claimed and events['presses'] == 1
                     and events['longs'] == 0)
        self._claimed = True
        if (not active or view is None or events['releases']
                or events['shorts'] or events['delta']):
            self._started = None
        elif new_press:
            self._view = view
            self._started = received_at
        elif (events['presses'] or view != self._view or previous is None
                or received_at - previous > PANEL_FRESHNESS):
            self._started = None

        fired = self._started is not None and received_at - self._started >= HOLD_SECONDS
        if fired:
            self._started = None
        return True, fired
