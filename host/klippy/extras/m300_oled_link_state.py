# SPDX-License-Identifier: GPL-3.0-or-later
"""M10: bounded OLED stream recovery policy, independent of Klippy/MCU/menu.

The underlying OledStream is the sole owner of SSD1322 transactions and ACK
ordering. This policy never sends a byte, never fabricates ACK, and never
opens or arms an MCU resource. A retry always means a complete reset + full
visible frame through OledStream.start(), never continuation of a partial RAM
write. Delays/retry counts are engineering safety policy, not measured OEM.
"""
import hashlib
import math


class OledLinkPolicy:
    def __init__(self, retry_delay=1.5, max_retries=2, automatic=True):
        if (not isinstance(retry_delay, (int, float)) or
                isinstance(retry_delay, bool) or
                not math.isfinite(retry_delay) or not .2 <= retry_delay <= 30.):
            raise ValueError('M10 retry_delay must be 0.2..30 s')
        if type(max_retries) is not int or not 0 <= max_retries <= 5:
            raise ValueError('M10 max_retries must be 0..5')
        if type(automatic) is not bool:
            raise ValueError('M10 automatic must be boolean')
        self.retry_delay = float(retry_delay)
        self.max_retries = max_retries
        self.automatic = automatic
        self.generation = 0
        self.reset()

    def reset(self):
        self.generation += 1
        self.state = 'idle'
        self.retry_at = None
        self.retries_used = 0
        self.faults = 0
        self.last_error = None
        self.last_frame = -1
        self.ready_since = None

    def ready(self, now):
        self.reset()
        self.state = 'initializing'

    def stop(self):
        self.reset()
        self.state = 'stopped'

    def manual(self, now):
        self.reset()
        self.state = 'initializing'

    def fault(self, now, reason):
        """Schedule only a bounded retry; never send while awaiting an ACK."""
        self.faults += 1
        self.last_error = str(reason)[:160]
        self.ready_since = None
        if self.automatic and self.retries_used < self.max_retries:
            self.retry_at = now + self.retry_delay * (2 ** self.retries_used)
            self.state = 'retry_wait'
        else:
            self.retry_at = None
            self.state = 'exhausted' if self.automatic else 'manual_required'

    def service(self, now, stream, connected, update_frame=None):
        """Called by the existing, single OLED host timer; no second sender."""
        if not connected:
            return False
        if stream.ready and stream.enabled:
            if self.state != 'ready':
                self.ready_since = now
            self.state = 'ready'
            self.retry_at = None
            # A complete image earns a fresh finite retry budget for a later
            # independent outage; partial operations do not.
            if stream.completed_frames != self.last_frame:
                self.last_frame = stream.completed_frames
                self.retries_used = 0
            return False
        if self.state != 'retry_wait' or self.retry_at is None or now < self.retry_at:
            return False
        if stream.pending is not None or stream.enabled or stream.state != 'fault':
            # Do not bypass pending ACK, shutdown, or another transport owner.
            return False
        if update_frame is not None:
            update_frame(now)
        self.retries_used += 1
        self.retry_at = None
        self.state = 'initializing'
        # OledStream._begin invalidates previous/window, resets/clears the
        # controller and sends latest 8192 bytes before display-on.
        stream.start(now)
        return True

    def status(self, now, stream, connected):
        visible = (stream.previous if stream.ready and stream.enabled else None)
        return {
            'model': 'M300_CLASSIC', 'stage': 'M10',
            'connected': bool(connected), 'state': self.state,
            'stream_state': stream.state,
            'display_ready': bool(connected and stream.ready and stream.enabled),
            'automatic': self.automatic, 'max_retries': self.max_retries,
            'retry_delay_s': self.retry_delay,
            'retries_used': self.retries_used,
            'retry_at': self.retry_at, 'faults': self.faults,
            'last_error': self.last_error,
            'generation': self.generation,
            'completed_frames': stream.completed_frames,
            'visible_frame_sha256': (hashlib.sha256(visible).hexdigest()
                                     if visible is not None else None),
            'pending_ack': stream.pending is not None,
            'ready_since': self.ready_since,
        }
