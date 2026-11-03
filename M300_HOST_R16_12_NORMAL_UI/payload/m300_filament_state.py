# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure M300 M03 filament-session FSM and bounded signed-E segment plans.

No Klippy imports, hardware access, G-code or automatic job resume. Design
provenance: audited M300 A-D contract (2026-10-19), section 4, and C3-C5/C8-C9.
Stock transport counters are evidence for qualification, not default distances.
"""
from collections import deque
from copy import deepcopy
from fractions import Fraction
import math
from numbers import Real


MODES = frozenset({'LOAD', 'UNLOAD', 'CHANGE'})
STATES = frozenset({'IDLE', 'WAIT_PAUSE', 'HEATING', 'REHEATING', 'WAIT_INSERT', 'LOADING',
                    'WAIT_UNLOAD', 'UNLOADING', 'WAIT_PURGE', 'PURGING',
                    'COMPLETING', 'COMPLETE', 'CANCELLING', 'CANCELLED', 'FAULT'})
TERMINAL_STATES = frozenset({'IDLE', 'COMPLETE', 'CANCELLED', 'FAULT'})
ACTIVE_STATES = STATES - TERMINAL_STATES
START_STATES = frozenset({'IDLE', 'COMPLETE', 'CANCELLED'})
TRANSPORT_STATES = {'LOADING': 'load', 'UNLOADING': 'unload', 'PURGING': 'purge'}
WAIT_STATES = frozenset({'WAIT_INSERT', 'WAIT_UNLOAD', 'WAIT_PURGE'})
PROFILE_FIELDS = frozenset({
    'load_mm', 'unload_mm', 'purge_mm', 'max_purge_mm', 'segment_mm',
    'load_speed', 'unload_speed', 'purge_speed',
    'heat_timeout', 'confirm_timeout', 'move_timeout', 'total_timeout',
})
MAX_SEGMENTS = 4096


class FilamentStateError(ValueError):
    """A profile, current-session operation or segment violates the contract."""


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise FilamentStateError('%s must be a finite real number' % name)
    try:
        result = float(value)
    except (ValueError, OverflowError, TypeError) as exc:
        raise FilamentStateError('%s must be a finite real number' % name) from exc
    if not math.isfinite(result):
        raise FilamentStateError('%s must be a finite real number' % name)
    return result


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FilamentStateError('%s must be an integer >= %d' % (name, minimum))
    return value


def _reason(reason):
    if not isinstance(reason, str) or not reason.strip():
        raise FilamentStateError('A nonempty textual reason is required')
    return reason.strip()[:512]


def _as_float(value, name):
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise FilamentStateError('%s must remain finite' % name) from exc
    return _finite(result, name)


def _deadline(now, timeout):
    result = now + timeout
    if not math.isfinite(result) or result <= now:
        raise FilamentStateError('A positive finite deadline is not representable')
    return result


def _split(length, speed, limit, sign):
    """Bound each float segment and never round the requested budget upward."""
    requested, cap = Fraction(length), Fraction(limit)
    ratio = requested / cap
    count = (ratio.numerator + ratio.denominator - 1) // ratio.denominator
    if count > MAX_SEGMENTS:
        raise FilamentStateError('A transport exceeds %d bounded segments' % MAX_SEGMENTS)
    result = [{'delta_e': sign * limit, 'speed': speed} for _ in range(count - 1)]
    tail = requested - (count - 1) * cap
    last = float(tail)
    if Fraction(last) > tail:
        last = math.nextafter(last, 0.)
    if not 0. < last <= limit:
        raise FilamentStateError('Final bounded segment is not representable')
    result.append({'delta_e': sign * last, 'speed': speed})
    return result


def build_plan(mode, profile, native_max_e_dist):
    """Validate explicit profile and precompute all LOAD/UNLOAD/PURGE segments.

    Distances are positive magnitudes; unload is converted to negative delta_e.
    The effective cap is min(segment_mm, native_max_e_dist). A purge request is
    one fixed purge_mm portion; max_purge_mm limits all requests in the session.
    No stock lengths, temperature, acceleration or implicit defaults are used.
    """
    if not isinstance(mode, str) or mode not in MODES:
        raise FilamentStateError('Mode must be LOAD, UNLOAD or CHANGE')
    if not isinstance(profile, dict) or set(profile) != PROFILE_FIELDS:
        raise FilamentStateError('Profile must contain exactly the documented fields')
    values = {key: _finite(profile[key], key) for key in PROFILE_FIELDS}
    for key, value in values.items():
        if value < 0. or (key != 'max_purge_mm' and value == 0.):
            raise FilamentStateError('%s must be %s' %
                                     (key, 'nonnegative' if key == 'max_purge_mm' else 'positive'))
    native = _finite(native_max_e_dist, 'native_max_e_dist')
    if native <= 0.:
        raise FilamentStateError('native_max_e_dist must be positive')
    limit = min(values['segment_mm'], native)
    segments = {
        'load': _split(values['load_mm'], values['load_speed'], limit, 1.),
        'unload': _split(values['unload_mm'], values['unload_speed'], limit, -1.),
        'purge': _split(values['purge_mm'], values['purge_speed'], limit, 1.),
    }
    distances = {name: sum((Fraction(abs(s['delta_e'])) for s in parts), Fraction())
                 for name, parts in segments.items()}
    durations = {name: sum((Fraction(abs(s['delta_e'])) / Fraction(s['speed'])
                           for s in parts), Fraction())
                 for name, parts in segments.items()}
    # Every segment needs enough time even at ideal constant speed. Real
    # acceleration and queue overhead require a qualified, larger host timeout.
    longest = max(Fraction(abs(s['delta_e'])) / Fraction(s['speed'])
                  for parts in segments.values() for s in parts)
    if Fraction(values['move_timeout']) < longest:
        raise FilamentStateError('move_timeout is shorter than an ideal segment')
    requests = int(Fraction(values['max_purge_mm']) / Fraction(values['purge_mm']))
    kinds = ('load',) if mode == 'LOAD' else ('unload',) if mode == 'UNLOAD' else ('unload', 'load')
    if mode == 'UNLOAD':
        requests = 0
    count = sum(len(segments[kind]) for kind in kinds) + requests * len(segments['purge'])
    if count > MAX_SEGMENTS:
        raise FilamentStateError('The full session exceeds %d segments' % MAX_SEGMENTS)
    base = sum((distances[kind] for kind in kinds), Fraction())
    reserved_purge = Fraction(values['max_purge_mm']) if mode != 'UNLOAD' else Fraction()
    ideal = sum((durations[kind] for kind in kinds), Fraction()) + requests * durations['purge']
    if Fraction(values['total_timeout']) < ideal:
        raise FilamentStateError('total_timeout is shorter than planned ideal transport')
    return {
        'version': 1, 'mode': mode, 'profile': values, 'native_max_e_dist': native,
        'segment_limit_mm': limit, 'segments': segments,
        'planned_mm': {name: _as_float(value, name + '_planned_mm')
                       for name, value in distances.items()},
        'base_budget_mm': _as_float(base, 'base_budget_mm'),
        'total_budget_mm': _as_float(base + reserved_purge, 'total_budget_mm'),
        'max_purge_requests': requests,
        'max_segments': count,
        'ideal_transport_seconds': _as_float(ideal, 'ideal_transport_seconds'),
    }


class FilamentState:
    """Revocable, bounded material operation with one acknowledged E segment.

    next_segment reserves absolute distance before an adapter may enqueue it.
    ack_segment is accepted only after the adapter has checked native drain.
    A stale token/phase cannot continue a replacement operation. FAULT latches
    for this object lifetime and never authorizes automatic M02 Resume.
    """
    def __init__(self, history_limit=64):
        history_limit = _integer(history_limit, 'history_limit', 1)
        if history_limit > 4096:
            raise FilamentStateError('history_limit must be <= 4096')
        self._state, self._token, self._phase_id = 'IDLE', 0, 0
        self._mode, self._reason = None, None
        self._context, self._plan = {}, {}
        self._history = deque(maxlen=history_limit)
        self._total_deadline = self._phase_deadline = self._last_now = None
        self._pending = None
        self._segment_id = self._last_ack_id = 0
        self._segments, self._index = [], 0
        self._issued = self._completed = self._budget = Fraction()
        self._purge_requests = 0
        self._reheat_wait = None

    @property
    def state(self):
        return self._state

    @property
    def token(self):
        return self._token

    @property
    def phase_id(self):
        return self._phase_id

    @property
    def mode(self):
        return self._mode

    @property
    def context(self):
        return deepcopy(self._context)

    @property
    def plan(self):
        return deepcopy(self._plan)

    @property
    def reason(self):
        return self._reason

    @property
    def history(self):
        return deepcopy(list(self._history))

    @property
    def active(self):
        return self._state in ACTIVE_STATES

    @property
    def deadline(self):
        candidates = [value for value in (self._total_deadline, self._phase_deadline,
                      None if self._pending is None else self._pending['deadline'])
                      if value is not None]
        return min(candidates) if candidates else None

    @property
    def pending(self):
        return deepcopy(self._pending)

    @property
    def issued_mm(self):
        return float(self._issued)

    @property
    def completed_mm(self):
        return float(self._completed)

    @property
    def remaining_budget(self):
        return float(self._budget - self._issued)

    def _current(self, token, phase_id=None):
        _integer(token, 'token')
        if token != self._token:
            return False
        if phase_id is not None:
            _integer(phase_id, 'phase_id')
            if phase_id != self._phase_id:
                return False
        return True

    def _time(self, now, enforce_deadline=True):
        now = _finite(now, 'now')
        if self._last_now is not None and now < self._last_now:
            raise FilamentStateError('Current-session time must be monotonic')
        if enforce_deadline and self.deadline is not None and now > self.deadline:
            raise FilamentStateError('Current material-operation deadline expired')
        return now

    def _phase_timeout(self, state):
        if state in TERMINAL_STATES:
            return None
        profile = self._plan['profile']
        if state in ('HEATING', 'REHEATING'):
            return profile['heat_timeout']
        if state in WAIT_STATES:
            return profile['confirm_timeout']
        if state in TRANSPORT_STATES:
            # Segment deadlines independently bound every native queue drain.
            return profile['total_timeout']
        return profile['move_timeout']

    def _enter(self, state, event, now, reason=None, new_deadline=None):
        previous = self._state
        self._state, self._reason, self._last_now = state, reason, now
        self._phase_id += 1
        self._phase_deadline = new_deadline
        if state in TERMINAL_STATES:
            self._total_deadline = None
        self._pending = None
        kind = TRANSPORT_STATES.get(state)
        self._segments = deepcopy(self._plan['segments'][kind]) if kind else []
        self._index = 0
        self._history.append({'from': previous, 'to': state, 'event': event,
                              'token': self._token, 'phase_id': self._phase_id,
                              'at': now, 'reason': reason})

    def start(self, mode, plan, context, now):
        now = self._time(now, enforce_deadline=False)
        if self._state not in START_STATES:
            raise FilamentStateError('Cannot start material operation from ' + self._state)
        if not isinstance(plan, dict) or plan.get('mode') != mode:
            raise FilamentStateError('Preflight plan mode does not match the request')
        validated = build_plan(mode, plan.get('profile'), plan.get('native_max_e_dist'))
        if plan != validated:
            raise FilamentStateError('Preflight plan was modified or has an unknown version')
        if not isinstance(context, dict):
            raise FilamentStateError('Session context must be a dictionary')
        try:
            source = deepcopy(context)
        except Exception as exc:
            raise FilamentStateError('Context must support independent copy') from exc
        owner = source.get('owner_state', 'IDLE')
        if mode == 'CHANGE':
            if owner not in ('PRINTING', 'PAUSING', 'PAUSED'):
                raise FilamentStateError('CHANGE requires a live printing/paused M02 owner')
            _integer(source.get('owner_token'), 'owner_token', 1)
        elif owner not in ('IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR', 'PAUSED'):
            raise FilamentStateError('LOAD/UNLOAD cannot request an automatic job pause')
        if owner == 'PAUSED':
            _integer(source.get('owner_token'), 'owner_token', 1)
        state = 'WAIT_PAUSE' if mode == 'CHANGE' and owner != 'PAUSED' else 'HEATING'
        total_deadline = _deadline(now, validated['profile']['total_timeout'])
        timeout = validated['profile']['move_timeout' if state == 'WAIT_PAUSE' else 'heat_timeout']
        phase_deadline = _deadline(now, timeout)
        # Exact arithmetic prevents mixed directions or float summation from
        # manufacturing extra transport budget. Public values remain floats.
        base_kinds = ('load',) if mode == 'LOAD' else ('unload',) if mode == 'UNLOAD' else ('unload', 'load')
        budget = sum((Fraction(abs(segment['delta_e']))
                      for kind in base_kinds for segment in validated['segments'][kind]), Fraction())
        if mode != 'UNLOAD':
            budget += Fraction(validated['profile']['max_purge_mm'])
        self._token += 1
        self._mode, self._context, self._plan = mode, source, validated
        self._issued = self._completed = Fraction()
        self._budget, self._purge_requests = budget, 0
        self._reheat_wait = None
        self._total_deadline = total_deadline
        self._enter(state, 'start', now, new_deadline=phase_deadline)
        return self._token

    def advance(self, event, token, now, phase_id=None):
        if not self._current(token, phase_id):
            return False
        now = self._time(now)
        if not isinstance(event, str):
            raise FilamentStateError('Event must be a string')
        if (self._state, event) in (('COMPLETE', 'completed'), ('CANCELLED', 'cancelled')):
            return True
        transitions = {
            ('WAIT_PAUSE', 'paused'): 'HEATING',
            ('HEATING', 'heated'): 'WAIT_INSERT' if self._mode == 'LOAD' else 'WAIT_UNLOAD',
            ('WAIT_INSERT', 'inserted'): 'LOADING',
            ('WAIT_UNLOAD', 'unload_confirmed'): 'UNLOADING',
            ('LOADING', 'loaded'): 'WAIT_PURGE',
            ('UNLOADING', 'unloaded'): 'WAIT_INSERT' if self._mode == 'CHANGE' else 'COMPLETING',
            ('WAIT_PURGE', 'purge'): 'PURGING',
            ('PURGING', 'purged'): 'WAIT_PURGE',
            ('WAIT_PURGE', 'finish'): 'COMPLETING',
            ('COMPLETING', 'completed'): 'COMPLETE',
            ('CANCELLING', 'cancelled'): 'CANCELLED',
        }
        if self._state in WAIT_STATES:
            transitions[(self._state, 'reheat')] = 'REHEATING'
        if self._state == 'REHEATING' and self._reheat_wait in WAIT_STATES:
            transitions[('REHEATING', 'heated')] = self._reheat_wait
        target = transitions.get((self._state, event))
        if target is None:
            raise FilamentStateError('Event %s is invalid in %s' % (event, self._state))
        if self._state in TRANSPORT_STATES and (self._pending is not None
                                               or self._index != len(self._segments)):
            raise FilamentStateError('Transport phase still has unacknowledged segments')
        if event == 'purge' and self._purge_requests >= self._plan['max_purge_requests']:
            raise FilamentStateError('Explicit purge budget exhausted')
        timeout = self._phase_timeout(target)
        deadline = None if timeout is None else _deadline(now, timeout)
        if event == 'purge':
            self._purge_requests += 1
        if target == 'REHEATING':
            self._reheat_wait = self._state
        elif self._state == 'REHEATING':
            self._reheat_wait = None
        reason = self._reason if target == 'CANCELLED' else 'completed' if target == 'COMPLETE' else None
        self._enter(target, event, now, reason, deadline)
        return True

    def next_segment(self, token, now):
        if not self._current(token):
            return None
        now = self._time(now)
        if self._state not in TRANSPORT_STATES:
            raise FilamentStateError('Current phase does not issue material segments')
        if self._pending is not None:
            raise FilamentStateError('A native segment is still awaiting drain acknowledgement')
        if self._index == len(self._segments):
            return None
        source = self._segments[self._index]
        amount = Fraction(abs(source['delta_e']))
        if self._issued + amount > self._budget:
            raise FilamentStateError('Absolute material-transport budget exhausted')
        deadline = min(self.deadline, _deadline(now, self._plan['profile']['move_timeout']))
        ideal = Fraction(abs(source['delta_e'])) / Fraction(source['speed'])
        if ideal > Fraction(deadline) - Fraction(now):
            raise FilamentStateError('Remaining time cannot fit the next ideal segment')
        identifier = self._segment_id + 1
        pending = {'id': identifier, 'token': self._token, 'phase_id': self._phase_id,
                   'phase': self._state, 'delta_e': source['delta_e'],
                   'speed': source['speed'], 'deadline': deadline}
        self._segment_id, self._last_now = identifier, now
        self._issued += amount  # Reserve before a native move can be enqueued.
        self._index += 1
        self._pending = pending
        return deepcopy(pending)

    def ack_segment(self, identifier, token, now):
        if not self._current(token):
            return False
        identifier = _integer(identifier, 'segment identifier', 1)
        if identifier <= self._last_ack_id:
            return False
        if self._pending is None or identifier != self._pending['id']:
            raise FilamentStateError('Acknowledgement does not match the outstanding segment')
        now = self._time(now)
        self._completed += Fraction(abs(self._pending['delta_e']))
        self._last_ack_id, self._last_now = identifier, now
        self._pending = None
        return True

    def cancel(self, reason, now):
        now = self._time(now, enforce_deadline=False)
        if self._state in TERMINAL_STATES:
            return None
        if self._state == 'CANCELLING':
            return self._token
        reason = _reason(reason)
        deadline = _deadline(now, self._plan['profile']['move_timeout'])
        self._token += 1
        self._total_deadline = deadline  # New bounded cleanup, not the expired wait.
        self._reheat_wait = None
        self._enter('CANCELLING', 'cancel', now, reason, deadline)
        return self._token

    def fail(self, reason, now):
        now = _finite(now, 'now')
        if self._state == 'FAULT':
            return self._token
        reason = _reason(reason)
        self._token += 1
        self._reheat_wait = None
        self._enter('FAULT', 'fail', now, reason)
        return self._token

    def snapshot(self, include_plan=True):
        # UI polling needs budgets, not a fresh copy of every future segment.
        # Full snapshots retain their original independent-copy contract.
        plan = self.plan if include_plan else {
            'total_budget_mm': self._plan.get('total_budget_mm',0.)}
        return {'state': self._state, 'token': self._token, 'phase_id': self._phase_id,
                'mode': self._mode, 'active': self.active, 'reason': self._reason,
                'context': self.context, 'plan': plan, 'deadline': self.deadline,
                'pending': self.pending, 'issued_mm': self.issued_mm,
                'completed_mm': self.completed_mm, 'remaining_budget': self.remaining_budget,
                'purge_requests': self._purge_requests,
                'purge_requests_remaining': self._plan.get('max_purge_requests', 0) - self._purge_requests,
                'phase_segments_remaining': len(self._segments) - self._index,
                'reheat_return_state': self._reheat_wait,
                'history': self.history, 'automatic_resume': False}
