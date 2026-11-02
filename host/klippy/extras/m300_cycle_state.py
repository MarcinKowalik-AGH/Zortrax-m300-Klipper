# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure M08 22-state M300 job/material cycle contract.

This module contains no Klippy imports and no hardware I/O.  It is the neutral
executor contract recovered from the M300 A-D specification: the M08 adapter
maps these phases to the already-qualified M02/M03/M06/M07 owners.
"""
from collections import deque
from copy import deepcopy
import math

STATES = (
    'IDLE', 'PREPARING_PRINT', 'PRINTING', 'PAUSE_PARK', 'PAUSED',
    'CHANGE_UNLOAD', 'CHANGE_INSERT', 'CHANGE_LOAD',
    'RESUME_HEAT', 'RESUME_PURGE', 'RESUME_CLEAN', 'RESUME_RETURN',
    'LOAD_HEAT', 'LOAD_READY', 'LOAD_RUN',
    'UNLOAD_HEAT', 'UNLOAD_READY', 'UNLOAD_RUN',
    'COMPLETE', 'CANCELLED', 'FILE_ERROR', 'FAULT',
)
STATE_SET = frozenset(STATES)
TERMINAL = frozenset({'IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR', 'FAULT'})
STARTABLE = frozenset({'IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR'})

TRANSITIONS = {
    ('PREPARING_PRINT', 'ready'): 'PRINTING',
    ('PRINTING', 'pause'): 'PAUSE_PARK',
    ('PAUSE_PARK', 'parked'): 'PAUSED',
    ('PAUSED', 'change'): 'CHANGE_UNLOAD',
    ('CHANGE_UNLOAD', 'unloaded'): 'CHANGE_INSERT',
    ('CHANGE_INSERT', 'inserted'): 'CHANGE_LOAD',
    ('CHANGE_LOAD', 'loaded'): 'PAUSED',
    ('PAUSED', 'resume'): 'RESUME_HEAT',
    ('RESUME_HEAT', 'heated'): 'RESUME_PURGE',
    ('RESUME_PURGE', 'purged'): 'RESUME_CLEAN',
    ('RESUME_CLEAN', 'cleaned'): 'RESUME_RETURN',
    ('RESUME_RETURN', 'returned'): 'PRINTING',
    ('LOAD_HEAT', 'heated'): 'LOAD_READY',
    ('LOAD_READY', 'confirmed'): 'LOAD_RUN',
    ('LOAD_RUN', 'completed'): 'IDLE',
    ('UNLOAD_HEAT', 'heated'): 'UNLOAD_READY',
    ('UNLOAD_READY', 'confirmed'): 'UNLOAD_RUN',
    ('UNLOAD_RUN', 'completed'): 'IDLE',
    ('PRINTING', 'eof'): 'COMPLETE',
}

class CycleStateError(ValueError):
    pass

def _now(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CycleStateError('now must be finite') from exc
    if not math.isfinite(result):
        raise CycleStateError('now must be finite')
    return result

class CycleState:
    """Revocable session token plus the recovered 22 user-visible phases."""
    def __init__(self, history_limit=128):
        if isinstance(history_limit, bool) or not isinstance(history_limit, int) or not 1 <= history_limit <= 4096:
            raise CycleStateError('history_limit must be in 1..4096')
        self.state = 'IDLE'
        self.token = 0
        self.reason = None
        self.context = {}
        self.history = deque(maxlen=history_limit)

    def _enter(self, state, event, now, reason=None):
        if state not in STATE_SET:
            raise CycleStateError('unknown state: ' + str(state))
        previous = self.state
        self.state, self.reason = state, reason
        self.history.append({'from': previous, 'to': state, 'event': event,
                             'token': self.token, 'at': _now(now), 'reason': reason})

    def start_print(self, context, now):
        if self.state not in STARTABLE:
            raise CycleStateError('print start unavailable in ' + self.state)
        if not isinstance(context, dict):
            raise CycleStateError('context must be a dictionary')
        self.token += 1
        self.context = deepcopy(context)
        self._enter('PREPARING_PRINT', 'start_print', now)
        return self.token

    def start_service(self, mode, context, now):
        if self.state != 'IDLE':
            raise CycleStateError('standalone material service requires IDLE')
        if mode not in ('LOAD', 'UNLOAD'):
            raise CycleStateError('mode must be LOAD or UNLOAD')
        self.token += 1
        self.context = deepcopy(context if isinstance(context, dict) else {})
        self._enter(mode + '_HEAT', 'start_' + mode.lower(), now)
        return self.token

    def advance(self, event, token, now):
        if isinstance(token, bool) or not isinstance(token, int):
            raise CycleStateError('token must be an integer')
        if token != self.token:
            return False
        target = TRANSITIONS.get((self.state, event))
        if target is None:
            raise CycleStateError('event %s invalid in %s' % (event, self.state))
        self._enter(target, event, now)
        return True

    def cancel(self, reason, now):
        if self.state in TERMINAL:
            return None
        self.token += 1
        self._enter('CANCELLED', 'cancel', now, str(reason)[:512])
        return self.token

    def file_error(self, reason, now):
        if self.state == 'FAULT':
            return self.token
        self.token += 1
        self._enter('FILE_ERROR', 'file_error', now, str(reason)[:512])
        return self.token

    def fault(self, reason, now):
        if self.state == 'FAULT':
            return self.token
        self.token += 1
        self._enter('FAULT', 'fault', now, str(reason)[:512])
        return self.token

    def snapshot(self):
        return {'state': self.state, 'token': self.token, 'reason': self.reason,
                'context': deepcopy(self.context), 'history': deepcopy(list(self.history)),
                'state_count': len(STATES), 'states': list(STATES)}
