# SPDX-License-Identifier: GPL-3.0-or-later
"""M07 M300 five-point, three-screw workflow; no printer or hardware imports.

The arithmetic/ordering contract is M300_STOCK_LEVELING_V1. Acquisition uses
bounded native contact moves, repeated samples and explicit commits in the
adapter. Those safety/persistence policies are additions to the stock loop.
"""
import copy
import math
import statistics
import struct

from .m300_calibration_state import (CalibrationState, CalibrationError,
                                     CORNER_ORDER, POINTS, finite)

CONTRACT = 'M300_STOCK_LEVELING_V1'
METHOD = 'M300_STOCK_FIVE_POINT_V1'
WORKFLOW = 'M07_STOCK'
STOCK_COEFFICIENT = struct.unpack('<f', bytes.fromhex('5c8f023f'))[0]
SCREWS = ('rear_left', 'rear_right', 'front')
RAW_EPSILON = 1.e-6  # representation roundoff in counts, not a physical tolerance


def _raw(value):
    if type(value) is not int or not -(2**31) < value < 2**31:
        raise CalibrationError('raw contact count must be a bounded signed integer')
    return value


def _scale(value):
    if type(value) is not int or value not in (400, 800):
        raise CalibrationError('stock_steps_per_mm must be explicitly 400 or 800')
    return value


def stock_front_delta(d0_raw, d1_raw):
    total = _raw(d0_raw) + _raw(d1_raw)
    return total // 2 if total >= 0 else -((-total) // 2)


def stock_rear_accepted(delta_raw, steps_per_mm):
    d, s = _raw(delta_raw), _scale(steps_per_mm)
    return -s // 5 <= d <= s // 10


def stock_front_accepted(delta_raw, steps_per_mm):
    d, s = _raw(delta_raw), _scale(steps_per_mm)
    return -s // 5 < d < s // 10


def stock_screw_turns(delta_raw, steps_per_mm):
    d, s = _raw(delta_raw), _scale(steps_per_mm)
    # Stock promotes its binary32 coefficient to double. Preserve the literal
    # and operation order: an ideal decimal 0.51 changes quarter-turn edges.
    return math.ceil(((abs(d) / float(s)) / STOCK_COEFFICIENT) * 4.) / 4.


def _count(value, scale):
    v = finite(value, 'sample', -1000., 1000.) * _scale(scale)
    count = round(v)
    if abs(v - count) > RAW_EPSILON:
        raise CalibrationError('sample does not lie on the qualified stock Z count grid')
    return _raw(count)


class LevelingState(CalibrationState):
    """Same adapter protocol as M04, with independently versioned M300 math."""
    workflow, contract_version = WORKFLOW, CONTRACT

    def __init__(self, samples=3, sample_spread=.05, center_tolerance=None,
                 screw_pitch=None, directions=None, max_adjustments=40,
                 stock_steps_per_mm=None, max_sample_retries=2):
        super().__init__(samples, sample_spread, center_tolerance,
                         screw_pitch, directions, max_adjustments)
        if stock_steps_per_mm is not None:
            _scale(stock_steps_per_mm)
        if type(max_sample_retries) is not int or not 0 <= max_sample_retries <= 10:
            raise CalibrationError('max_sample_retries must be 0..10 per session')
        self.stock_steps_per_mm = stock_steps_per_mm
        self.max_sample_retries = max_sample_retries
        self._reset_m07()

    def _reset_m07(self):
        self.reference_raw = None
        self.pair_cursor = 5
        self.pending_instructions = []
        self.retry_count, self.rejected_samples = 0, []
        self.events = []
        self.rear_accepted = self.front_accepted = False

    def validate_profile(self):
        _scale(self.stock_steps_per_mm)
        if self.center_tolerance is not None:
            finite(self.center_tolerance, 'optional center safety tolerance', 0., 5.)
        if self.screw_pitch is not None:
            pitch = finite(self.screw_pitch, 'stock coefficient alias', .01, 10.)
            if struct.unpack('<f', struct.pack('<f', pitch))[0] != STOCK_COEFFICIENT:
                raise CalibrationError('M07 uses the stock 0.51 coefficient; screw_pitch cannot change it')
        if set(self.directions) != set(SCREWS) or any(
                value != 'CCW' for value in self.directions.values()):
            raise CalibrationError('M07 stock positive directions must explicitly be CCW for all three screws')

    def start(self, now):
        token = super().start(now)
        self._reset_m07()
        return token

    def confirm(self, token, phase, now):
        self.check(token, phase)
        if self.state == 'ADJUST':
            if self.pending_instructions and len(self.corrections) >= self.max_adjustments:
                self.terminate('maximum screw instructions reached', now, fault=True)
                raise CalibrationError(self.reason)
            self.events.append({'kind': 'confirm_adjustment',
                                'instruction_index': len(self.corrections)-1})
            if self.pending_instructions:
                self._issue(self.pending_instructions.pop(0), now)
                return 'INSTRUCT'
            self.instruction = None
            rear = self.stage == 'rear'
            first = (4 if rear else 1) if self.pair_cursor in (1, 4) else (3 if rear else 0)
            second = (3 if first == 4 else 4) if rear else (0 if first == 1 else 1)
            self.queue = [first, second]
            self.pair_cursor = second
            self._phase('PROBING', now)
            return 'PROBE'
        if self.state == 'WAIT_RETRY':
            self.events.append({'kind': 'confirm_retry', 'point_id': self.queue[0]})
            self._phase('PROBING', now)
            return 'PROBE'
        return super().confirm(token, phase, now)

    def measured(self, token, phase, point_id, samples, now):
        self.check(token, phase)
        if type(point_id) is not int or point_id != self.next_point:
            raise CalibrationError('unexpected point ID')
        if not isinstance(samples, (list, tuple)) or len(samples) != self.samples:
            raise CalibrationError('incomplete sample series')
        values = [finite(v, 'sample', -1000., 1000.) for v in samples]
        raw = [_count(v, self.stock_steps_per_mm) for v in values]
        if max(values)-min(values) > self.sample_spread + RAW_EPSILON/self.stock_steps_per_mm:
            self.retry_count += 1
            self.rejected_samples.append({'point_id': point_id, 'samples_mm': values,
                                          'reason': 'sample_spread'})
            self.events.append({'kind': 'rejected_measurement', 'point_id': point_id,
                                'samples_mm': values})
            if self.retry_count > self.max_sample_retries:
                raise CalibrationError('maximum sample retries reached')
            self._phase('WAIT_RETRY', now)
            return
        median_raw = int(statistics.median(raw))
        result = dict(point_id=point_id, median_mm=median_raw/self.stock_steps_per_mm,
                      median_raw=median_raw, samples_mm=values, samples_raw=raw)
        self.current[point_id] = result
        self.history.append([point_id, values])
        self.events.append({'kind': 'measurement', 'point_id': point_id, 'samples_mm': values})
        if self.stage == 'initial':
            self.initial[point_id] = copy.deepcopy(result)
        self.queue.pop(0)
        if self.queue:
            self._phase('PROBING', now)
            return
        if self.stage == 'initial':
            self.reference_raw = max(self.initial[p]['median_raw'] for p in CORNER_ORDER)
            self.reference = self.reference_raw/self.stock_steps_per_mm
            self.stage = 'rear'
        if self.stage == 'rear':
            self._assess_rear(now)
        elif self.stage == 'front':
            self._assess_front(now)
        elif self.stage == 'center':
            self._validate_complete()
            self._phase('REVIEW', now)
        else:
            raise CalibrationError('unexpected measurement stage')

    def _delta(self, point_id):
        return self.current[point_id]['median_raw'] - self.reference_raw

    def _instruction(self, screw, delta):
        return dict(screw=screw, delta_raw=delta,
                    delta_mm=delta/self.stock_steps_per_mm,
                    turns=stock_screw_turns(delta, self.stock_steps_per_mm),
                    direction='CCW' if delta > 0 else 'CW',
                    action='TIGHTEN' if delta > 0 else 'LOOSEN',
                    point_ids=[4, 3] if screw != 'front' else [0, 1],
                    source_measurements=len(self.history))

    def _issue(self, instruction, now):
        if len(self.corrections) >= self.max_adjustments:
            self.terminate('maximum screw instructions reached', now, fault=True)
            raise CalibrationError(self.reason)
        self.instruction = copy.deepcopy(instruction)
        self.corrections.append(copy.deepcopy(instruction))
        self._phase('ADJUST', now)

    def _assess_rear(self, now):
        instructions = [self._instruction(name, self._delta(point))
                        for name, point in (('rear_left', 4), ('rear_right', 3))
                        if not stock_rear_accepted(self._delta(point), self.stock_steps_per_mm)]
        if instructions:
            self.pending_instructions = instructions[1:]
            self._issue(instructions[0], now)
            return
        self.rear_accepted = True
        self.stage = 'front'
        self._assess_front(now)

    def _assess_front(self, now):
        delta = stock_front_delta(self._delta(0), self._delta(1))
        if not stock_front_accepted(delta, self.stock_steps_per_mm):
            self._issue(self._instruction('front', delta), now)
            return
        self.front_accepted = True
        self.stage, self.queue = 'center', [2]
        self._phase('PROBING', now)

    def _validate_complete(self):
        if (set(self.initial) != set(CORNER_ORDER) or set(self.current) != set(range(5))
                or not self.rear_accepted or not self.front_accepted or self.queue
                or self.pending_instructions or self.instruction is not None
                or self.reference_raw != max(self.initial[p]['median_raw'] for p in CORNER_ORDER)):
            raise CalibrationError('incomplete five-point leveling cannot be committed')
        for point in (4, 3):
            if not stock_rear_accepted(self._delta(point), self.stock_steps_per_mm):
                raise CalibrationError('rear result is not accepted')
        if not stock_front_accepted(stock_front_delta(self._delta(0), self._delta(1)),
                                    self.stock_steps_per_mm):
            raise CalibrationError('front result is not accepted')
        if (self.center_tolerance is not None and
                abs(self._delta(2)/self.stock_steps_per_mm) > self.center_tolerance):
            raise CalibrationError('center deviation exceeds explicit port safety tolerance')

    def observation(self, identity, geometry):
        if self.state != 'REVIEW':
            raise CalibrationError('only a complete REVIEW can be committed')
        self._validate_complete()
        result = super().observation(identity, geometry)
        # Store each sample series once. The ordered ledger references the
        # immutable accepted/rejected series instead of duplicating their
        # floating-point representations and exceeding the NVM record budget.
        events, sample_index, retry_index = [], 0, 0
        for event in self.events:
            if event['kind'] == 'measurement':
                events.append({'kind': 'measurement', 'sample_index': sample_index})
                sample_index += 1
            elif event['kind'] == 'rejected_measurement':
                events.append({'kind': 'rejected_measurement', 'retry_index': retry_index})
                retry_index += 1
            else:
                events.append(copy.deepcopy(event))
        result.update(method=METHOD, workflow=WORKFLOW, contract_version=CONTRACT,
                      reference_raw=self.reference_raw,
                      deltas_raw=[self._delta(p) for p in range(5)],
                      stock_steps_per_mm=self.stock_steps_per_mm,
                      stock_coefficient=STOCK_COEFFICIENT,
                      sample_count=self.samples, sample_spread=self.sample_spread,
                      max_adjustments=self.max_adjustments,
                      max_sample_retries=self.max_sample_retries,
                      center_tolerance=self.center_tolerance,
                      center_policy='REPORT_ONLY' if self.center_tolerance is None else 'EXPLICIT_PORT_LIMIT',
                      retry_count=self.retry_count, rejected_samples=copy.deepcopy(self.rejected_samples),
                      events=events,
                      stock_rechecks_rear_after_front=False)
        return result

    def terminate(self, reason, now, fault=False):
        if self.state == 'FAULT':
            return
        self.pending_instructions = []
        super().terminate(reason, now, fault)

    def get_status(self):
        result = super().get_status()
        result.update(workflow=WORKFLOW, contract_version=CONTRACT,
                      stock_steps_per_mm=self.stock_steps_per_mm,
                      stock_coefficient=STOCK_COEFFICIENT,
                      reference_raw=self.reference_raw,
                      retry_count=self.retry_count, max_sample_retries=self.max_sample_retries,
                      max_adjustments=self.max_adjustments,
                      pending_instructions=len(self.pending_instructions),
                      center_policy='REPORT_ONLY' if self.center_tolerance is None else 'EXPLICIT_PORT_LIMIT')
        if self.state == 'WAIT_RETRY':
            result['prompt'] = 'Samples disagree. Check nozzle/pad; confirm to repeat this point.'
            result['point_id'] = self.queue[0]
        return result


def validate_observation(record):
    """Replay the complete event ledger before accepting a stored M07 record.

    A checksum alone cannot establish completeness or consistent medians. No
    hardware is touched and no serialized live control state is restored.
    """
    try:
        if (not isinstance(record, dict) or record.get('method') != METHOD
                or record.get('workflow') != WORKFLOW or record.get('contract_version') != CONTRACT
                or not isinstance(record.get('events'), list) or len(record['events']) > 160):
            raise CalibrationError('unsupported/incomplete M07 observation')
        machine = LevelingState(samples=record['sample_count'], sample_spread=record['sample_spread'],
                                center_tolerance=record['center_tolerance'],
                                directions={s: 'CCW' for s in SCREWS},
                                max_adjustments=record['max_adjustments'],
                                stock_steps_per_mm=record['stock_steps_per_mm'],
                                max_sample_retries=record['max_sample_retries'])
        machine.start(0.)
        machine.token = record['session_token']
        machine.confirm(machine.token, machine.phase_id, 0.)
        machine.heated(machine.token, 0.)
        for event in record['events']:
            if not isinstance(event, dict):
                raise CalibrationError('invalid M07 event')
            kind = event.get('kind')
            if kind == 'measurement':
                index = event.get('sample_index')
                if type(index) is not int or not 0 <= index < len(record['samples_history']):
                    raise CalibrationError('invalid M07 sample series reference')
                point_id, samples = record['samples_history'][index]
                machine.measured(machine.token, machine.phase_id, point_id, samples, 0.)
            elif kind == 'rejected_measurement':
                index = event.get('retry_index')
                if type(index) is not int or not 0 <= index < len(record['rejected_samples']):
                    raise CalibrationError('invalid M07 rejected series reference')
                sample = record['rejected_samples'][index]
                machine.measured(machine.token, machine.phase_id, sample['point_id'], sample['samples_mm'], 0.)
            elif kind == 'confirm_adjustment' and machine.state == 'ADJUST':
                machine.confirm(machine.token, machine.phase_id, 0.)
            elif kind == 'confirm_retry' and machine.state == 'WAIT_RETRY':
                machine.confirm(machine.token, machine.phase_id, 0.)
            else:
                raise CalibrationError('inconsistent M07 event order')
        expected = machine.observation(record['identity'], record['geometry'])
        # Exact canonical serialization also separates bool/int and disallows
        # forged extra fields, while finite noise remains original evidence.
        import json
        canonical = lambda v: json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if canonical(record) != canonical(expected):
            raise CalibrationError('M07 observation does not match its complete measurement/confirmation ledger')
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise CalibrationError('invalid M07 observation: ' + str(exc)) from exc
