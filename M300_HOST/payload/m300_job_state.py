# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure classic-M300 M02 session state and bounded Cartesian parking geometry.

No Klippy imports, printer references, I/O, G-code execution or motor commands.
Provenance: M300 behavior contract (2026-10-19), section 8, and the audited
C_PRZERWANIE_WZNOWIENIE cancellation/resume contract. The former inert 22-state
reference is design evidence, not a runtime dependency or stock behavior clone.
"""
from collections import deque
from collections.abc import Mapping
from copy import deepcopy
import math
from numbers import Real


STATES = frozenset({
    'IDLE', 'PREFLIGHT', 'HEATING', 'HOMING', 'PRINTING', 'PAUSING', 'PAUSED',
    'RESUMING', 'RETURNING', 'CANCELLING', 'COMPLETING', 'COMPLETE',
    'CANCELLED', 'FILE_ERROR', 'FAULT',
})
TERMINAL_STATES = frozenset({'IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR', 'FAULT'})
ACTIVE_STATES = STATES - TERMINAL_STATES
START_STATES = frozenset({'IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR'})

_TRANSITIONS = {
    ('PREFLIGHT', 'preflight_ok'): 'HEATING',
    ('HEATING', 'heated'): 'HOMING',
    ('HOMING', 'homed'): 'PRINTING',
    ('PRINTING', 'pause'): 'PAUSING',
    ('PAUSING', 'parked'): 'PAUSED',
    ('PAUSED', 'resume'): 'RESUMING',
    ('RESUMING', 'reheated'): 'RETURNING',
    ('RETURNING', 'returned'): 'PRINTING',
    ('PRINTING', 'eof'): 'COMPLETING',
    ('COMPLETING', 'completed'): 'COMPLETE',
    ('CANCELLING', 'cancelled'): 'CANCELLED',
}
_TERMINAL_ACKS = frozenset({('COMPLETE', 'completed'), ('CANCELLED', 'cancelled')})


class JobStateError(ValueError):
    """A current-session operation or geometric request violates the contract."""


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise JobStateError('%s must be a finite real number' % name)
    try:
        result = float(value)
    except (ValueError, OverflowError, TypeError) as exc:
        raise JobStateError('%s must be a finite real number' % name) from exc
    if not math.isfinite(result):
        raise JobStateError('%s must be a finite real number' % name)
    return result


def _reason_text(reason):
    if not isinstance(reason, str) or not reason.strip():
        raise JobStateError('A nonempty textual reason is required')
    # Retain a bounded diagnostic; never retain an exception/driver object.
    return reason.strip()[:512]


class JobState:
    """Single job session with revocable continuation tokens and a fault latch.

    start/cancel/accepted fail increment the token before cleanup can be begun
    by an adapter. Ordinary phase transitions keep the session token. An old
    callback returns False without inspecting its event or timestamp. Current
    invalid transitions raise JobStateError and leave the state untouched.

    context is copied on admission and on every read. Adapter-owned live motion,
    file and heater objects belong outside this immutable source context.
    """
    def __init__(self, history_limit=64):
        if (isinstance(history_limit, bool) or not isinstance(history_limit, int)
                or not 1 <= history_limit <= 4096):
            raise JobStateError('history_limit must be an integer in 1..4096')
        self._state = 'IDLE'
        self._token = 0
        self._context = {}
        self._reason = None
        self._history = deque(maxlen=history_limit)

    @property
    def state(self):
        return self._state

    @property
    def token(self):
        return self._token

    @property
    def context(self):
        return deepcopy(self._context)

    @property
    def reason(self):
        return self._reason

    @property
    def history(self):
        return deepcopy(list(self._history))

    @property
    def active(self):
        return self._state in ACTIVE_STATES

    def _enter(self, state, event, now, reason=None):
        previous = self._state
        self._state = state
        self._reason = reason
        self._history.append({'from': previous, 'to': state, 'event': event,
                              'token': self._token, 'at': now, 'reason': reason})

    def start(self, context, now):
        now = _finite(now, 'now')
        if self._state not in START_STATES:
            raise JobStateError('Cannot start a job from ' + self._state)
        if not isinstance(context, dict):
            raise JobStateError('Job context must be a dictionary')
        try:
            source = deepcopy(context)
        except Exception as exc:
            raise JobStateError('Job context must support an independent copy') from exc
        # No fallible validation/copy remains after token revocation begins.
        self._token += 1
        self._context = source
        self._enter('PREFLIGHT', 'start', now)
        return self._token

    def advance(self, event, token, now):
        if isinstance(token, bool) or not isinstance(token, int):
            raise JobStateError('Continuation token must be an integer')
        if token != self._token:
            return False
        now = _finite(now, 'now')
        if not isinstance(event, str):
            raise JobStateError('Event must be a string')
        pair = (self._state, event)
        if pair in _TERMINAL_ACKS:
            return True  # Duplicate final cleanup ACK: no second transition.
        target = _TRANSITIONS.get(pair)
        if target is None:
            raise JobStateError('Event %s is invalid in %s' % (event, self._state))
        reason = self._reason if target == 'CANCELLED' else None
        if target == 'COMPLETE':
            reason = 'completed'
        self._enter(target, event, now, reason)
        return True

    def cancel(self, reason, now):
        now = _finite(now, 'now')
        if self._state in TERMINAL_STATES:
            return None
        if self._state == 'CANCELLING':
            return self._token
        reason = _reason_text(reason)
        self._token += 1  # Revoke every pending old phase before adapter cleanup.
        self._enter('CANCELLING', 'cancel', now, reason)
        return self._token

    def fail(self, reason, now, kind='FAULT'):
        now = _finite(now, 'now')
        if kind not in ('FAULT', 'FILE_ERROR'):
            raise JobStateError('Failure kind must be FAULT or FILE_ERROR')
        if self._state == 'FAULT':
            return self._token
        if kind == 'FILE_ERROR' and self._state in {
                'CANCELLING', 'CANCELLED', 'COMPLETE', 'FILE_ERROR'}:
            return self._token
        reason = _reason_text(reason)
        self._token += 1  # Fault wins over cancellation, EOF, and completed work.
        self._enter(kind, 'fail', now, reason)
        return self._token

    def snapshot(self):
        return {'state': self._state, 'token': self._token,
                'active': self.active, 'context': self.context,
                'reason': self._reason, 'history': self.history}


def _vector(values, lengths, name):
    if isinstance(values, (str, bytes, bytearray, Mapping)):
        raise JobStateError('%s must be a coordinate sequence' % name)
    try:
        result = tuple(values)
    except TypeError as exc:
        raise JobStateError('%s must be a coordinate sequence' % name) from exc
    if len(result) not in lengths:
        raise JobStateError('%s must have %s coordinates' %
                            (name, ' or '.join(str(n) for n in sorted(lengths))))
    return tuple(_finite(v, '%s[%d]' % (name, i)) for i, v in enumerate(result))


def bounded_park(position, axis_min, axis_max, park_xy, z_hop, min_clearance):
    """Plan XYZ-only lift/park/return inside supplied Cartesian axis bounds.

    position and axis bounds may be XYZ or XYZE; every supplied number must be
    finite. The E coordinate is diagnostic only and is NEVER put in a move.
    Requested XY must already be in bounds. Only Z-hop is clamped. When actual
    lift is below the strictly positive clearance, stay at the original XY;
    an available partial vertical lift may still be returned as a move.

    Geometry alone does not authorize motion or resume. The adapter must still
    verify the same live session, unchanged/known machine position, homing,
    current limits, sensors, temperatures and local MCU guard before execution.
    """
    full_position = _vector(position, {3, 4}, 'position')
    minimum = _vector(axis_min, {3, 4}, 'axis_min')[:3]
    maximum = _vector(axis_max, {3, 4}, 'axis_max')[:3]
    requested_xy = _vector(park_xy, {2}, 'park_xy')
    requested_hop = _finite(z_hop, 'z_hop')
    clearance = _finite(min_clearance, 'min_clearance')
    if requested_hop < 0:
        raise JobStateError('z_hop must be nonnegative')
    if clearance <= 0:
        raise JobStateError('min_clearance must be strictly positive')
    origin = full_position[:3]
    for index, (lower, upper, current) in enumerate(zip(minimum, maximum, origin)):
        span = upper - lower
        if lower >= upper or not math.isfinite(span):
            raise JobStateError('Invalid finite axis range at index %d' % index)
        if not lower <= current <= upper:
            raise JobStateError('Saved position is outside axis bounds at index %d' % index)
    for index, coordinate in enumerate(requested_xy):
        if not minimum[index] <= coordinate <= maximum[index]:
            raise JobStateError('Requested park XY is outside axis bounds at index %d' % index)

    available = maximum[2] - origin[2]
    desired_lift = min(requested_hop, available)
    lift_z = min(maximum[2], origin[2] + desired_lift)
    if lift_z - origin[2] > desired_lift:
        # Addition may round the destination upward (for example 0.1 + 0.2).
        # Never turn that extra ULP into permission for a lateral clearance.
        lift_z = math.nextafter(lift_z, origin[2])
    # The subtraction reflects the actual representable geometric displacement,
    # rather than a requested value that rounded away at a large coordinate.
    actual_hop = lift_z - origin[2]
    if not 0. <= actual_hop <= desired_lift:
        raise JobStateError('A bounded Z lift is not representable for this geometry')
    xy_allowed = actual_hop >= clearance
    target_xy = requested_xy if xy_allowed else origin[:2]
    lift = (origin[0], origin[1], lift_z)
    target = (target_xy[0], target_xy[1], lift_z)
    xy_moved = target_xy != origin[:2]

    park_moves = []
    if lift != origin:
        park_moves.append(list(lift))
    if target != lift:
        park_moves.append(list(target))
    return_moves = []
    if target != lift:
        return_moves.append(list(lift))  # XY return at the raised Z, never a diagonal descent.
    if lift != origin:
        return_moves.append(list(origin))

    return {
        'origin': list(origin), 'lift': list(lift), 'target': list(target),
        'return_target': list(origin),
        'e_position': full_position[3] if len(full_position) == 4 else None,
        'park_moves': park_moves, 'return_moves': return_moves,
        'requested_z_hop': requested_hop, 'actual_z_hop': actual_hop,
        'available_z_hop': available, 'min_clearance': clearance,
        'xy_allowed': xy_allowed, 'xy_moved': xy_moved,
        'pause_in_place': not xy_moved,
        'clamped_z_hop': actual_hop < requested_hop,
        'return_constraints': {
            'minimum': list(minimum), 'maximum': list(maximum),
            'saved_position': list(origin),
            'requires_known_position': True, 'requires_same_session': True,
            'requires_current_safety_checks': True,
        },
    }
