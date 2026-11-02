# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure M04 five-point/three-screw observation state machine (millimetres)."""
import copy
import math
import statistics
import uuid

POINTS = ((269., 44.), (35., 44.), (150., 158.), (269., 275.), (35., 275.))
CORNER_ORDER = (0, 1, 4, 3)
TERMINAL = {'IDLE', 'COMPLETE', 'CANCELLED', 'FAULT'}


class CalibrationError(ValueError):
    pass


def finite(value, name, minimum=None, maximum=None):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or (minimum is not None and value < minimum)
            or (maximum is not None and value > maximum)):
        raise CalibrationError('invalid ' + name)
    return float(value)


def screw_instruction(delta, pitch, positive_direction):
    delta = finite(delta, 'deviation')
    pitch = finite(pitch, 'screw pitch', .01, 10.)
    if positive_direction not in ('CW', 'CCW'):
        raise CalibrationError('screw direction must be explicitly CW or CCW')
    turns = math.ceil(4. * abs(delta) / pitch) / 4.
    direction = positive_direction if delta > 0 else ('CCW' if positive_direction == 'CW' else 'CW')
    return dict(delta_mm=delta, turns=turns, direction=direction)


class CalibrationState:
    def __init__(self, samples=3, sample_spread=.05, center_tolerance=None,
                 screw_pitch=None, directions=None, max_adjustments=40):
        if type(samples) is not int or samples not in (1, 3, 5, 7, 9):
            raise CalibrationError('samples must be one of 1,3,5,7,9')
        self.samples = samples
        self.sample_spread = finite(sample_spread, 'sample spread', 0., 1.)
        self.center_tolerance = center_tolerance
        self.screw_pitch = screw_pitch
        self.directions = directions or {}
        if type(max_adjustments) is not int or not 1 <= max_adjustments <= 40:
            raise CalibrationError('max_adjustments must be 1..40')
        self.max_adjustments = max_adjustments
        self.state, self.token, self.phase_id, self.reason = 'IDLE', '', 0, ''
        self.started = self.phase_started = None
        self.initial, self.current, self.history, self.corrections = {}, {}, [], []
        self.queue, self.stage, self.reference, self.instruction = [], '', None, None

    @property
    def active(self):
        return self.state not in TERMINAL

    def _phase(self, state, now):
        self.state = state
        self.phase_id += 1
        self.phase_started = now

    def validate_profile(self):
        finite(self.center_tolerance, 'center tolerance', 0., 5.)
        finite(self.screw_pitch, 'screw pitch', .01, 10.)
        if set(self.directions) != {'rear_left', 'rear_right', 'front'}:
            raise CalibrationError('all three screw directions must be explicit')
        if any(v not in ('CW', 'CCW') for v in self.directions.values()):
            raise CalibrationError('screw directions must be CW/CCW')

    def start(self, now):
        if self.active or self.state == 'FAULT':
            raise CalibrationError('calibration busy or latched fault')
        self.validate_profile()
        self.token = uuid.uuid4().hex
        self.reason, self.initial, self.current = '', {}, {}
        self.history, self.corrections, self.queue = [], [], []
        self.reference = self.instruction = None
        self.stage, self.started = 'prepare', now
        self._phase('WAIT_PREPARE', now)
        return self.token

    def check(self, token, phase=None):
        if not self.active or token != self.token or (phase is not None and phase != self.phase_id):
            raise CalibrationError('stale/inactive calibration session or phase')

    def confirm(self, token, phase, now):
        self.check(token, phase)
        if self.state == 'WAIT_PREPARE':
            self._phase('HEATING', now)
            return 'HEAT'
        if self.state == 'ADJUST':
            self.stage = self.instruction['screw']
            self.queue = list(self.instruction['point_ids'])
            self.instruction = None
            self._phase('PROBING', now)
            return 'PROBE'
        if self.state == 'REVIEW':
            return 'COMMIT'
        raise CalibrationError('this phase does not accept confirmation')

    def heated(self, token, now):
        self.check(token)
        if self.state != 'HEATING':
            raise CalibrationError('not heating')
        self.stage, self.queue = 'initial', list(CORNER_ORDER)
        self._phase('PROBING', now)

    @property
    def next_point(self):
        return self.queue[0] if self.state == 'PROBING' and self.queue else None

    def measured(self, token, phase, point_id, samples, now):
        self.check(token, phase)
        if type(point_id) is not int or point_id != self.next_point:
            raise CalibrationError('unexpected point ID')
        if len(samples) != self.samples:
            raise CalibrationError('incomplete sample series')
        values = [finite(v, 'sample', -1000, 1000) for v in samples]
        if max(values) - min(values) > self.sample_spread:
            raise CalibrationError('probe sample spread exceeded')
        result = dict(point_id=point_id, median_mm=statistics.median(values), samples_mm=values)
        self.current[point_id] = result
        self.history.append([point_id, values])
        if self.stage == 'initial':
            self.initial[point_id] = copy.deepcopy(result)
        self.queue.pop(0)
        if self.queue:
            self._phase('PROBING', now)
            return
        if self.stage == 'initial':
            self.reference = max(self.initial[p]['median_mm'] for p in CORNER_ORDER)
        if self.stage == 'center':
            delta = self.current[2]['median_mm'] - self.reference
            if abs(delta) > self.center_tolerance:
                raise CalibrationError('center deviation exceeds explicit center_tolerance')
            self._phase('REVIEW', now)
            return
        self._assess(now)

    def _assess(self, now):
        deviations = {p: self.current[p]['median_mm'] - self.reference for p in CORNER_ORDER}
        # Median millimetres are deliberate; no old raw-count truncation or
        # constant 1/800 display scaling is applied to new measurements.
        for name, delta, ids, accepted in (
                ('rear_left', deviations[4], (4, 3), -.2 <= deviations[4] <= .1),
                ('rear_right', deviations[3], (4, 3), -.2 <= deviations[3] <= .1),
                ('front', (deviations[0]+deviations[1])*.5, (0, 1),
                 -.2 < (deviations[0]+deviations[1])*.5 < .1)):
            if not accepted:
                if len(self.corrections) >= self.max_adjustments:
                    raise CalibrationError('maximum screw instructions reached')
                self.instruction = screw_instruction(delta, self.screw_pitch,
                                                     self.directions[name])
                self.instruction.update(screw=name, point_ids=list(ids))
                self.corrections.append(copy.deepcopy(self.instruction))
                self._phase('ADJUST', now)
                return
        self.stage, self.queue = 'center', [2]
        self._phase('PROBING', now)

    def observation(self, identity, geometry):
        if self.state != 'REVIEW' or len(self.current) != 5:
            raise CalibrationError('only a complete REVIEW can be committed')
        return dict(valid=True, method='CONTACT_MEDIAN_FIVE_POINTS', units='mm',
                    identity=copy.deepcopy(identity), session_token=self.token,
                    reference_mm=self.reference,
                    initial_points=[copy.deepcopy(self.initial[p]) for p in CORNER_ORDER],
                    final_points=[copy.deepcopy(self.current[p]) for p in range(5)],
                    deltas_mm=[self.current[p]['median_mm']-self.reference for p in range(5)],
                    corrections=copy.deepcopy(self.corrections),
                    samples_history=copy.deepcopy(self.history), geometry=copy.deepcopy(geometry))

    def complete(self, token, phase, now):
        self.check(token, phase)
        if self.state != 'REVIEW':
            raise CalibrationError('commit requires REVIEW')
        self._phase('COMPLETE', now)

    def terminate(self, reason, now, fault=False):
        self.reason = str(reason)
        self.queue, self.instruction = [], None
        self._phase('FAULT' if fault else 'CANCELLED', now)

    def get_status(self):
        prompts = {'WAIT_PREPARE': 'Clean nozzle and conductive pads; prepare screws; confirm.',
                   'HEATING': 'Heating nozzle; do not touch.',
                   'PROBING': 'Measuring platform; keep clear.',
                   'ADJUST': 'Adjust indicated screw, then confirm.',
                   'REVIEW': 'Review five deviations; confirm to save observation.'}
        return dict(state=self.state, session_token=self.token, phase_id=self.phase_id,
                    active=self.active, reason=self.reason,
                    prompt=prompts.get(self.state, self.state),
                    point_id=self.next_point, instruction=copy.deepcopy(self.instruction),
                    reference_mm=self.reference, corrections=len(self.corrections),
                    review=([self.current[p]['median_mm']-self.reference for p in range(5)]
                            if len(self.current) == 5 and self.reference is not None else None))
