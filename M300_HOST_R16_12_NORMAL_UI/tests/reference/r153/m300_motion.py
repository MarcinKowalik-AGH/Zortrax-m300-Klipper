# SPDX-License-Identifier: GPL-3.0-or-later
"""M300 bounded initial homing and encoder/deadman Z motion.

The one native PC7 probe is reused. HomingMove owns MCU endstop stopping;
temporary native homing coordinates are private to an exclusive operation.
No raw steps, force_move, SET_KINEMATIC_POSITION or automatic ARM is used.
Qualification flags describe a separately measured allowed starting envelope;
they cannot establish clearance from an arbitrary unknown physical position.
"""
import json
import logging
import math

VERSION = '0.6.0-LAB_M01_M02_M03_M04_M05_M06'
PERIOD = .05
EPS = 1.e-6
XY_CLEARANCE_MIN = 5.
XY_CLEARANCE_MAX_AGE = 60.
GEOMETRY = ('x_search_distance', 'y_search_distance', 'z_search_distance',
            'z_initial_release_distance', 'z_release_distance',
            'initial_clearance_distance', 'initial_travel_limit')
PANEL_COUNTERS = ('sequence', 'position', 'presses', 'releases', 'shorts',
                  'longs', 'invalid')
IDLE_JOB = ('IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR')
PEERS = ('m300_filament', 'm300_calibration', 'm300_maintenance',
         'm300_sd', 'm300_nvm', 'm300_fans', 'm300_thermal')


class _CompletedRetractContactError(Exception):
    """Contact validation failed after a completed, drained native retract."""


def finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def axes_spec(value):
    """Explicit axes only; neither numeric G28 parameters nor silent typos."""
    if not isinstance(value, str) or not value:
        raise ValueError('AXES must contain X, Y and/or Z')
    value = value.lower()
    if any(c not in 'xyz' for c in value) or len(set(value)) != len(value):
        raise ValueError('AXES must contain distinct X, Y and/or Z')
    return ''.join(c for c in 'yxz' if c in value)


def panel_snapshot(value):
    if not isinstance(value, dict):
        raise ValueError('invalid panel snapshot')
    result = {}
    for key in PANEL_COUNTERS:
        item = value.get(key)
        if type(item) is not int or not 0 <= item <= 0xffffffff:
            raise ValueError('invalid panel ' + key)
        result[key] = item
    pressed = value.get('pressed')
    if type(pressed) not in (bool, int) or pressed not in (False, True):
        raise ValueError('invalid panel pressed')
    result['pressed'] = bool(pressed)
    return result


class _HomingToolhead:
    """A phase/token-bound capability given only to the real HomingMove."""
    def __init__(self, owner, axis, target, speed):
        self.owner, self.axis = owner, axis
        self.token, self.phase = owner.token, owner.phase_id
        self.start, self.target = owner.toolhead.get_position(), list(target)
        self.speed, self.used = speed, False

    def __getattr__(self, name):
        return getattr(self.owner.toolhead, name)

    def _check(self):
        self.owner._check_live(self.token, self.phase)

    def drip_move(self, position, speed, completion):
        self._check()
        if self.used or list(position) != self.target or speed != self.speed:
            raise self.owner._error('unexpected native homing move')
        self.used = True
        return self.owner._native_drip(list(position), speed, completion)

    def set_position(self, position, *args, **kwargs):
        self._check()
        p = list(position)
        if (args or kwargs or len(p) != 4 or not all(finite(v) for v in p)
                or any(abs(p[i]-self.start[i]) > EPS for i in range(4) if i != self.axis)
                or not min(self.start[self.axis], self.target[self.axis])-EPS
                <= p[self.axis] <= max(self.start[self.axis], self.target[self.axis])+EPS):
            raise self.owner._error('native homing returned an out-of-envelope position')
        self.owner._set_native(p)
        self._check()


class M300Motion:
    def __init__(self, config):
        self.config, self.printer = config, config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.job = self.printer.load_object(config, 'm300_job')
        self.board = self.job.board
        self.qualified = config.getboolean('qualified', False)
        self.unknown_z_qualified = config.getboolean('unknown_z_qualified', False)
        self.initial_xy_clearance_qualified = config.getboolean('initial_xy_clearance_qualified', False)
        self.jog_qualified = config.getboolean('jog_qualified', False)
        self.production_control = config.getboolean('production_control', False)
        self.production_e_velocity = self._option('production_e_velocity', 45., .001, 45.)
        self.production_e_accel = self._option('production_e_accel', 4000., .001, 4000.)
        self.production_retract_accel = self._option('production_retract_accel', 2000., .001, 2000.)
        self.xy_test_mode = config.getboolean('xy_test_mode', False)
        self.z_contact_test_mode = config.getboolean('z_contact_test_mode', False)
        self.native_xy_control = config.getboolean('native_xy_control', False)
        self.z_contact_clearance = self._option('z_contact_clearance', None, 5., 10.)
        self.xy_jog_moves = 0
        self._xy_axes = None
        self._xy_clearance = self._xy_clearance_at = None
        raw_xy = config.get('home_xy', None)
        self.home_xy = None
        if raw_xy is not None:
            try:
                self.home_xy = tuple(float(v.strip()) for v in raw_xy.split(','))
                if len(self.home_xy) != 2 or not all(finite(v) for v in self.home_xy):
                    raise ValueError()
            except (ValueError, AttributeError):
                raise config.error('M300 motion home_xy requires two finite coordinates')
        for name in GEOMETRY + ('jog_step', 'jog_max_distance'):
            setattr(self, name, self._option(name, None, .000001, 1000.))
        self.travel_speed = self._option('travel_speed', 10., .001, 200.)
        self.z_speed = self._option('z_speed', .5, .001, 10.)
        self.release_speed = self._option('release_speed', .5, .001, 10.)
        self.jog_speed = self._option('jog_speed', .5, .001, 10.)
        self.move_timeout = self._option('move_timeout', 60., .05, 3600.)
        self.total_timeout = self._option('total_timeout', 300., .1, 7200.)
        self.jog_timeout = self._option('jog_timeout', 30., .1, 600.)
        self.panel_timeout = self._option('panel_timeout', .5, .05, 2.)
        self._require_options()
        self.ready = self.installed = self._executing = self.native_active = False
        self.state, self.phase, self.reason = 'IDLE', 'IDLE', ''
        self.token = self.phase_id = 0
        self.result = None
        self.last_rejection = ''
        self._owner_job = self._owner_job_token = None
        self._temporary = self._setting_position = False
        self._deadline = self._move_deadline = None
        self._session_started = None
        self._move_permit = None
        self._fault_shutdown_requested = False
        self._native_move = self._native_drip = self._native_set_position = None
        self.toolhead = self.kin = self.gcode_move = self.endstop = self.probe = None
        self.initial_travel = self.jog_travel = 0.
        self._panel = self._panel_time = None
        self._pending_detents = 0
        self._panel_residual = 0
        self._steps_per_detent, self._encoder_reverse = 4, False
        self._timer = self.reactor.register_timer(self._tick)
        self._watch_timer = self.reactor.register_timer(self._watchdog)
        self.board.get_mcu().register_config_callback(self._audit_config)
        for name, callback in (('klippy:connect', self._connect),
                               ('klippy:ready', self._ready),
                               ('klippy:shutdown', self._lifecycle),
                               ('klippy:disconnect', self._lifecycle),
                               ('gcode:request_restart', self._lifecycle),
                               ('stepper_enable:motor_off', self._motor_off),
                               ('homing:home_rails_begin', self._foreign_home)):
            self.printer.register_event_handler(name, callback)
        for name, callback in (('ZORTRAX_HOME', self.cmd_home),
                               ('ZORTRAX_MOTION_CANCEL', self.cmd_cancel),
                               ('ZORTRAX_Z_JOG', self.cmd_jog),
                               ('ZORTRAX_Z_JOG_STOP', self.cmd_cancel)):
            self.gcode.register_command(name, callback)
        self.gcode.register_command('ZORTRAX_MOTION_STATUS', self.cmd_status,
                                     when_not_ready=True)
        self.gcode.register_command('ZORTRAX_XY_ARM', self.cmd_xy_arm)

    def _error(self, text):
        text = str(text)
        if not text.startswith('M300 motion: '):
            text = 'M300 motion: ' + text
        return self.printer.command_error(text)

    def _shutdown_cause(self):
        # This check must precede the session check: the MCU shutdown handler
        # revoked our token while a native HomingMove was still unwinding.
        if not self.printer.is_shutdown():
            return None
        try:
            state = self.printer.get_state_message()
            message = state[0] if isinstance(state, tuple) else state
            cause = str(message).splitlines()[0].strip()
        except Exception:
            cause = ''
        return cause or 'firmware shutdown (see the Klippy log)'

    def _option(self, name, default, low, high):
        value = self.config.getfloat(name, default, minval=low, maxval=high)
        if value is not None and not finite(value):
            raise self.config.error('M300 motion %s must be finite' % name)
        return value

    def _require_options(self):
        if self.production_control:
            if any((self.xy_test_mode, self.z_contact_test_mode, self.native_xy_control)):
                raise self.config.error('production_control and commissioning modes are mutually exclusive')
            for name in ('home_xy',) + GEOMETRY + ('z_contact_clearance', 'jog_step', 'jog_max_distance'):
                if getattr(self, name) is None:
                    raise self.config.error('M300 production_control requires explicit '+name)
            if self.jog_step > self.jog_max_distance:
                raise self.config.error('jog_step exceeds jog_max_distance')
            if self.z_initial_release_distance+self.initial_clearance_distance > self.initial_travel_limit+EPS:
                raise self.config.error('initial_travel_limit must cover release plus clearance')
        if (self.z_contact_test_mode or self.native_xy_control) and not self.xy_test_mode:
            raise self.config.error('M300 contact/jog commissioning requires xy_test_mode=True')
        if self.z_contact_test_mode:
            for name in ('home_xy', 'z_search_distance', 'z_release_distance', 'z_contact_clearance'):
                if getattr(self, name) is None:
                    raise self.config.error('M300 z_contact_test_mode requires explicit '+name)
        if self.xy_test_mode:
            if any((self.qualified, self.unknown_z_qualified,
                    self.initial_xy_clearance_qualified, self.jog_qualified)):
                raise self.config.error('M300 xy_test_mode requires full qualification flags False')
            for name in ('x_search_distance', 'y_search_distance'):
                if getattr(self, name) is None:
                    raise self.config.error('M300 xy_test_mode requires explicit ' + name)
        if self.jog_qualified and not self.qualified:
            raise self.config.error('M300 motion jog_qualified requires qualified=True')
        if self.qualified:
            for name in ('home_xy',) + GEOMETRY:
                if getattr(self, name) is None:
                    raise self.config.error('M300 motion qualified requires explicit ' + name)
            if self.z_initial_release_distance + self.initial_clearance_distance > self.initial_travel_limit + EPS:
                raise self.config.error('M300 motion initial_travel_limit must cover release plus clearance')
        if self.jog_qualified:
            for name in ('jog_step', 'jog_max_distance'):
                if getattr(self, name) is None:
                    raise self.config.error('M300 motion jog_qualified requires explicit ' + name)
            if self.jog_step > self.jog_max_distance:
                raise self.config.error('M300 motion jog_step exceeds jog_max_distance')

    def _bind(self):
        self.job._bind_resources()
        self.toolhead, self.gcode_move = self.job.toolhead, self.job.gcode_move
        self.kin = self.toolhead.get_kinematics()
        self.probe = self.printer.lookup_object('probe')
        self.endstop = getattr(getattr(self.probe, 'mcu_probe', None), 'mcu_endstop', None)
        if self.endstop is None or not callable(getattr(self.kin, 'clear_homing_state', None)):
            raise self.config.error('M300 motion requires pinned native PC7 probe and Cartesian homing state')

    def _audit_config(self):
        self._bind()
        pcfg = self.config.getsection('probe')
        for option in ('activate_gcode', 'deactivate_gcode'):
            if pcfg.get(option, '').strip():
                raise self.config.error('M300 fixed contact requires empty probe ' + option)
        if any(self.probe.get_offsets()[i] != 0. for i in (0, 1)):
            raise self.config.error('M300 nozzle contact requires zero native XY probe offsets')
        if self.qualified:
            try:
                self._profile()
            except self.printer.command_error as exc:
                raise self.config.error(str(exc))
        if self.production_control:
            try:
                self._production_profile()
            except self.printer.command_error as exc:
                raise self.config.error(str(exc))
        if self.xy_test_mode:
            try:
                self._xy_profile()
                if self.z_contact_test_mode:
                    self._z_contact_profile()
            except self.printer.command_error as exc:
                raise self.config.error(str(exc))

    def _xy_profile(self):
        if (not self.xy_test_mode or self.qualified or self.board.gates not in (1, 3)
                or not self.board.allow_actuators or not self.board.allow_motion
                or bool(self.board.gates & 2) != bool(self.board.allow_heating)):
            raise self._error('XY test requires motion permission; heating remains independent')
        lo, hi = self._bounds()
        rails = getattr(self.kin, 'rails', ())
        if len(rails) != 3:
            raise self._error('three native Cartesian rails required')
        for i, axis in enumerate('xy'):
            info = rails[i].get_homing_info()
            search = getattr(self, axis+'_search_distance')
            capacity = abs((lo[i] if info.positive_dir else hi[i])-info.position_endstop)
            if (not finite(search) or not 0. < search <= capacity
                    or not lo[i] <= info.position_endstop <= hi[i]
                    or not all(finite(v) for v in (info.speed, info.retract_speed, info.retract_dist))
                    or not 0. < info.speed <= 2. or not 0. < info.retract_speed <= 2.
                    or not 0. < info.retract_dist <= min(capacity, 2.)
                    or len(rails[i].get_endstops()) != 1):
                raise self._error('invalid bounded XY test profile on '+axis)
        return lo, hi

    def _z_contact_profile(self):
        lo, hi = self._bounds()
        contact = self.probe.get_offsets()[2]
        if (not self.z_contact_test_mode or not self.xy_test_mode or self.qualified
                or self.home_xy is None or not all(lo[i] <= self.home_xy[i] <= hi[i] for i in (0, 1))
                or not finite(contact) or not lo[2] <= contact < hi[2]
                or not finite(self.z_search_distance) or not 0. < self.z_search_distance <= hi[2]-lo[2]
                or not finite(self.z_release_distance) or not 0. < self.z_release_distance <= 2.
                or not finite(self.z_contact_clearance) or not 5. <= self.z_contact_clearance <= 10.
                or contact+self.z_release_distance+self.z_contact_clearance > hi[2]
                or not 0. < self.z_speed <= .5 or not 0. < self.release_speed <= .5
                or not 0. < self.travel_speed <= 10.
                or self.move_timeout < self.z_search_distance/self.z_speed+10.
                or self.total_timeout < self.move_timeout+30.):
            raise self._error('invalid bounded Z contact commissioning profile')
        return lo, hi

    def _production_profile(self):
        # Reuse physical geometry validation, without claiming qualification of
        # the job/filament/calibration/SD workflows. Rates are then checked by
        # native Cartesian kinematics and ToolHead acceleration planning.
        lo, hi = self._profile()
        if (self.board.gates not in (1, 3) or not self.board.allow_actuators
                or not self.board.allow_motion
                or bool(self.board.gates & 2) != bool(self.board.allow_heating)):
            raise self._error('production XYZ requires independent native motion permission')
        self._unknown_z_clearance()
        contact = self.probe.get_offsets()[2]
        if (contact+self.z_release_distance+self.z_contact_clearance > hi[2]
                or not 0. < self.z_speed <= 5. or not 0. < self.release_speed <= 5.
                or self.move_timeout < self.z_search_distance/self.z_speed+10.
                or self.total_timeout < self.move_timeout+30.):
            raise self._error('invalid production contact/travel/time budget')
        return lo, hi

    def _wake_for_motion(self):
        maintenance = self.printer.lookup_object('m300_maintenance', None)
        wake = getattr(maintenance, 'wake_for_operator_motion', None)
        if wake is not None:
            wake()

    def cmd_xy_arm(self, gcmd):
        self._params(gcmd, ('CLEARANCE',))
        if not self.ready or self.printer.is_shutdown() or self.is_busy():
            raise self._error('XY test is not idle and Ready')
        self._production_profile() if self.production_control else self._xy_profile()
        self._wake_for_motion()
        self._peers()
        if not self._empty():
            raise self._error('motion queue must be empty')
        clearance = gcmd.get_float('CLEARANCE', 5. if self.production_control else None)
        if not finite(clearance) or clearance < XY_CLEARANCE_MIN or clearance > 300.:
            raise self._error('CLEARANCE must declare at least 5mm of actual clear XY travel')
        status = self.board.get_status(self.reactor.monotonic())
        if status.get('armed') is True:
            self.board.require_motion()
        else:
            cmd = self.gcode.create_gcode_command('ZORTRAX_ARM', 'ZORTRAX_ARM',
                                                  {'ACK': 'M300_LAB_QUALIFIED'})
            self.board.cmd_arm(cmd)
        self._xy_clearance = float(clearance)
        self._xy_clearance_at = self.reactor.monotonic()
        maintenance = self.printer.lookup_object('m300_maintenance', None)
        if maintenance is not None:
            maintenance.activity()
        if self.production_control:
            gcmd.respond_info('MCU ARM requested/checked; wait for armed=true. Native XYZ/E control; '
                             'no clearance declaration or timed gate. No movement or heating started.')
        elif self.native_xy_control:
            gcmd.respond_info('MCU ARM requested/checked; wait for armed=true. XY uses native '
                             'homing and limits, without a 60s declaration gate. '
                             'Declared 5mm clearance applies to first G28 Z within 60s. '
                             'No movement or heating started.')
        else:
            gcmd.respond_info('Motion ARM/clearance requested; wait for armed=true; '
                             'start G28 X Y within 60s. Heating is independent; '
                             'no movement started by this command.')

    def _bounds(self):
        status = self.kin.get_status(self.reactor.monotonic())
        lo, hi = list(status['axis_minimum'])[:3], list(status['axis_maximum'])[:3]
        if (len(lo) != 3 or len(hi) != 3 or not all(finite(v) for v in lo+hi)
                or any(lo[i] >= hi[i] for i in range(3))):
            raise self._error('invalid native axis bounds')
        return lo, hi

    def _homed(self):
        if self.kin is None:
            return ''
        return self.kin.get_status(self.reactor.monotonic()).get('homed_axes', '')

    def _profile(self):
        self._require_options()
        lo, hi = self._bounds()
        if not all(lo[i] <= self.home_xy[i] <= hi[i] for i in (0, 1)):
            raise self._error('home_xy outside native axis bounds')
        rails = getattr(self.kin, 'rails', ())
        if len(rails) != 3:
            raise self._error('exactly three native Cartesian rails required')
        for i, name in enumerate(('x_search_distance', 'y_search_distance', 'z_search_distance')):
            if getattr(self, name) > hi[i]-lo[i]:
                raise self._error(name + ' exceeds native axis span')
        for i in (0, 1):
            info = rails[i].get_homing_info()
            values = (info.position_endstop, info.speed, info.retract_speed, info.retract_dist)
            if not all(finite(v) for v in values) or min(values[1:]) <= 0.:
                raise self._error('native XY homing speed/retract must be finite and positive')
            away_bound = lo[i] if info.positive_dir else hi[i]
            capacity = abs(away_bound-info.position_endstop)
            if (not lo[i] <= info.position_endstop <= hi[i]
                    or getattr(self, 'xy'[i]+'_search_distance') > capacity
                    or info.retract_dist > capacity):
                raise self._error('native XY search/retract outside axis envelope')
            if len(rails[i].get_endstops()) != 1:
                raise self._error('one native endstop per XY rail required')
        contact_z = self.probe.get_offsets()[2]
        if not finite(contact_z) or not lo[2] <= contact_z < hi[2]:
            raise self._error('qualified native probe z_offset outside Z bounds')
        if (self.z_release_distance > hi[2]-contact_z
                or self.initial_travel_limit > hi[2]-lo[2]):
            raise self._error('Z release/initial_travel_limit outside native Z envelope')
        return lo, hi

    def _connect(self):
        self._bind()
        self._native_move = self.toolhead.move
        self._native_drip = self.toolhead.drip_move
        self._native_set_position = self.toolhead.set_position
        if getattr(self.board, 'native_control', False):
            # Only the M300 contact-homing geometry remains. Native ToolHead,
            # extruder checks and all ordinary G-code handlers stay untouched.
            self.gcode.register_command('G28', None)
            self.gcode.register_command('G28', self.cmd_G28)
            self.installed = True
            return
        def move(position, speed):
            jog = False
            if self.production_control and not self.is_busy() and list(position) != list(self.toolhead.get_position()):
                speed = self._allow_native_move(position, speed)
            if self.xy_test_mode and not self.is_busy() and list(position) != list(self.toolhead.get_position()):
                if not self.native_xy_control:
                    raise self._error('XY test permits only explicit X/Y homing')
                speed = self._allow_xy_jog(position, speed)
                jog = True
            if self.is_busy():
                permit, self._move_permit = self._move_permit, None
                if permit != (self.token, self.phase_id, list(position), speed):
                    raise self._error('exclusive motion owns the toolhead')
                self._guard()
            result = self._native_move(position, speed)
            if jog:
                self.xy_jog_moves += 1
            return result
        self.toolhead.move = move
        for name, original in (('drip_move', self._native_drip),
                               ('set_position', self._native_set_position)):
            def locked(*args, original=original, name=name, **kwargs):
                if self.xy_test_mode and name == 'drip_move':
                    raise self._error('XY test permits only the current native homing capability')
                if self.is_busy():
                    raise self._error('exclusive motion owns native ' + name)
                if name == 'set_position' and (len(args) > 1 and args[1]
                                               or kwargs.get('homing_axes')):
                    raise self._error('homing coordinates require the M06 owner')
                return original(*args, **kwargs)
            setattr(self.toolhead, name, locked)
        if self.production_control:
            extruder = self.toolhead.get_extruder()
            original_check = getattr(extruder, 'check_move', None)
            if not callable(original_check):
                raise self.config.error('production control requires native extruder check_move')
            def checked_extrusion(move, index):
                original_check(move, index)
                self._limit_production_extrusion(move, index)
            extruder.check_move = checked_extrusion
        # Future wrappers may be installed later; capture at connect and
        # rebind the parser at ready as the preserved M04 owners do.
        self._bind_parser()
        self.gcode.register_command('G28', None)
        self.gcode.register_command('G28', self.cmd_G28)
        blocked = ('G0', 'G1', 'G90', 'G91', 'G92', 'M82', 'M83', 'M204',
                   'M220', 'M221', 'SAVE_GCODE_STATE', 'RESTORE_GCODE_STATE',
                   'SET_GCODE_OFFSET', 'SET_KINEMATIC_POSITION', 'FORCE_MOVE',
                   'STEPPER_BUZZ', 'SET_VELOCITY_LIMIT', 'PROBE',
                   'PROBE_ACCURACY', 'PROBE_CALIBRATE', 'Z_OFFSET_APPLY_PROBE',
                   'BED_MESH_CALIBRATE', 'SCREWS_TILT_CALCULATE',
                   'Z_TILT_ADJUST', 'QUAD_GANTRY_LEVEL', 'PID_CALIBRATE',
                   'M109', 'M190', 'TEMPERATURE_WAIT', 'M106', 'M107',
                   'SET_FAN_SPEED', 'SET_EXTRUDER_ROTATION_DISTANCE',
                   'SYNC_EXTRUDER_MOTION', 'SET_STEPPER_ENABLE')
        test_blocked = frozenset(('G0', 'G1', 'G92', 'RESTORE_GCODE_STATE',
            'SET_GCODE_OFFSET', 'SET_KINEMATIC_POSITION', 'FORCE_MOVE', 'STEPPER_BUZZ',
            'PROBE', 'PROBE_ACCURACY', 'PROBE_CALIBRATE', 'Z_OFFSET_APPLY_PROBE',
            'BED_MESH_CALIBRATE', 'SCREWS_TILT_CALCULATE', 'Z_TILT_ADJUST',
            'QUAD_GANTRY_LEVEL', 'SET_EXTRUDER_ROTATION_DISTANCE',
            'SYNC_EXTRUDER_MOTION', 'SET_STEPPER_ENABLE'))
        for name in blocked:
            original = self.gcode.register_command(name, None)
            if original is None:
                continue
            def guarded(gcmd, original=original, name=name):
                native_parser = (self.native_xy_control and
                    (name in ('G0', 'G1', 'G92') or name == 'RESTORE_GCODE_STATE'
                     and gcmd.get_int('MOVE', 0) == 0))
                if self.xy_test_mode and name in test_blocked and not native_parser:
                    raise self._error(name+' is disabled in the XY-only test profile')
                if (self.production_control and name in ('SYNC_EXTRUDER_MOTION', 'SET_STEPPER_ENABLE', 'STEPPER_BUZZ')):
                    raise self._error(name+' bypasses native production motion ownership')
                if self.is_busy() or name in ('SET_KINEMATIC_POSITION', 'FORCE_MOVE'):
                    raise self._error(name + ' is incompatible with bounded motion ownership')
                return original(gcmd)
            self.gcode.register_command(name, guarded)
        for heater in (self.job.hotend, self.job.bed):
            original = heater.set_temp
            def heat(value, original=original):
                thermal = self.printer.lookup_object('m300_thermal', None)
                if self.is_busy() and value != 0. and not getattr(thermal, 'native_control', False):
                    raise self._error('positive heater target while motion owns resources')
                return original(value)
            heater.set_temp = heat
        for name in self.job.steppers.get_steppers():
            self.job.steppers.lookup_enable(name).register_state_callback(self._enable_changed)
        self.printer.lookup_object('webhooks').register_endpoint('m300/motion/cancel', self._web_cancel)
        self.installed = True

    def _limit_production_extrusion(self, move, index):
        # Stock per-axis E ceilings also apply to positive coordinated E.
        # Native max_extrude_only_* intentionally only bounds E-only/retraction.
        ratio = abs(move.axes_r[index])
        if not finite(ratio):
            raise self._error('invalid native extrusion ratio')
        if ratio:
            accel = self.production_retract_accel if move.axes_r[index] < 0. else self.production_e_accel
            move.limit_speed(self.production_e_velocity/ratio, accel/ratio)

    def _allow_native_move(self, position, speed):
        if not self.ready or self.printer.is_shutdown() or not finite(speed) or speed <= 0.:
            raise self._error('native move requires Ready and a finite positive speed')
        if self.board.get_mcu().is_fileoutput():
            raise self._error('FILEOUTPUT has no physical MCU acknowledgement; motion refused')
        self.board.require_motion()
        self._peers()
        if len(position) != 4 or not all(finite(v) for v in position):
            raise self._error('invalid native move position')
        # E-only calibration does not depend on XYZ homing. The preserved
        # native extruder checks can_extrude, max_extrude_only_distance,
        # velocity/acceleration and extrusion cross-section in check_move().
        current = self.toolhead.get_position()
        homed = self._homed()
        for i, axis in enumerate('xyz'):
            if abs(position[i]-current[i]) > EPS and axis not in homed:
                raise self._error('Must home '+axis.upper()+' first')
        return speed

    def _allow_xy_jog(self, position, speed):
        if not self.ready or self.printer.is_shutdown() or not finite(speed) or speed <= 0.:
            raise self._error('XY jog requires Ready and a finite positive speed')
        self._xy_profile()
        self.board.require_motion()
        self._peers()
        current = self.toolhead.get_position()
        if len(position) != 4 or not all(finite(v) for v in position):
            raise self._error('invalid XY jog position')
        if any(abs(position[i]-current[i]) > EPS for i in (2, 3)):
            raise self._error('this stage permits XY jog only; Z uses G28 Z and E is a later stage')
        homed = self._homed()
        for i, axis in enumerate('xy'):
            if abs(position[i]-current[i]) > EPS and axis not in homed:
                raise self._error('Must home '+axis.upper()+' first')
        # Native Cartesian kinematics enforces axis bounds and printer speed /
        # acceleration limits. No additional XY qualification/temperature gate.
        return speed

    def _bind_parser(self):
        if self.gcode_move.move_with_transform == self._native_move:
            self.gcode_move.move_with_transform = self.toolhead.move

    def _ready(self):
        self._bind_parser()
        self.ready = True
        self.reactor.update_timer(self._timer, self.reactor.NOW)
        self.reactor.update_timer(self._watch_timer, self.reactor.NOW)

    def is_busy(self):
        return self.state not in ('IDLE', 'COMPLETE', 'CANCELLED') or self._executing or self.native_active

    def _valid_owner(self):
        return (self._owner_job is self.job and type(self._owner_job_token) is int
                and self.job.machine.token == self._owner_job_token
                and self.job.machine.state == 'HOMING'
                and not self.printer.is_shutdown())

    def owns_job(self, job, token):
        return (self.state == 'HOMING' and job is self._owner_job
                and token == self._owner_job_token and self._valid_owner())

    def _peers(self):
        now = self.reactor.monotonic()
        status = self.job.get_status(now)
        if self._owner_job is not None:
            if not self._valid_owner():
                raise self._error('owning job token/phase changed')
        elif (not isinstance(status, dict) or status.get('busy') is not False
                or status.get('state') not in IDLE_JOB):
            raise self._error('job/file workflow owns resources')
        for name in PEERS:
            peer = self.printer.lookup_object(name, None)
            if peer is None:
                continue
            try:
                value = peer.get_status(now)
            except Exception:
                raise self._error(name + ' status unavailable')
            if (not isinstance(value, dict) or value.get('busy') is not False
                    or not isinstance(value.get('state'), str) or not value['state'].strip()
                    or value['state'].upper() in ('FAULT', 'SLEEP', 'SLEEPING')):
                raise self._error(name + ' owns resources or has invalid status')

    def _guard(self):
        if not self.ready or self.printer.is_shutdown():
            raise self._error('Klippy is not ready')
        if getattr(self.board, 'native_control', False):
            self.board.require_motion()
            return
        if self.production_control:
            self._production_profile()
        elif self.xy_test_mode:
            z_only = self.z_contact_test_mode and self._xy_axes == 'z'
            if not self._xy_axes or (not z_only and any(a not in 'xy' for a in self._xy_axes)):
                raise self._error('XY test accepts only explicit G28 X/Y axes')
            self._xy_profile()
            if z_only:
                self._z_contact_profile()
                if not all(a in self._homed() for a in 'xy'):
                    raise self._error('G28 Z requires current homed X and Y; run G28 X Y first')
            needs_declaration = z_only or not self.native_xy_control
            if needs_declaration and (self._xy_clearance is None or self._xy_clearance_at is None
                    or (not self.is_busy() and not 0. <= self.reactor.monotonic()-self._xy_clearance_at <= XY_CLEARANCE_MAX_AGE)):
                raise self._error('declare current XY clearance with ZORTRAX_XY_ARM CLEARANCE=5')
        elif not self.qualified:
            # Preserve the established M01 refusal for the default closed
            # profile (disabled actuators or missing fresh armed status).
            # This is a read-only gate; it never arms or enables anything.
            self.board.require_motion()
            raise self._error('qualified=False; motion geometry is unqualified')
        if self.board.get_mcu().is_fileoutput():
            raise self._error('FILEOUTPUT has no physical MCU acknowledgement; motion refused')
        self.board.require_motion()
        if self.gcode_move.move_transform not in (None, self.toolhead):
            raise self._error('additional motion transform is not qualified')
        self._peers()
        if self._deadline is not None and self.reactor.monotonic() > self._deadline:
            raise self._error('TOTAL_TIMEOUT')

    def _check_live(self, token, phase=None):
        cause = self._shutdown_cause()
        if cause:
            raise self._error('aborted by MCU/host shutdown: ' + cause)
        if self.state == 'FAULT':
            raise self._error(self.reason or 'motion fault')
        if (token != self.token or self.state not in ('HOMING', 'JOG_WAIT_RELEASE', 'JOG_WAIT_PRESS', 'JOGGING')
                or phase is not None and phase != self.phase_id):
            raise self._error('stale motion session/phase')
        self._guard()

    def _empty(self):
        queued, current, empty = self.toolhead.check_busy(self.reactor.monotonic())
        return bool(empty and finite(queued) and finite(current) and queued <= current)

    def _begin(self, operation, owner_job=None, job_token=None):
        if self.is_busy():
            raise self._error('operation active or fault latched')
        self._bind()
        self._owner_job, self._owner_job_token = owner_job, job_token
        try:
            if getattr(self.board, 'native_control', False):
                self.toolhead.wait_moves()
            self._guard()
            if self.production_control:
                self._production_profile()
            else:
                self._xy_profile() if self.xy_test_mode else self._profile()
            if not getattr(self.board, 'native_control', False) and not self._empty():
                raise self._error('motion queue must be empty')
        except Exception:
            self._owner_job = self._owner_job_token = None
            raise
        self.token += 1
        self._fault_shutdown_requested = False
        self.last_rejection = ''
        self._session_started = self.reactor.monotonic()
        self.phase_id = 0
        self.state, self.phase, self.reason = operation, operation, ''
        self.result = None
        self.initial_travel = self.jog_travel = 0.
        self._deadline = self.reactor.monotonic() + (self.total_timeout if operation == 'HOMING' else self.jog_timeout)
        self._move_deadline = None
        self._pending_detents = self._panel_residual = 0
        return self.token

    def _phase(self, label):
        self.phase, self.phase_id = label, self.phase_id + 1

    def _set_native(self, position, homing_axes=''):
        token, phase = self.token, self.phase_id
        self._check_live(token, phase)
        if len(position) != 4 or not all(finite(v) for v in position):
            raise self._error('invalid native position')
        self._setting_position = True
        try:
            self._native_set_position(list(position), homing_axes=homing_axes)
        finally:
            self._setting_position = False
        self._check_live(token, phase)

    def _temporary_axis(self, axis, value):
        self._temporary = True
        position = self.toolhead.get_position()
        position[axis] = value
        self._set_native(position, 'xyz'[axis])

    def _query(self, endstop=None):
        token, phase = self.token, self.phase_id
        self._check_live(token, phase)
        # This read must not prime a new motion horizon. On the pinned native
        # ToolHead, get_last_move_time() can advance print_time by 250 ms even
        # with no movement, which would turn a safe button release while the
        # query waits into an apparent queued-motion fault. No lookahead may
        # be hidden here; an existing completed/issued horizon remains the
        # MCU query's minclock without changing ToolHead scheduling state.
        queued, current, empty = self.toolhead.check_busy(self.reactor.monotonic())
        if not empty or not finite(queued) or not finite(current):
            raise self._error('unexpected pending lookahead during contact query')
        value = (endstop or self.endstop).query_endstop(max(queued, current))
        self._check_live(token, phase)
        if type(value) not in (bool, int) or value not in (False, True):
            raise self._error('invalid native endstop state')
        return bool(value)

    def _leg(self, axis, target, speed, endstop, triggered, required=True):
        z_only = self.z_contact_test_mode and self._xy_axes == 'z'
        if self.xy_test_mode and ((z_only and axis != 2) or (not z_only
                and (axis not in (0, 1) or 'xy'[axis] not in self._xy_axes))):
            raise self._error('XY test cannot move Z, E or an unrequested axis')
        from . import homing
        token, phase = self.token, self.phase_id
        self._check_live(token, phase)
        start = self.toolhead.get_position()
        if (len(target) != 4 or not all(finite(v) for v in target)
                or any(abs(target[i]-start[i]) > EPS for i in range(4) if i != axis)
                or abs(target[axis]-start[axis]) <= EPS or not finite(speed) or speed <= 0.):
            raise self._error('invalid bounded native leg')
        lo, hi = self._bounds()
        if not lo[axis]-EPS <= target[axis] <= hi[axis]+EPS:
            raise self._error('native leg outside qualified axis envelope')
        proxy = _HomingToolhead(self, axis, target, speed)
        native = homing.HomingMove(self.printer, [(endstop, 'm300_'+'xyz'[axis])], toolhead=proxy)
        if not native.get_mcu_endstops():
            raise self._error('native endstop has no associated stepper')
        self.native_active = True
        self._move_deadline = min(self._deadline, self.reactor.monotonic()+self.move_timeout)
        try:
            measured = native.homing_move(list(target), speed, probe_pos=True,
                                          triggered=triggered, check_triggered=required)
            self._check_live(token, phase)
            if self.reactor.monotonic() > self._move_deadline:
                raise self._error('MOVE_TIMEOUT')
            if required and native.check_no_movement() is not None:
                raise self._error('NO_TRANSITION: contact changed without movement')
            halt = self.toolhead.get_position()
            travelled = abs(halt[axis]-start[axis])
            if travelled > abs(target[axis]-start[axis])+EPS:
                raise self._error('native travel exceeded bounded leg')
            return list(measured), halt, travelled
        except self.printer.command_error as exc:
            if 'No trigger on ' in str(exc):
                raise self._error('NO_CONTACT' if triggered else 'NO_RELEASE')
            raise
        finally:
            self.native_active = False
            self._move_deadline = None

    def _move_and_drain(self, position, speed):
        token, phase = self.token, self.phase_id
        self._check_live(token, phase)
        lo, hi = self._bounds()
        if (len(position) != 4 or not all(finite(v) for v in position)
                or position[3] != self.toolhead.get_position()[3]
                or any(not lo[i]-EPS <= position[i] <= hi[i]+EPS for i in range(3)
                       if position[i] != self.toolhead.get_position()[i])):
            raise self._error('clearance/travel outside native bounds')
        self._move_deadline = min(self._deadline, self.reactor.monotonic()+self.move_timeout)
        self._move_permit = (token, phase, list(position), speed)
        try:
            self.toolhead.move(list(position), speed)
            self._check_live(token, phase)
            self._drain()
        finally:
            self._move_permit = None
            self._move_deadline = None

    def _drain(self):
        token, phase = self.token, self.phase_id
        deadline = min(self._deadline, self.reactor.monotonic()+self.move_timeout)
        self.toolhead.get_last_move_time()
        while not self._empty():
            self._check_live(token, phase)
            if self.reactor.monotonic() > deadline:
                raise self._error('MOVE_TIMEOUT during queue drain')
            self.reactor.pause(self.reactor.monotonic()+PERIOD)
        if self.reactor.monotonic() > deadline:
            raise self._error('MOVE_TIMEOUT during queue drain')
        self._check_live(token, phase)

    def _unknown_z_clearance(self):
        # OEM contact HOME, entered after XY reference, issues five raw STEP
        # pulses before its center/contact search. This is not an initial
        # unknown-position XY clearance or the calibration wizard's 5*S_Z.
        # Express exactly five native
        # configured microsteps through the existing Z stepper's step distance.
        steppers = self.kin.rails[2].get_steppers()
        if len(steppers) != 1:
            raise self._error('initial Z release requires exactly one native Z stepper')
        step_dist = steppers[0].get_step_dist()
        distance = 5.*step_dist if finite(step_dist) else None
        if not finite(distance) or not 0. < distance <= .1:
            raise self._error('five native Z microsteps must be finite and within 0.1mm')
        return distance

    def _retract_z(self, distance):
        # Native Klipper retracts the full configured distance with move().
        # A reverse HomingMove would stop on the first OPEN edge, which does
        # not establish the requested clearance after contact rebound.
        start = self.toolhead.get_position()
        target = list(start)
        target[2] += distance
        self._move_and_drain(target, self.release_speed)
        released = self.toolhead.get_position()
        active = self._query()
        logging.info('M300 Z retract phase=%s start_z=%.6f end_z=%.6f '
                     'requested_mm=%.6f PC7_active=%s', self.phase,
                     start[2], released[2], distance, active)
        if active:
            raise _CompletedRetractContactError(
                'NO_RELEASE: PC7 remains active after completed %.3fmm '
                'native retract (%s)' % (distance, self.phase))
        return released, abs(released[2]-start[2])

    def _initial_clearance(self):
        if not self.production_control and not self.initial_xy_clearance_qualified:
            raise self._error('initial_xy_clearance_qualified=False; starting envelope unqualified')
        unknown = 'z' not in self._homed()
        if unknown and not self.production_control and not self.unknown_z_qualified:
            raise self._error('unknown_z_qualified=False; unknown-Z movement refused')
        lo, hi = self._bounds()
        self._phase('INITIAL_CONTACT_CHECK')
        active = self._query()
        if unknown and (active or not self.production_control):
            # Only an active contact permits a bounded release before XY.
            # Open contact with unknown Z does not authorize a guessed hop.
            # This is an unpublished homing frame, never measured machine Z.
            self._temporary_axis(2, lo[2])
        initial = self.toolhead.get_position()
        released = None
        if active:
            self._phase('INITIAL_RELEASE')
            if getattr(self.board, 'native_control', False):
                released, distance = self._retract_z(self.z_initial_release_distance)
            else:
                target = self.toolhead.get_position()
                target[2] += self.z_initial_release_distance
                _, released, distance = self._leg(2, target, self.release_speed, self.endstop, False)
            self.initial_travel += distance
            if self._query():
                raise self._error('NO_RELEASE: initial PC7 remains active')
        self._phase('INITIAL_CLEARANCE')
        start = self.toolhead.get_position()
        target = list(start)
        if self.production_control and not unknown:
            # Known native Z needs a minimum gap, not another additive drop
            # on each G28 X/Y/Z. The latter could reject valid Z near max.
            target[2] = max(start[2], self.probe.get_offsets()[2]+self.initial_clearance_distance)
        elif self.production_control:
            # The five raw pulses belong to the Z contact routine AFTER XY
            # reference. No unsolicited Z step is issued before XY homing.
            pass
        else:
            target[2] += self.initial_clearance_distance
        clearance_travel = target[2]-start[2]
        if self.initial_travel+clearance_travel > self.initial_travel_limit+EPS:
            raise self._error('initial_travel_limit exhausted')
        if clearance_travel > EPS:
            self._move_and_drain(target, self.release_speed)
        self.initial_travel += abs(self.toolhead.get_position()[2]-start[2])
        if self.initial_travel > self.initial_travel_limit+EPS:
            raise self._error('initial_travel_limit exceeded')
        if self._query():
            raise self._error('CONTACT_ACTIVE_AFTER_CLEARANCE')
        if unknown:
            self.kin.clear_homing_state('z')
        return {'initially_active': active, 'initial_z_unknown': unknown,
                'start_frame': initial, 'release_frame': released,
                'clearance_frame': self.toolhead.get_position(),
                'travel_mm': self.initial_travel, 'limit_mm': self.initial_travel_limit,
                'unreferenced_extra_clearance_steps': 0 if self.production_control else None}

    def _home_axis(self, axis):
        rail = self.kin.rails[axis]
        endstop = rail.get_endstops()[0][0]
        info = rail.get_homing_info()
        direction = 1. if info.positive_dir else -1.
        search = getattr(self, 'xy'[axis]+'_search_distance')
        self._phase('HOME_'+'XY'[axis]+'_CHECK')
        if self._query(endstop):
            self._temporary_axis(axis, info.position_endstop)
            self._phase('HOME_'+'XY'[axis]+'_INITIAL_RELEASE')
            target = self.toolhead.get_position(); target[axis] -= direction*info.retract_dist
            self._leg(axis, target, info.retract_speed, endstop, False)
            if self._query(endstop):
                raise self._error('NO_RELEASE on native '+'XY'[axis])
        self._phase('HOME_'+'XY'[axis]+'_APPROACH')
        self._temporary_axis(axis, info.position_endstop-direction*search)
        target = self.toolhead.get_position(); target[axis] = info.position_endstop
        approach, halt, _ = self._leg(axis, target, info.speed, endstop, True)
        if not self._query(endstop):
            raise self._error('UNSTABLE_CONTACT on native '+'XY'[axis])
        # Establish the native endstop reference while still exclusively owned.
        # Final publication waits for every release/clearance and queue barrier.
        current = list(halt)
        current[axis] = info.position_endstop + halt[axis]-approach[axis]
        self._set_native(current)
        self._phase('HOME_'+'XY'[axis]+'_RELEASE')
        target = self.toolhead.get_position(); target[axis] -= direction*info.retract_dist
        _, release, _ = self._leg(axis, target, info.retract_speed, endstop, False)
        if self._query(endstop):
            raise self._error('NO_RELEASE on native '+'XY'[axis])
        return {'approach': approach, 'release': release,
                'position_endstop': info.position_endstop}

    def _home_z(self):
        if not all(axis in self._homed() for axis in 'xy'):
            raise self._error('Z homing requires known native XY')
        initial_contact_release = None
        if self.z_contact_test_mode or self.production_control:
            # PC7 may already be triggered when G28 Z starts with the nozzle
            # touching the bed (or may have reclosed after the early release).
            # Never attempt XY travel across a closed nozzle-bed contact.
            # Move the bed away by a bounded distance, drain the native queue,
            # and confirm the contact is OPEN before any lateral movement.
            # With a referenced Z use real coordinates; otherwise use only a
            # temporary unpublished frame for this single retract.
            self._phase('HOME_Z_INITIAL_CONTACT_CHECK')
            if self._query():
                lo, hi = self._bounds()
                if 'z' not in self._homed():
                    self._temporary_axis(2, lo[2])
                if self.toolhead.get_position()[2] + self.z_release_distance > hi[2] + EPS:
                    raise self._error('CONTACT_RELEASE_OUTSIDE_Z_BOUNDS')
                self._phase('HOME_Z_INITIAL_CONTACT_RELEASE')
                released, distance = self._retract_z(self.z_release_distance)
                # _retract_z always checks PC7 after completing the full
                # travel; an active/shorted PC7 fails closed, never retries
                # indefinitely and never resets the latched MCU error.
                initial_contact_release = {'distance_mm': distance,
                                           'position_after': list(released),
                                           'PC7_confirmed_open': True}
        retreat = None
        if self.production_control and 'z' not in self._homed():
            # The source contact routine expects XY already referenced. Its
            # five raw pulses precede center travel, not initial Y/X homing.
            # Existing referenced Z already has a checked minimum gap and
            # must not accumulate a new drop on every rehome.
            lo, hi = self._bounds()
            self._phase('HOME_Z_FIVE_STEP_CLEARANCE')
            self._temporary_axis(2, lo[2])
            before = self.toolhead.get_position()
            target = list(before)
            target[2] += self._unknown_z_clearance()
            self._move_and_drain(target, self.release_speed)
            if self._query():
                raise self._error('CONTACT_ACTIVE_AFTER_FIVE_STEP_CLEARANCE')
            retreat = {'steps': 5, 'distance_mm': target[2]-before[2],
                       'after_xy_reference': True}
            self.kin.clear_homing_state('z')
        self._phase('HOME_XY_TRAVEL')
        target = self.toolhead.get_position(); target[:2] = self.home_xy
        self._move_and_drain(target, self.travel_speed)
        if self._query():
            raise self._error('CONTACT_ACTIVE_BEFORE_APPROACH')
        lo, hi = self._bounds()
        self._phase('HOME_Z_APPROACH')
        self._temporary_axis(2, lo[2]+self.z_search_distance)
        target = self.toolhead.get_position(); target[2] = lo[2]
        approach, halt, search_travel_mm = self._leg(
            2, target, self.z_speed, self.endstop, True)
        if not self._query():
            raise self._error('UNSTABLE_CONTACT on PC7')
        # Observed motion is reconstructed from native homing positions. No
        # encoder exists on M300 Z: this is an estimate of executed step
        # commands, NOT a physical measurement of the spindle movement.
        steppers = self.kin.rails[2].get_steppers()
        if len(steppers) != 1:
            raise self._error('Z step report requires one native Z stepper')
        step_mm = steppers[0].get_step_dist()
        if not finite(step_mm) or step_mm <= 0.:
            raise self._error('invalid Z step distance for homing report')
        search_steps_estimated = int(round(search_travel_mm / step_mm))
        contact_z = self.probe.get_offsets()[2]
        current = list(halt); current[2] = contact_z+halt[2]-approach[2]
        self._set_native(current)
        self._phase('HOME_Z_RELEASE')
        native_retract = getattr(self.board, 'native_control', False)
        if native_retract:
            release, release_travel = self._retract_z(self.z_release_distance)
        else:
            target = self.toolhead.get_position(); target[2] += self.z_release_distance
            _, release, release_travel = self._leg(2, target, self.release_speed, self.endstop, False)
        if self._query():
            raise self._error('NO_RELEASE: PC7 remains active')
        result = {'approach': approach, 'release': release, 'contact_z': contact_z,
                  'initial_contact_release': initial_contact_release,
                  'search_travel_mm_estimated': search_travel_mm,
                  'search_steps_estimated': search_steps_estimated,
                  'configured_step_distance_mm': step_mm,
                  'step_count_kind': 'native_motion_estimate_NO_ENCODER',
                  'search_limit_mm': self.z_search_distance}
        if native_retract:
            result.update(release_distance_mm=release_travel,
                          release_policy='FULL_NATIVE_RETRACT_THEN_QUERY')
        if self.production_control:
            result['pre_approach_retreat'] = retreat
        if self.z_contact_test_mode or self.production_control:
            self._phase('HOME_Z_FINAL_CLEARANCE')
            target = self.toolhead.get_position()
            if native_retract:
                target[2] = max(target[2], contact_z+self.z_contact_clearance)
            else:
                target[2] += self.z_contact_clearance
            self._move_and_drain(target, self.release_speed)
            if self._query():
                raise self._error('CONTACT_ACTIVE_AFTER_FINAL_CLEARANCE')
            result['clearance_position'] = self.toolhead.get_position()
            result['clearance_mm'] = self.z_contact_clearance
        return result

    def _commit_parser(self, axes):
        from . import homing
        token, phase = self.token, self.phase_id
        self._check_live(token, phase)
        # The bounded HomingMove path deliberately does not impersonate a
        # complete home_rails event (optional plugins may require MCU trigger
        # maps). Invoke the pinned native parser's actual homing callback with
        # a real Homing object: only homed XYZ lose G92; native homing offsets,
        # E, relative/absolute modes and scale factors remain untouched.
        state = homing.Homing(self.printer)
        indices = ['xyz'.index(axis) for axis in axes]
        state.set_axes(indices)
        self.gcode_move._handle_home_rails_end(state, [self.kin.rails[i] for i in indices])
        self._check_live(token, phase)

    def home(self, owner_job=None, job_token=None, axes='xyz'):
        try:
            order = axes_spec(axes)
        except ValueError as exc:
            raise self._error(str(exc))
        if self.production_control and 'z' in order and not all(a in order or a in self._homed() for a in 'xy'):
            raise self._error('Z homing requires known native XY or requested XY homing')
        if self.xy_test_mode:
            z_only = self.z_contact_test_mode and order == 'z'
            if ('z' in order and not z_only) or owner_job is not None or job_token is not None:
                if self.z_contact_test_mode:
                    raise self._error('contact commissioning requires separate G28 X Y then G28 Z')
                raise self._error('XY test accepts G28 X Y / G28 X / G28 Y only; Z is a later stage')
            self._xy_axes = order
        if owner_job is None and job_token is not None:
            raise self._error('job token without owning job')
        if owner_job is not None and (owner_job is not self.job or type(job_token) is not int
                or self.job.machine.token != job_token or self.job.machine.state != 'HOMING'):
            raise self._error('owning job must have the current HOMING token')
        try:
            token = self._begin('HOMING', owner_job, job_token)
        except Exception as exc:
            self.last_rejection = str(exc)
            self._xy_axes = None
            raise
        self._executing = True
        result = {'axes': {}, 'order': order, 'session_token': token}
        try:
            if 'z' in order and not all(a in order or a in self._homed() for a in 'xy'):
                raise self._error('Z homing requires known native XY or requested XY homing')
            result['initial'] = ({'xy_only': 'z' not in order, 'declared_clearance_mm': self._xy_clearance,
                                  'automatic_z_movement': False, 'z_contact_only': order == 'z'}
                                 if self.xy_test_mode else self._initial_clearance())
            if self.native_xy_control and 'z' not in order:
                self._phase('HOME_INITIAL_CONTACT_CHECK')
                if self._query():
                    raise self._error('CONTACT_ACTIVE_BEFORE_XY_TRAVEL')
            for axis in (1, 0):
                if 'xyz'[axis] in order:
                    result['axes']['xyz'[axis]] = self._home_axis(axis)
            if 'z' in order:
                result['axes']['z'] = self._home_z()
            self._check_live(token)
            self._phase('FINAL_DRAIN')
            self._drain()
            self._commit_parser(order)
            self._check_live(token)
            self._temporary = False
            result['final_position'] = self.toolhead.get_position()
            result['homed_axes'] = self._homed()
            self.result = result
            self.state, self.phase = 'COMPLETE', 'COMPLETE'
            self._deadline = None
        except Exception as exc:
            # The printer's original shutdown message has priority over any
            # stale token generated while native HomingMove unwinds.
            shutdown_cause = self._shutdown_cause()
            if shutdown_cause:
                detail = 'homing interrupted: ' + shutdown_cause
                self._fault(detail, shutdown=False)
                self.last_rejection = str(self._error(detail))
                raise self._error(detail) from exc
            stopped_contact_error = (isinstance(exc, _CompletedRetractContactError)
                                     and getattr(self.board, 'native_control', False))
            self._fault(str(exc), shutdown=not stopped_contact_error)
            if stopped_contact_error and not self.printer.is_shutdown():
                # Match native PrinterHoming.cmd_G28: a completed homing
                # validation error disables motors and returns a command error.
                # Timeouts, interrupted movement and MCU faults still shut down.
                self.last_rejection = str(self._error(exc))
                try:
                    self.printer.lookup_object('stepper_enable').motor_off()
                except Exception:
                    self.printer.invoke_async_shutdown(
                        'M300 motion: unable to disable motors after failed retract')
            raise self._error(str(exc))
        finally:
            self._executing = False
            self._owner_job = self._owner_job_token = None
            self._xy_axes = None
        return self.get_status(self.reactor.monotonic())

    def _panel_baseline(self):
        oled = self.printer.lookup_object('m300_oled', None)
        if oled is None:
            raise self._error('fresh native OLED panel snapshot required')
        status = oled.get_status(self.reactor.monotonic())
        age = status.get('encoder_age')
        if (status.get('connected') is not True or not finite(age)
                or not 0. <= age <= self.panel_timeout):
            raise self._error('fresh native OLED panel snapshot required')
        try:
            snapshot = panel_snapshot(status.get('encoder'))
        except ValueError as exc:
            raise self._error(str(exc))
        encoder = getattr(oled, 'encoder', None)
        self._steps_per_detent = getattr(encoder, 'steps_per_detent', 4)
        self._encoder_reverse = getattr(encoder, 'reverse', False)
        if self._steps_per_detent not in (1, 2, 4):
            raise self._error('invalid native encoder scale')
        return snapshot, self.reactor.monotonic()-age

    def start_jog(self):
        if not self.production_control and not self.jog_qualified:
            raise self._error('jog_qualified=False; manual Z geometry is unqualified')
        token = self._begin('JOG_WAIT_RELEASE')
        try:
            if not all(a in self._homed() for a in 'xyz'):
                raise self._error('manual Z requires known native XYZ')
            self._panel, self._panel_time = self._panel_baseline()
            self._check_live(token)
            # The cached released baseline may predate an unobserved press.
            # Every lease therefore needs its own current-view, post-session
            # released frame before a subsequent new press can authorize jog.
            self.state = 'JOG_WAIT_RELEASE'
            self._phase(self.state)
            return token
        except Exception as exc:
            self._finish_idle('CANCELLED', str(exc))
            self.last_rejection = str(exc)
            raise

    def panel_update(self, snapshot, eventtime, token, view_current=False):
        if not self.state.startswith('JOG_') and self.state != 'JOGGING':
            return False
        try:
            value = panel_snapshot(snapshot)
        except ValueError:
            self.cancel('invalid panel snapshot')
            return True
        now = self.reactor.monotonic()
        if not finite(eventtime) or not 0. <= now-eventtime <= self.panel_timeout:
            self.cancel('STALE_PANEL')
            return True
        if eventtime < self._session_started:
            # Even a recently received packet may predate this lease. Stop
            # instead of later mistaking its held button for a fresh press.
            self.cancel('PRE_SESSION_PANEL')
            return True
        # A foreign frame is stop-only, including a held button. Ignoring its
        # press counter would let the next current-view heartbeat resurrect
        # that old press as a new authorization against a released baseline.
        if token != self.token or view_current is not True:
            self.cancel('PANEL_CONTEXT_LOST')
            return True
        old = self._panel
        seq = (value['sequence']-old['sequence']) & 0xffffffff
        if not 0 < seq < 0x80000000:
            if not value['pressed']:
                self.cancel('stale panel release')
            return True
        counts = {k: (value[k]-old[k]) & 0xffffffff for k in ('presses', 'releases', 'shorts', 'longs')}
        delta = (value['position']-old['position']) & 0xffffffff
        if delta >= 0x80000000:
            delta -= 0x100000000
        self._panel, self._panel_time = value, eventtime
        if (abs(delta) > 128 or any(v > 1 for v in counts.values())
                or value['invalid'] != old['invalid']):
            self.cancel('PANEL_DISCONTINUITY')
            return True
        if self.state == 'JOG_WAIT_RELEASE':
            if not value['pressed'] and (not old['pressed'] or counts['releases'] == 1):
                self.state = 'JOG_WAIT_PRESS'; self._phase(self.state)
            return True
        if self.state == 'JOG_WAIT_PRESS':
            if value['pressed'] and not old['pressed'] and counts['presses'] == 1:
                self.state = 'JOGGING'; self._phase(self.state)
                self._panel_residual = 0
            return True
        if not value['pressed'] or counts['releases']:
            self.cancel('button released')
            return True
        if not old['pressed'] or counts['presses']:
            self.cancel('PANEL_BUTTON_DISCONTINUITY')
            return True
        self._panel_residual += -delta if self._encoder_reverse else delta
        detents = abs(self._panel_residual)//self._steps_per_detent
        if self._panel_residual < 0:
            detents = -detents
        self._panel_residual -= detents*self._steps_per_detent
        pending = self._pending_detents+detents
        if abs(pending) > 4 or self.jog_travel+abs(pending)*self.jog_step > self.jog_max_distance+EPS:
            self.cancel('JOG_TRAVEL_LIMIT')
            return True
        self._pending_detents = pending
        return True

    def _jog_once(self):
        token = self.token
        self._guard()
        if not all(a in self._homed() for a in 'xyz'):
            raise self._error('POSITION_LOST')
        if not self._empty():
            raise self._error('unexpected queued motion during jog')
        sign = 1 if self._pending_detents > 0 else -1
        self._pending_detents -= sign
        self._phase('JOG_AWAY' if sign > 0 else 'JOG_TOWARD')
        contact = self._query()
        if contact and sign < 0:
            self.cancel('CONTACT_BLOCKS_TOWARD_JOG')
            return
        start = self.toolhead.get_position()
        target = list(start); target[2] += sign*self.jog_step
        if self.jog_travel+self.jog_step > self.jog_max_distance+EPS:
            raise self._error('JOG_TRAVEL_LIMIT')
        if sign < 0 or contact:
            _, halt, distance = self._leg(2, target, self.jog_speed, self.endstop,
                                          triggered=sign < 0, required=False)
        else:
            self._move_and_drain(target, self.jog_speed)
            halt = self.toolhead.get_position(); distance = abs(halt[2]-start[2])
        self._check_live(token)
        self.jog_travel += distance
        if self.jog_travel > self.jog_max_distance+EPS:
            raise self._error('JOG_TRAVEL_LIMIT')
        if sign < 0 and self._query():
            self.cancel('CONTACT_REACHED')

    def _finish_idle(self, state, reason, sync=True):
        self._xy_clearance = self._xy_clearance_at = None
        self.state, self.phase, self.reason = state, state, str(reason)
        self.token += 1
        self.phase_id += 1
        self.result = None
        self._pending_detents = self._panel_residual = 0
        self._deadline = self._move_deadline = None
        self._move_permit = None
        self._panel = self._panel_time = None
        self._owner_job = self._owner_job_token = None
        if sync and self.gcode_move is not None:
            self.gcode_move.reset_last_position()

    def _invalidate_position(self):
        self._temporary = False
        if self.kin is not None:
            self.kin.clear_homing_state('xyz')
        if self.gcode_move is not None:
            self.gcode_move.reset_last_position()

    def _fault(self, reason, shutdown=True):
        already = self.state == 'FAULT'
        if already:
            # Do not advance token/phase again on the shutdown event and the
            # delayed native homing continuation. Still escalate once if a
            # prior non-shutdown fault is later judged unsafe.
            if (shutdown and not self.printer.is_shutdown()
                    and not self._fault_shutdown_requested):
                self._fault_shutdown_requested = True
                self.printer.invoke_async_shutdown(str(self._error(self.reason or reason)))
            return
        self._finish_idle('FAULT', reason, sync=False)
        self._temporary = False
        try:
            if self.kin is not None:
                self.kin.clear_homing_state('xyz')
        except Exception:
            logging.exception('M300 motion failed to invalidate native axes')
        if shutdown and not self.printer.is_shutdown():
            self._fault_shutdown_requested = True
            self.printer.invoke_async_shutdown(str(self._error(reason)))
        try:
            if self.gcode_move is not None:
                self.gcode_move.reset_last_position()
        except Exception:
            logging.exception('M300 motion failed to synchronize invalid coordinates')

    def cancel(self, reason='operator cancelled', token=None):
        if token is not None and (type(token) is not int or token != self.token):
            raise self._error('stale motion session token')
        if self.state == 'FAULT':
            return self.get_status(self.reactor.monotonic())
        if not self.is_busy():
            if self.result is not None:
                self._finish_idle('CANCELLED', reason)
            return self.get_status(self.reactor.monotonic())
        if self.state == 'HOMING' or self.native_active or self._move_deadline is not None or not self._empty():
            self._fault(str(reason))
        else:
            self._finish_idle('CANCELLED', reason)
        return self.get_status(self.reactor.monotonic())

    def _lifecycle(self, *args):
        cause = self._shutdown_cause()
        self.ready = False
        # Preserve the actual timer/MCU failure before the continuation sees
        # its revoked session. Do not send another emergency shutdown here.
        self._fault('host lifecycle: ' + cause if cause else
                    'host lifecycle invalidated motion/position', shutdown=False)
        self.reactor.update_timer(self._timer, self.reactor.NEVER)
        self.reactor.update_timer(self._watch_timer, self.reactor.NEVER)

    def _motor_off(self, *args):
        self._xy_clearance = self._xy_clearance_at = None
        if self.is_busy():
            self._fault('POSITION_LOST: shared PD14 motors disabled')
        else:
            self.result = None
            self._invalidate_position()
            if self.z_contact_test_mode or self.native_xy_control or self.production_control:
                self.state, self.phase = 'IDLE', 'POSITION_LOST'
                self.reason = 'Motors disabled; homing required'

    def _enable_changed(self, print_time, enabled):
        if not enabled:
            self._motor_off()

    def _foreign_home(self, *args):
        if self.is_busy():
            self._fault('foreign homing invalidated the operation')

    def _tick(self, eventtime):
        if not self.ready:
            return self.reactor.NEVER
        if self.state == 'JOGGING' and self._pending_detents and not self._executing:
            self._executing = True
            token = self.token
            try:
                self._jog_once()
            except Exception as exc:
                # Querying PC7 may yield before any segment has been queued.
                # A safe release there revokes the token and stays CANCELLED;
                # unwinding its stale continuation must not create a fault.
                if not (self.state == 'CANCELLED' and self.token != token
                        and not self.native_active and self._move_deadline is None
                        and self._empty()):
                    self._fault(str(exc))
            finally:
                self._executing = False
        return eventtime+PERIOD

    def _watchdog(self, eventtime):
        if not self.ready:
            return self.reactor.NEVER
        if self.state == 'HOMING' or self.state.startswith('JOG_') or self.state == 'JOGGING':
            try:
                self._guard()
                if self._move_deadline is not None and eventtime > self._move_deadline:
                    raise self._error('MOVE_TIMEOUT')
                if self.state != 'HOMING' and (self._panel_time is None
                        or not 0. <= eventtime-self._panel_time <= self.panel_timeout):
                    self.cancel('STALE_PANEL')
            except Exception as exc:
                self._fault(str(exc))
        return eventtime+PERIOD

    def get_status(self, eventtime):
        homed = self._homed()
        return {'version': VERSION, 'model': 'M300_CLASSIC', 'state': self.state,
                'motion_revision': '0.13.15.3-M300-CONTACT-RELEASE-DIAG',
                'production_control': self.production_control,
                'unknown_z_initial_clearance_steps': 0 if self.production_control else None,
                'z_contact_retreat_steps': 5 if self.production_control else None,
                'production_e_velocity': self.production_e_velocity,
                'production_e_accel': self.production_e_accel,
                'production_retract_accel': self.production_retract_accel,
                'z_contact_test_mode': self.z_contact_test_mode,
                'native_xy_control': self.native_xy_control,
                'xy_jog_moves': self.xy_jog_moves,
                'native_position': None if self.toolhead is None else self.toolhead.get_position(),
                'xy_test_mode': self.xy_test_mode, 'xy_test_axes': self._xy_axes,
                'xy_clearance_mm': self._xy_clearance,
                'xy_clearance_age': (None if self._xy_clearance_at is None else eventtime-self._xy_clearance_at),
                'busy': self.is_busy(), 'ready': self.ready, 'installed': self.installed,
                'session_token': self.token, 'phase_id': self.phase_id,
                'session_started': self._session_started,
                'phase': self.phase, 'reason': self.reason, 'last_rejection': self.last_rejection,
                'position_valid': bool(self.ready and self.state not in ('FAULT', 'HOMING') and not self._temporary
                                       and all(a in homed for a in 'xyz')),
                'homed_axes': homed, 'temporary_homing_frame': self._temporary,
                'native_active': self.native_active, 'qualified': self.qualified,
                'unknown_z_qualified': self.unknown_z_qualified,
                'initial_xy_clearance_qualified': self.initial_xy_clearance_qualified,
                'jog_qualified': self.jog_qualified, 'hardware_qualified': False,
                'initial_travel_mm': self.initial_travel, 'jog_travel_mm': self.jog_travel,
                'pending_detents': self._pending_detents, 'deadline': self._deadline,
                'panel_age': None if self._panel_time is None else eventtime-self._panel_time,
                'result': self.result, 'automatic_arm': False,
                'physical_hardware_tests': False}

    def _params(self, gcmd, allowed):
        params = gcmd.get_command_parameters()
        if any(k not in allowed for k in params):
            raise self._error('unexpected command parameter')
        return params

    def cmd_home(self, gcmd):
        self._params(gcmd, ('AXES',))
        self.home(axes=gcmd.get('AXES', 'XYZ'))
        self.cmd_status(gcmd)

    def cmd_G28(self, gcmd):
        params = dict(gcmd.get_command_parameters())
        if params.get('G') == '28':
            del params['G']
        if self.production_control:
            # Native Klipper selects axes by presence; X0/Y0/Z0 do not set
            # endstop coordinates. Keep rejection of unknown parameters.
            if any(k not in ('X', 'Y', 'Z') for k in params):
                raise self._error('G28 accepts only X/Y/Z axes')
        elif any(k not in ('X', 'Y', 'Z') or value != '' for k, value in params.items()):
            raise self._error('G28 accepts only bare X/Y/Z axes')
        self.home(axes=''.join(params) or 'xyz')

    def cmd_jog(self, gcmd):
        self._params(gcmd, ())
        token = self.start_jog()
        try:
            menu = self.printer.lookup_object('m300_menu', None)
            if menu is None:
                raise self._error('jog requires the current motion menu view')
            menu.present_motion_jog(self, token)
        except Exception as exc:
            self.cancel('jog view could not be established: '+str(exc), token)
            raise self._error('jog view could not be established: '+str(exc))
        self.cmd_status(gcmd)

    def cmd_cancel(self, gcmd):
        self._params(gcmd, ('TOKEN',))
        self.cancel(token=gcmd.get_int('TOKEN', None, minval=0))
        self.cmd_status(gcmd)

    def _web_cancel(self, request):
        try:
            result = self.cancel('webhook cancelled', request.get_int('token', None))
        except self.printer.command_error as exc:
            raise request.error(str(exc))
        request.send(result)

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_MOTION '+json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))


def load_config(config):
    return M300Motion(config)
