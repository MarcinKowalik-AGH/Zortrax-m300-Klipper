# SPDX-License-Identifier: GPL-3.0-or-later
"""SSD1322 power transactions at existing M300 frame/ACK boundaries.

The wrapped native stream still owns frames, tokens, DMA, and its MCU queue.
No reset, power-gate, heater, motion, or host-link operation is introduced.
"""
from collections import deque

AWAKE, DIM, OFF = 'AWAKE', 'DIM', 'OFF'


class DisplayStream:
    def __init__(self, base, normal=159, dim=32):
        object.__setattr__(self, '_base', base)
        object.__setattr__(self, '_local', {
            'normal': normal, 'dim': dim, 'mode': AWAKE, 'desired': AWAKE,
            'ops': deque(), 'pending': None, 'transaction': None,
            'wake_frame': None, 'restart': False, 'changes': 0,
            'contrast': 159})

    def __getattr__(self, name):
        return getattr(self._base, name)

    def __setattr__(self, name, value):
        setattr(self._base, name, value)

    @property
    def pending(self):
        return self._local['pending'] or self._base.pending

    @property
    def inflight(self):
        result = tuple(getattr(self._base, 'inflight', ()))
        own = self._local['pending']
        return result + ((own,) if own else ())

    @property
    def display_mode(self):
        return self._local['mode']

    @property
    def requested_mode(self):
        return self._local['desired']

    @property
    def display_changes(self):
        return self._local['changes']

    def set_mode(self, mode):
        if mode not in (AWAKE, DIM, OFF):
            raise ValueError('Unknown display mode')
        self._local['desired'] = mode

    def _clear(self):
        s = self._local
        s['ops'].clear()
        s.update(pending=None, transaction=None, wake_frame=None, restart=False,
                 mode=AWAKE, desired=AWAKE, contrast=159)

    def start(self, now):
        # Never drop an outstanding command or its data byte before reinit.
        if self._local['pending'] or self._local['ops']:
            self._local['restart'] = True
            self._base.ready = False
            self._base.state = 'reinitializing'
            return
        self._clear()
        self._base.start(now)

    def stop(self, reason=None, state='stopped'):
        self._clear()
        self._base.stop(reason, state)

    def ack(self, token, now):
        p = self._local['pending']
        if p is None:
            return self._base.ack(token, now)
        if token != p[0] or not self._base.enabled:
            self._base.ignored_acks += 1
            return False
        self._local['pending'] = None
        self._base.acked += 1
        return True

    def _boundary(self):
        b = self._base
        return (b.ready and b.operations is None and b.pending is None
                and not getattr(b, 'inflight', ())
                and not getattr(b, '_held', None)
                and not b.restart_requested)

    def _queue(self, goal, stage, operations):
        self._local['transaction'] = (goal, stage)
        self._local['ops'].extend(operations)

    def _finish(self):
        s = self._local
        transaction, s['transaction'] = s['transaction'], None
        if transaction is None:
            return
        goal, stage = transaction
        if goal != OFF:
            s['contrast'] = s['normal'] if goal == AWAKE else s['dim']
        if stage == 'prepare_wake':
            # Update visible RAM while AE is still in force, then send AF.
            self._base.previous = None
            self._base.next_frame = self._base.next_interactive = 0.
            s['wake_frame'] = goal
        else:
            s['mode'], s['wake_frame'] = goal, None
            s['changes'] += 1

    def _emit(self, now):
        s, b = self._local, self._base
        dc, data = s['ops'][0]
        fast = hasattr(b, 'inflight')
        if fast and b.active_work:
            cost = len(data) + 20
            b.work_credit = min(208., b.work_credit
                + max(0., now - b.credit_at) * b.work_bytes_per_second)
            b.credit_at = now
            if cost > b.work_credit + 1.e-9:
                b.budget_at = now + (cost - b.work_credit) / b.work_bytes_per_second
                return None
            b.work_credit -= cost
            b.budget_at = now
        s['ops'].popleft()
        b.token = (b.token + 1) & 65535
        s['pending'] = (b.token, now + b.timeout, 0.)
        b.sent += 1
        if fast:
            b.max_pending = max(b.max_pending, 1)
            b.payload_bytes += len(data)
            b.wire_bytes += len(data)
            return 'burst', b.token, (dc, 0, len(data), data)
        return 'write', b.token, (dc, data)

    def step(self, now):
        s, b = self._local, self._base
        if not b.enabled:
            return None
        if s['pending']:
            if now >= s['pending'][1]:
                self.stop('Display command ACK timeout; MCU reset required',
                          'reset_required')
                raise TimeoutError(self.failure)
            return None
        if s['ops']:
            return self._emit(now)
        self._finish()
        if s['restart']:
            self._clear()
            b.start(now)
        if not self._boundary():
            return b.step(now)
        goal = s['desired']
        if s['wake_frame'] is not None:
            if goal == s['wake_frame'] and b.previous == b.latest:
                self._queue(goal, 'apply', [(0, bytes([0xaf]))])
                return self._emit(now)
            if goal != s['wake_frame']:
                s['wake_frame'] = None
            else:
                return b.step(now)
        target_contrast = s['normal'] if goal == AWAKE else s['dim']
        if (goal != s['mode'] or
                (goal != OFF and s['contrast'] != target_contrast)):
            if goal == OFF:
                self._queue(goal, 'apply', [(0, bytes([0xae]))])
            else:
                contrast = s['normal'] if goal == AWAKE else s['dim']
                stage = 'prepare_wake' if s['mode'] == OFF else 'apply'
                self._queue(goal, stage, [(0, bytes([0xc1])),
                                          (1, bytes([contrast]))])
            return self._emit(now)
        # Preserve the host lease and encoder, but send no hidden RAM frames.
        if s['mode'] == OFF:
            return None
        return b.step(now)

    def next_wakeup(self, now):
        s, b = self._local, self._base
        if s['pending']:
            return s['pending'][1]
        if s['ops'] or s['transaction'] or s['restart']:
            return max(now + .0001, getattr(b, 'budget_at', now))
        if s['wake_frame'] is not None:
            return b.next_wakeup(now) if hasattr(b, 'next_wakeup') else now + .002
        contrast = s['normal'] if s['desired'] == AWAKE else s['dim']
        if (b.enabled and b.ready and (s['mode'] != s['desired']
                or (s['desired'] != OFF and s['contrast'] != contrast))):
            return now + .0001
        if s['mode'] == OFF and b.enabled:
            return now + 1.
        return b.next_wakeup(now) if hasattr(b, 'next_wakeup') else now + .002
