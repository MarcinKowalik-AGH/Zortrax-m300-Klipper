# SPDX-License-Identifier: GPL-3.0-or-later
"""M300 M03 bounded filament services on native Klippy and the M02 owner.

No automatic ARM, physical calibration, second GPIO/ADC owner, or job Resume.
Only one acknowledged E segment may be outstanding. Native motion permissions
are consumed before entering a possibly yielding call, never a global bypass.
"""
import copy
import json
import logging
import math

from .m300_filament_state import (FilamentState, FilamentStateError, build_plan,
                                 TRANSPORT_STATES, WAIT_STATES)
from .m300_native_service import (NativeServiceLease, native_service_frame,
                                  native_temperature_ready, require_idle_print)

PERIOD = .1
JOB_IDLE = {'IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR'}
STATE_NAME = 'M300_M03_SERVICE'


class M300Filament:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.job = self.printer.load_object(config, 'm300_job')
        self.board = self.job.board
        self.native_mode = bool(getattr(self.board,'native_control',False))
        self.native_lease = (NativeServiceLease(self,
            lambda:(self.machine.token,self.machine.phase_id),
            lambda:self._guard(transport=True),self.cancel) if self.native_mode else None)
        self.filament_qualified = config.getboolean('filament_qualified', False)
        self.procedure_temperature = self._option('procedure_temperature', 240., 170., 300.)
        self.use_sensor = config.getboolean('use_filament_sensor', False)
        self.load_length = self._option('load_length', 130., .1, 500.)
        self.unload_length = self._option('unload_length', 110., .1, 500.)
        self.change_load_length = self._option('change_load_length', 150., .1, 500.)
        self.segment_length = self._option('segment_length', 5., .1, 20.)
        self.purge_length = self._option('purge_length', 5., .1, 50.)
        self.max_purge_length = self._option('max_purge_length', 20., 0., 200.)
        self.load_speed = self._option('load_speed', 2., .1, 20.)
        self.unload_speed = self._option('unload_speed', 2., .1, 20.)
        self.purge_speed = self._option('purge_speed', 1., .1, 10.)
        self.heat_timeout = self._option('heat_timeout', 1200., 1., 7200.)
        self.confirm_timeout = self._option('confirm_timeout', 600., 1., 7200.)
        self.move_timeout = self._option('move_timeout', 60., 1., 600.)
        self.total_timeout = self._option('total_timeout', 2400., 1., 14400.)
        self.tolerance = self._option('temperature_tolerance', 2., .1, 10.)
        self.stable_time = self._option('temperature_stable_time', 2., 0., 30.)
        self.standby_after = self._option('standby_after', 300., 0., 7200.)
        self.standby_temperature = self._option('standby_temperature', 150., 0., 300.)
        self.max_material_length = self._option('max_material_length', 500., 1., 1000.)
        if self.standby_after > self.confirm_timeout:
            raise config.error('M300 filament standby_after exceeds confirm_timeout')
        self.machine = FilamentState()
        self.ready = self.installed = False
        self.last_rejection = ''
        self.target = 0.
        self._expected_target = None
        self._temperature_stable_since = None
        self._phase_started = None
        self._intent = None
        self._owner_token = None
        self._native_pause = None
        self._owner_file = self._owner_gcode = None
        self._owner_context = None
        self._anchor = None
        self._saved_gcode = None
        self._parser_restored = False
        self._idle_saved = None
        self._captured = False
        self._parent_cancelled = False
        self._cancel_before_capture = False
        self._cleanup_pending = False
        self._executing = False
        self._waiting = None
        self._drain_deadline = None
        self._need_drain = False
        self._move_permit = None
        self._native_move = None
        self.toolhead = self.hotend = self.gcode_move = self.idle = None
        self._timer = self.reactor.register_timer(self._tick)
        self._watchdog_timer = self.reactor.register_timer(self._watchdog)
        self.board.get_mcu().register_config_callback(self._audit_config)
        for event, handler in [('klippy:connect', self._connect), ('klippy:ready', self._ready),
                               ('klippy:shutdown', self._shutdown), ('klippy:disconnect', self._disconnect),
                               ('gcode:request_restart', self._restart),
                               ('stepper_enable:motor_off', self._motor_off),
                               ('homing:home_rails_begin', self._homing_begin)]:
            self.printer.register_event_handler(event, handler)
        commands = {'LOAD_FILAMENT': self.cmd_load, 'UNLOAD_FILAMENT': self.cmd_unload,
                    'CHANGE_FILAMENT': self.cmd_change, 'M600': self.cmd_m600,
                    'FILAMENT_CONFIRM': self.cmd_confirm, 'FILAMENT_PURGE': self.cmd_purge,
                    'FILAMENT_CANCEL': self.cmd_cancel}
        for name, handler in commands.items():
            self.gcode.register_command(name, handler)
        self.gcode.register_command('ZORTRAX_FILAMENT_STATUS', self.cmd_status, when_not_ready=True)

    def _error(self, message):
        return self.printer.command_error('M300 filament: ' + str(message))

    def _option(self, name, default, minimum, maximum):
        value = self.config.getfloat(name, default, minval=minimum, maxval=maximum)
        if not math.isfinite(value):
            raise self.config.error('M300 filament %s must be finite' % name)
        return value

    def _bind(self):
        self.job._bind_resources()
        self.toolhead, self.hotend = self.job.toolhead, self.job.hotend
        self.gcode_move, self.idle = self.job.gcode_move, self.job.idle

    def _profile(self, mode, length=None, load_length=None, unload_length=None):
        load = self.change_load_length if mode == 'CHANGE' else self.load_length
        unload = self.unload_length
        if length is not None:
            if mode == 'CHANGE':
                raise self._error('CHANGE uses LOAD_LENGTH and UNLOAD_LENGTH, not LENGTH')
            if mode == 'LOAD':
                load = length
            else:
                unload = length
        if load_length is not None:
            load = load_length
        if unload_length is not None:
            unload = unload_length
        profile = dict(load_mm=load, unload_mm=unload, purge_mm=self.purge_length,
                       max_purge_mm=self.max_purge_length, segment_mm=self.segment_length,
                       load_speed=self.load_speed, unload_speed=self.unload_speed,
                       purge_speed=self.purge_speed, heat_timeout=self.heat_timeout,
                       confirm_timeout=self.confirm_timeout, move_timeout=self.move_timeout,
                       total_timeout=self.total_timeout)
        try:
            plan = build_plan(mode, profile, self.toolhead.get_extruder().max_e_dist)
        except (ValueError, TypeError) as exc:
            raise self._error(str(exc))
        if plan['total_budget_mm'] > self.max_material_length:
            raise self._error('plan exceeds max_material_length')
        return plan

    def _audit_config(self):
        self._bind()
        if self.segment_length > self.toolhead.get_extruder().max_e_dist:
            raise self.config.error('M300 filament segment_length exceeds native max_extrude_only_distance')
        if self.standby_temperature > self.hotend.max_temp:
            raise self.config.error('M300 filament standby_temperature exceeds native heater limit')
        for mode in ('LOAD', 'UNLOAD', 'CHANGE'):
            try:
                self._profile(mode)
            except Exception as exc:
                raise self.config.error('M300 filament invalid profile: ' + str(exc))

    def _locks_motion(self):
        return (self.is_busy() and self.machine.state != 'WAIT_PAUSE'
                and not self._parent_cancelled and not self._cancel_before_capture)

    def _connect(self):
        self._bind()
        self._native_move = self.toolhead.move
        if getattr(self.job.board, 'native_control', False):
            self.installed = True
            return
        native_move = self._native_move
        def guarded_move(position, speed):
            if self._locks_motion():
                permit, self._move_permit = self._move_permit, None
                if (permit is None or permit['token'] != self.machine.token
                        or permit['phase'] != self.machine.phase_id
                        or list(position) != permit['position'] or speed != permit['speed']):
                    raise self._error('filament service owns motion; foreign move refused')
                self._check_deadline()
                self._guard(transport=True)
            return native_move(position, speed)
        self.toolhead.move = guarded_move
        for name in ('drip_move', 'set_position'):
            original = getattr(self.toolhead, name, None)
            if original is not None:
                def guarded(*args, original=original, name=name, **kwargs):
                    if self._locks_motion():
                        raise self._error('filament service owns position; ' + name + ' refused')
                    return original(*args, **kwargs)
                setattr(self.toolhead, name, guarded)
        self._bind_parser_move()
        blocked = ('G0', 'G1', 'G28', 'G90', 'G91', 'G92', 'M82', 'M83', 'M204', 'M220', 'M221',
                   'SAVE_GCODE_STATE', 'RESTORE_GCODE_STATE', 'SET_GCODE_OFFSET',
                   'SET_KINEMATIC_POSITION', 'FORCE_MOVE', 'STEPPER_BUZZ', 'SET_VELOCITY_LIMIT',
                   'PROBE', 'PROBE_ACCURACY', 'PROBE_CALIBRATE', 'BED_MESH_CALIBRATE',
                   'SCREWS_TILT_CALCULATE', 'Z_TILT_ADJUST', 'QUAD_GANTRY_LEVEL',
                   'PID_CALIBRATE', 'SET_PRESSURE_ADVANCE', 'SET_RETRACTION',
                   'SET_EXTRUDER_ROTATION_DISTANCE', 'SYNC_EXTRUDER_MOTION',
                   'M109', 'M190', 'TEMPERATURE_WAIT')
        for name in blocked:
            original = self.gcode.register_command(name, None)
            if original is not None:
                def guarded_command(gcmd, original=original, name=name):
                    if self.is_busy():
                        raise self._error('filament service owns resources; ' + name + ' refused')
                    return original(gcmd)
                self.gcode.register_command(name, guarded_command)
        for name in ('M104', 'M140', 'SET_HEATER_TEMPERATURE', 'TURN_OFF_HEATERS'):
            original = self.gcode.register_command(name, None)
            if original is None:
                continue
            def heat_command(gcmd, original=original, name=name):
                if self.is_busy():
                    value = (0. if name == 'TURN_OFF_HEATERS' else
                             gcmd.get_float('TARGET' if name == 'SET_HEATER_TEMPERATURE' else 'S', 0.))
                    if value != 0.:
                        raise self._error('filament service owns temperature; external target refused')
                    self.cancel('external heater-off command')
                return original(gcmd)
            self.gcode.register_command(name, heat_command)
        for name in self.job.steppers.get_steppers():
            self.job.steppers.lookup_enable(name).register_state_callback(self._enable_changed)
        self.installed = True

    def _bind_parser_move(self):
        # GCodeMove may have retained a pre-wrapper bound method at ready.
        target = getattr(self.gcode_move, 'move_with_transform', None)
        if target is self._native_move or target == self._native_move:
            self.gcode_move.move_with_transform = self.toolhead.move

    def _ready(self):
        if getattr(self.job.board, 'native_control', False):
            self.ready = True
            return
        self._bind_parser_move()
        self.ready = True
        self.reactor.update_timer(self._timer, self.reactor.NOW)
        self.reactor.update_timer(self._watchdog_timer, self.reactor.NOW)

    def _shutdown(self):
        self.ready = False
        self._fault('Klippy shutdown', signal_shutdown=False)
        self._stop_timers()
        if self.native_lease is not None:self.native_lease.release()

    def _disconnect(self):
        self.ready = False
        self._fault('MCU/host disconnected', signal_shutdown=False)
        self._stop_timers()
        if self.native_lease is not None:self.native_lease.release()

    def _restart(self, *args):
        self.ready = False
        self._fault('restart invalidated material operation', signal_shutdown=False)
        self._stop_timers()
        if self.native_lease is not None:self.native_lease.release()

    def _stop_timers(self):
        self.reactor.update_timer(self._timer, self.reactor.NEVER)
        self.reactor.update_timer(self._watchdog_timer, self.reactor.NEVER)

    def _motor_off(self, *args):
        if self.machine.active and not self._parent_cancelled:
            self._fault('motors disabled; service position lost')

    def _enable_changed(self, print_time, enabled):
        if not enabled:
            self._motor_off()

    def _homing_begin(self, *args):
        if self.machine.active:
            self._fault('external homing invalidated material operation')

    def is_busy(self):
        return bool(self.machine.active or self.machine.state == 'FAULT'
                    or self._cleanup_pending or self._executing)

    def _validate_temperature(self, target):
        if (isinstance(target, bool) or not isinstance(target, (int, float))
                or not math.isfinite(target) or not self.hotend.min_extrude_temp <= target <= self.hotend.max_temp):
            raise self._error('TEMP must be finite and within native extrusion/heater limits')
        return float(target)

    def _pause_identity(self):
        pause = self.printer.lookup_object('pause_resume', None)
        stats = self.printer.lookup_object('print_stats', None)
        sd = self.printer.lookup_object('virtual_sdcard', None)
        if (pause is None or stats is None or not pause.is_paused
                or stats.get_status(self.reactor.monotonic()).get('state') != 'paused'
                or sd is not None and sd.is_active()):
            raise self._error('pause the native print before changing material')
        saved = self.gcode_move.saved_states.get('PAUSE_STATE')
        if not isinstance(saved, dict):
            raise self._error('native PAUSE_STATE is unavailable')
        status = sd.get_status(self.reactor.monotonic()) if sd is not None else {}
        return dict(pause_id=id(pause), sd_id=id(sd),
                    filename=stats.get_status(self.reactor.monotonic()).get('filename'),
                    file_path=status.get('file_path'), file_position=status.get('file_position'),
                    saved=copy.deepcopy(saved))

    def _native_parent_ended(self):
        if self._native_pause is None or not self.machine.active:
            return
        try:
            if self._pause_identity() != self._native_pause['identity']:
                raise self._error('native paused-print identity changed')
        except self.printer.command_error:
            self._parent_cancelled = True
            self.cancel('native paused print ended or changed')

    def _live(self, require_position=True, native_pause=None):
        if not self.ready or self.printer.is_shutdown():
            raise self._error('Klippy is not ready')
        if not self.filament_qualified:
            raise self._error('filament_qualified=False; material path is unqualified')
        if self.native_mode:
            parent = native_pause if native_pause is not None else self._native_pause
            if self.machine.state == 'CANCELLING' and self._parent_cancelled:
                pass  # Cleanup only; never authorizes another E segment.
            elif parent is not None:
                if self._pause_identity() != parent['identity']:
                    raise self._error('native paused-print identity changed')
            else:
                require_idle_print(self.printer,self.reactor.monotonic())
            self.board.require_motion()
            self.board.require_heating()
            if self.job.machine.state not in JOB_IDLE or self.job.machine.active:
                raise self._error('M02 job owns resources')
            if not native_service_frame(self.printer, self.gcode_move, self.toolhead,
                                        paused_extrusion=parent is not None):
                raise self._error('native filament requires untransformed Cartesian motion')
            if self.job.m04_service_busy():
                raise self._error('another OEM service owns resources')
            # E-only services do not invent an XYZ home or require a Z move.
        else:
            self.job._check_authority(require_position=require_position)
        return self.job._temperatures(self.reactor.monotonic())

    def _check_owner(self):
        if self._parent_cancelled:
            return
        if self._owner_token is None:
            if self.job.machine.state not in JOB_IDLE or self.job.machine.active:
                raise self._error('standalone service lost exclusive job ownership')
        else:
            if self.job.machine.token != self._owner_token:
                raise self._error('paused job session changed')
            if self.machine.state == 'WAIT_PAUSE' or self._cancel_before_capture:
                if self.job.machine.state not in ('PRINTING', 'PAUSING', 'PAUSED'):
                    raise self._error('parent job did not reach an intact pause')
                return
            context = self.job.pause_context
            if self.job.machine.state != 'PAUSED' or context is None:
                raise self._error('material operation requires its intact paused job')
            if (context['token'] != self._owner_token or context['file'] != self._owner_file
                    or context['gcode'] != self._owner_gcode
                    or self.job.sd.get_context() != self._owner_file):
                raise self._error('paused file or G-code context changed')
        if self._captured and self.toolhead.get_position()[:3] != self._anchor:
            raise self._error('XYZ moved during an E-only material operation')

    def _sensor(self, require_material=False):
        if not self.use_sensor:
            return
        inputs = self.board.get_status(self.reactor.monotonic())['inputs']
        if not inputs.get('status_fresh') or inputs.get('filament_module_present') is not True:
            raise self._error('configured filament module is absent or stale')
        if require_material and inputs.get('filament_runout'):
            raise self._error('filament is absent before loading/purge')

    def _guard(self, transport=False):
        parent_cleanup = self.machine.state == 'CANCELLING' and self._parent_cancelled
        temperatures = self._live(require_position=not parent_cleanup)
        if parent_cleanup:
            # M02 may already have legitimately released the shared motors.
            # This branch only drains/discards/restores parser bookkeeping;
            # it never authorizes a new material segment or a position move.
            return temperatures
        self._check_owner()
        self._sensor(transport and self.machine.state in ('LOADING', 'PURGING'))
        measured, actual_target = temperatures['hotend']
        if (self._expected_target is not None and self.machine.state != 'CANCELLING'
                and actual_target != self._expected_target):
            raise self._error('hotend target changed outside material owner')
        ready = (native_temperature_ready(measured,actual_target,self.target,self.hotend)
                 if self.native_mode else actual_target == self.target
                 and measured >= self.hotend.min_extrude_temp and abs(measured-self.target) <= self.tolerance)
        if transport and (not self.hotend.can_extrude or not ready):
            raise self._error('temperature is not ready for the next E segment')
        return temperatures

    def _valid_session(self, token, phase=None):
        return token == self.machine.token and (phase is None or phase == self.machine.phase_id)

    def _check_deadline(self):
        if self.machine.deadline is not None and self.reactor.monotonic() > self.machine.deadline:
            if self.machine.state in WAIT_STATES:
                self.cancel('operator confirmation deadline expired')
                return False
            raise self._error('material deadline expired before actuation')
        return True

    def _set_target(self, target):
        token, phase = self.machine.token, self.machine.phase_id
        if target:
            self._live()
            if not self._check_deadline():
                return False
        self.toolhead.register_lookahead_callback(lambda pt: None)
        if not self._valid_session(token, phase):
            return False
        if target:
            self._live()
            if not self._check_deadline():
                return False
        if self.native_lease is not None:self.native_lease.heat(self.hotend,target)
        else:self.hotend.set_temp(target)
        self._expected_target = target
        self._temperature_stable_since = None
        return True

    def _off(self):
        if self.hotend is not None:
            try:
                if self.native_lease is not None:self.native_lease.heat(self.hotend,0.)
                else:self.hotend.set_temp(0.)
            except Exception:
                logging.exception('M300 filament heater-off')
        self._expected_target = 0.

    def _capture(self):
        token, phase = self.machine.token, self.machine.phase_id
        self._live()
        if self._owner_token is not None:
            context = self.job.pause_context
            if (self.job.machine.state != 'PAUSED' or context is None
                    or context['token'] != self._owner_token):
                raise self._error('pause must finish before material transport')
            self._owner_context = context
            self._owner_file = copy.deepcopy(context['file'])
            self._owner_gcode = copy.deepcopy(context['gcode'])
            self.job.sd.verify_resume(self._owner_file, full=False)
            context['filament_service_required'] = True
            if self.target is None:
                self.target = self._validate_temperature(context['targets']['hotend'])
        self._anchor = list(self.toolhead.get_position()[:3])
        command = self.gcode.create_gcode_command('SAVE_GCODE_STATE', 'SAVE_GCODE_STATE', {'NAME': STATE_NAME})
        self.gcode_move.cmd_SAVE_GCODE_STATE(command)
        self._saved_gcode = copy.deepcopy(self.gcode_move.saved_states[STATE_NAME])
        self._parser_restored = False
        self._captured = True
        self._need_drain = True
        self._idle_saved = self.idle.idle_timeout
        self.job._set_idle(max(self._idle_saved, self.total_timeout + self.move_timeout + 60.))
        if not self._valid_session(token, phase):
            return False
        self._expected_target = self.hotend.get_temp(self.reactor.monotonic())[1]
        return self._set_target(self.target)

    def start(self, operation, temperature=None, length=None, load_length=None, unload_length=None, gcmd=None):
        if getattr(self.job, 'm04_service_busy', lambda: False)():
            raise self._error('another service (calibration, maintenance, fan test, motion or SD) owns resources')
        if operation not in ('LOAD', 'UNLOAD', 'CHANGE'):
            raise self._error('operation must be LOAD, UNLOAD or CHANGE')
        if self.is_busy():
            raise self._error('another material operation is active or faulted')
        plan = self._profile(operation, length, load_length, unload_length)
        state = self.job.machine.state
        native_pause = None
        if self.native_mode and operation == 'CHANGE':
            if state not in JOB_IDLE or self.job.machine.active:
                raise self._error('legacy job owns resources')
            native_pause = dict(identity=self._pause_identity(),
                                target=self.hotend.get_temp(self.reactor.monotonic())[1])
        if operation == 'CHANGE':
            if native_pause is None and state not in ('PRINTING', 'PAUSING', 'PAUSED'):
                raise self._error('CHANGE requires a printing or paused M02 job')
        elif state not in JOB_IDLE | {'PAUSED'}:
            raise self._error('LOAD/UNLOAD requires idle or paused M02')
        if (self.job._cleanup_pending or self.job._resume_checking
                or (state in JOB_IDLE and (self.job._ops or self.job._waiting or self.job._executing))
                or self.job.sd.is_preparing):
            raise self._error('M02 cleanup or file operation still owns resources')
        # Standalone OEM Load/Unload uses 240C. A print-owned CHANGE/M600
        # without TEMP keeps its existing paused-print target selection.
        target = None if temperature is None and operation == 'CHANGE' else self._validate_temperature(
            self.procedure_temperature if temperature is None else temperature)
        if native_pause is not None and temperature is None:
            target = self._validate_temperature(native_pause['target'] if
                native_pause['target'] >= self.hotend.min_extrude_temp else self.procedure_temperature)
        self._live(native_pause=native_pause)
        self._sensor()
        self._owner_token = self.job.machine.token if state not in JOB_IDLE else None
        self._owner_file = self._owner_gcode = self._owner_context = None
        self._parent_cancelled = self._cleanup_pending = False
        self._cancel_before_capture = False
        self._captured = False
        self._parser_restored = False
        self._waiting = self._drain_deadline = self._intent = None
        self._need_drain = False
        self._move_permit = None
        self.target = target
        self._expected_target = None
        self.last_rejection = ''
        context = {'owner_state': state, 'owner_token': self._owner_token,
                   'target': target, 'automatic_resume': False}
        if native_pause is not None:
            context.update(owner_state='PAUSED', owner_token=self.machine.token+1,
                           owner_kind='NATIVE_PAUSE')
        now = self.reactor.monotonic()
        token = self.machine.start(operation, plan, context, now)
        self._native_pause = native_pause
        self._phase_started = now
        try:
            if self.native_lease is not None:
                self.native_lease.acquire(self.toolhead,self.gcode_move,(self.hotend,self.job.bed))
            if self.machine.state == 'WAIT_PAUSE':
                self.job.pause('M03 filament change')
            else:
                self._capture()
        except Exception as exc:
            self._fault('material start failed: ' + str(exc))
            raise
        if self._valid_session(token):
            self.reactor.update_timer(self._timer, self.reactor.NOW)
            if self.native_mode:self.reactor.update_timer(self._watchdog_timer,self.reactor.NOW)
            if gcmd is not None:
                gcmd.respond_info('M300 material operation accepted; explicit confirmations required, no automatic Resume')

    def _advance(self, event, phase_id=None):
        result = self.machine.advance(event, self.machine.token, self.reactor.monotonic(), phase_id=phase_id)
        if not result:
            raise self._error('stale material prompt')
        self._phase_started = self.reactor.monotonic()
        self._temperature_stable_since = None
        self.reactor.update_timer(self._timer, self.reactor.NOW)

    def _check_prompt(self, token, phase_id):
        if (isinstance(token, bool) or not isinstance(token, int)
                or isinstance(phase_id, bool) or not isinstance(phase_id, int)
                or token != self.machine.token or phase_id != self.machine.phase_id):
            raise self._error('stale material session or prompt phase')
        if self.machine.state not in WAIT_STATES:
            raise self._error('operator confirmation is unavailable in ' + self.machine.state)
        self._guard()

    def _ready_temperature(self):
        measured, target = self.job._temperatures(self.reactor.monotonic())['hotend']
        if self.native_mode:
            return self.hotend.can_extrude and native_temperature_ready(measured,target,self.target,self.hotend)
        return (target == self.target and abs(measured-self.target) <= self.tolerance
                and self.hotend.can_extrude and measured >= self.hotend.min_extrude_temp)

    def _request_transport(self, event):
        if self._ready_temperature():
            self._advance(event)
            return
        self._intent = event
        self._advance('reheat')
        self._set_target(self.target)

    def confirm(self, token, phase_id):
        self._check_prompt(token, phase_id)
        state = self.machine.state
        if state == 'WAIT_PURGE':
            self._advance('finish', phase_id)
        else:
            if state == 'WAIT_INSERT':
                self._sensor(require_material=True)
            self._request_transport('inserted' if state == 'WAIT_INSERT' else 'unload_confirmed')

    def purge(self, token, phase_id):
        self._check_prompt(token, phase_id)
        if self.machine.state != 'WAIT_PURGE':
            raise self._error('PURGE requires WAIT_PURGE')
        if self.machine.snapshot()['purge_requests_remaining'] <= 0:
            raise self._error('explicit purge budget exhausted')
        self._sensor(require_material=True)
        self._request_transport('purge')

    def cancel(self, reason='operator', token=None):
        if token is not None and (isinstance(token, bool) or not isinstance(token, int) or token != self.machine.token):
            raise self._error('stale material cancellation token')
        if not self.machine.active:
            return
        previous = self.machine.state
        self.machine.cancel(str(reason), self.reactor.monotonic())
        if previous == 'WAIT_PAUSE' and not self._captured:
            self._cancel_before_capture = True
        if self._owner_token is not None and not self._parent_cancelled:
            self.job.hold_filament_heat_off()
        self._move_permit = self._intent = None
        self._off()
        if previous == 'CANCELLING':
            return
        self._cleanup_pending = True
        self._waiting = self._drain_deadline = None
        self._need_drain = self._captured
        self.reactor.update_timer(self._timer, self.reactor.NOW)

    def parent_cancel(self, reason):
        if self.machine.active:
            self._parent_cancelled = True
            self.cancel('parent job cancelled: ' + str(reason))

    def parent_fault(self, reason):
        if self.machine.active:
            self._fault('parent job fault: ' + str(reason), signal_shutdown=False)

    def _fault(self, reason, signal_shutdown=True):
        was_fault = self.machine.state == 'FAULT'
        self.machine.fail(str(reason), self.reactor.monotonic())
        self._cleanup_pending = True
        self._move_permit = self._waiting = self._intent = self._drain_deadline = None
        self._need_drain = False
        if signal_shutdown and not was_fault:
            from .m300_error_codes import report
            report(self.printer, reason, source='m300_filament', fatal=True)
        if signal_shutdown and not was_fault and not self.printer.is_shutdown():
            self.printer.invoke_async_shutdown('M300 filament fault: ' + str(reason))
        self._off()
        if self.gcode_move is not None:
            self.gcode_move.saved_states.pop(STATE_NAME, None)
        self._saved_gcode = None

    def _begin_drain(self, kind, segment=None):
        token, phase = self.machine.token, self.machine.phase_id
        self.toolhead.get_last_move_time()
        if not self._valid_session(token, phase):
            return False
        self._waiting = (kind, segment)
        self._drain_deadline = self.reactor.monotonic() + self.move_timeout
        return True

    def _temperature_tick(self, now):
        if not self._ready_temperature():
            self._temperature_stable_since = None
            return
        if self._temperature_stable_since is None:
            self._temperature_stable_since = now
        if now - self._temperature_stable_since < self.stable_time:
            return
        was_reheat = self.machine.state == 'REHEATING'
        intent, self._intent = self._intent, None
        self._advance('heated')
        if self.native_mode and not was_reheat and self.machine.mode=='CHANGE':
            self._advance('unload_confirmed')
        if was_reheat and intent is not None:
            self._advance(intent)

    def _wait_tick(self, now):
        if now - self._phase_started >= self.standby_after:
            target = min(self.standby_temperature, self.target)
            if self._expected_target != target:
                self._set_target(target)

    def _transport_tick(self):
        self._guard(transport=True)
        token, phase = self.machine.token, self.machine.phase_id
        segment = self.machine.next_segment(token, self.reactor.monotonic())
        if segment is None:
            self._advance({'LOADING': 'loaded', 'UNLOADING': 'unloaded', 'PURGING': 'purged'}[self.machine.state])
            if self.native_mode and self.machine.mode in ('LOAD','CHANGE') and self.machine.state=='WAIT_PURGE':
                self._advance('finish')
            return
        position = list(self.toolhead.get_position())
        position[3] += segment['delta_e']
        if not all(math.isfinite(value) for value in position):
            raise self._error('non-finite E endpoint')
        self._move_permit = {'token': token, 'phase': phase, 'position': position, 'speed': segment['speed']}
        try:
            if self.native_lease is not None:
                self.native_lease.move(position,segment['speed'],extruder_only=True)
            else:
                self.toolhead.manual_move([None, None, None, position[3]], segment['speed'])
        finally:
            self._move_permit = None
        if self._valid_session(token, phase):
            self._begin_drain('segment', segment)

    def _cleanup(self, success):
        token, phase = self.machine.token, self.machine.phase_id
        self._cleanup_pending = True
        self._off()
        if self._captured and not self._parser_restored:
            if self.gcode_move.saved_states.get(STATE_NAME) != self._saved_gcode:
                raise self._error('saved service G-code context was replaced')
            if not self._parent_cancelled or self.job._homed():
                command = self.gcode.create_gcode_command('RESTORE_GCODE_STATE', 'RESTORE_GCODE_STATE',
                                                         {'NAME': STATE_NAME, 'MOVE': '0'})
                self.gcode_move.cmd_RESTORE_GCODE_STATE(command)
            self.gcode_move.saved_states.pop(STATE_NAME, None)
            self._parser_restored = True
        if not self._valid_session(token, phase):
            return
        if self._owner_token is not None and not self._parent_cancelled:
            self._check_owner()
            context = self.job.pause_context
            if success:
                elapsed = self.reactor.monotonic() - self.job.pause_started
                target = (0. if elapsed >= self.job.heater_off_after else
                          min(self.job.standby_temp, context['targets']['hotend'])
                          if elapsed >= self.job.standby_after else context['targets']['hotend'])
                if not self._set_target(target):
                    return
        if self._idle_saved is not None:
            saved, self._idle_saved = self._idle_saved, None
            if self._owner_token is None or not self._parent_cancelled:
                self.job._set_idle(saved)
        if not self._valid_session(token, phase):
            return
        if success and self._owner_token is not None and not self._parent_cancelled:
            self.job._filament_heat_off = False  # An explicitly requested service finished.
            if self.machine.mode in ('LOAD', 'CHANGE'):
                self.job.pause_context['filament_service_required'] = False
                self.job.pause_context['retracted'] = 0.  # Material explicitly loaded/primed.
        if success and self._native_pause is not None and not self._parent_cancelled:
            if not self._set_target(self._native_pause['target']):
                return
        self._captured = False
        self._saved_gcode = None
        self._advance('completed' if success else 'cancelled')
        self._cleanup_pending = False
        self._expected_target = None
        if self.native_lease is not None:self.native_lease.release()
        self._native_pause = None

    def _watchdog(self, now):
        if not self.ready or self.printer.is_shutdown():
            return self.reactor.NEVER
        if self.machine.active:
            try:
                self._native_parent_ended()
                self._guard()
                self._check_deadline()
                if self._drain_deadline is not None and now > self._drain_deadline:
                    raise self._error('native material queue drain deadline expired')
            except Exception as exc:
                self._fault(str(exc))
        return now + PERIOD if self.ready and (not self.native_mode or self.machine.active) else self.reactor.NEVER

    def _tick(self, now):
        if not self.ready or self.printer.is_shutdown():
            return self.reactor.NEVER
        if not self.machine.active or self._executing:
            return self.reactor.NEVER if self.native_mode and not self.machine.active else now + PERIOD
        try:
            self._native_parent_ended()
            self._guard()
            if not self._check_deadline():
                return now + PERIOD
            if self._waiting is not None:
                if not self.job._queue_drained(now):
                    return now + PERIOD
                kind, segment = self._waiting
                self._waiting = self._drain_deadline = None
                if kind == 'segment':
                    self.machine.ack_segment(segment['id'], segment['token'], now)
            if self.gcode.get_mutex().test():
                return now + PERIOD
            with self.gcode.get_mutex():
                self._executing = True
                try:
                    if self._need_drain:
                        self._need_drain = False
                        self._begin_drain('barrier')
                    elif self.machine.state == 'WAIT_PAUSE':
                        if self.job.machine.state == 'PAUSED':
                            self._advance('paused')
                            self._capture()
                    elif self.machine.state in ('HEATING', 'REHEATING'):
                        self._temperature_tick(now)
                    elif self.machine.state in WAIT_STATES:
                        self._wait_tick(now)
                    elif self.machine.state in TRANSPORT_STATES:
                        self._transport_tick()
                    elif self.machine.state in ('COMPLETING', 'CANCELLING'):
                        self._cleanup(self.machine.state == 'COMPLETING')
                finally:
                    self._executing = False
        except Exception as exc:
            logging.exception('M300 filament phase failure')
            self._fault(str(exc))
        return now + PERIOD if self.ready else self.reactor.NEVER

    def request_ui(self, action, token, phase_id=None):
        try:
            if not self.ready or self.printer.is_shutdown():
                raise self._error('panel action requires a ready host')
            if not self.machine.active or self.machine.state == 'CANCELLING':
                raise self._error('panel action is unavailable in ' + self.machine.state)
            if action == 'CONFIRM':
                self.confirm(token, phase_id)
            elif action == 'PURGE':
                self.purge(token, phase_id)
            elif action == 'CANCEL':
                self.cancel('panel request', token)
            else:
                raise self._error('unsupported material action')
            return {'accepted': True, 'error': None}
        except Exception as exc:
            self.last_rejection = str(exc)
            return {'accepted': False, 'error': str(exc)}

    def get_status(self, now):
        snapshot = self.machine.snapshot(include_plan=False)
        live = self.ready and not self.printer.is_shutdown()
        measured = None
        actual_target = self.hotend.get_temp(now)[1] if self.hotend is not None else 0.
        if self.hotend is not None and not self.board.mcu.is_fileoutput():
            try:
                measured = self.job._temperature('extruder', self.hotend, now)[0]
            except Exception:
                pass
        can_confirm = can_purge = False
        if live and self.machine.state in WAIT_STATES:
            try:
                self._guard()
                can_confirm = True
                can_purge = self.machine.state == 'WAIT_PURGE' and snapshot['purge_requests_remaining'] > 0
            except Exception:
                pass
        return {'version': '0.3.0-LAB_M01_M02_M03', 'model': 'M300_CLASSIC',
                'state': self.machine.state, 'operation': self.machine.mode,
                'session_token': self.machine.token, 'phase_id': self.machine.phase_id,
                'busy': self.is_busy(), 'active': self.machine.active,
                'ready': live, 'installed': self.installed,
                'temperature': measured, 'target': actual_target,
                'requested_target': self.target, 'completed_mm': snapshot['completed_mm'],
                'procedure_temperature': self.procedure_temperature,
                'issued_mm': snapshot['issued_mm'], 'budget_mm': snapshot['plan'].get('total_budget_mm', 0.),
                'remaining_budget_mm': snapshot['remaining_budget'],
                'purge_requests_remaining': snapshot['purge_requests_remaining'],
                'can_confirm': can_confirm, 'can_purge': can_purge,
                'can_cancel': live and self.machine.active and self.machine.state != 'CANCELLING',
                'reason': self.machine.reason or '', 'last_rejection': self.last_rejection,
                'owner_job_token': self._owner_token, 'job_resume_automatic': False,
                'filament_qualified': self.filament_qualified, 'hardware_qualified': False,
                'native_control': self.native_mode,
                'revision': '0.13.16.6-MATERIAL',
                'native_paused_print': self._native_pause is not None,
                'phase_remaining': None if self.machine.deadline is None else max(0., self.machine.deadline-now),
                'history': snapshot['history']}

    def cmd_load(self, gcmd):
        self._command_keys(gcmd, {'TEMP', 'LENGTH'})
        self.start('LOAD', temperature=gcmd.get_float('TEMP', None), length=gcmd.get_float('LENGTH', None), gcmd=gcmd)

    def cmd_unload(self, gcmd):
        self._command_keys(gcmd, {'TEMP', 'LENGTH'})
        self.start('UNLOAD', temperature=gcmd.get_float('TEMP', None), length=gcmd.get_float('LENGTH', None), gcmd=gcmd)

    def cmd_change(self, gcmd):
        self._command_keys(gcmd, {'TEMP', 'LOAD_LENGTH', 'UNLOAD_LENGTH'})
        self.start('CHANGE', temperature=gcmd.get_float('TEMP', None),
                   load_length=gcmd.get_float('LOAD_LENGTH', None), unload_length=gcmd.get_float('UNLOAD_LENGTH', None), gcmd=gcmd)

    def cmd_m600(self, gcmd):
        # The pinned native parser retains the traditional opcode as M=600.
        # It is part of the command itself; every actual argument stays denied.
        parameters = dict(gcmd.get_command_parameters())
        if parameters.get('M') == '600':
            del parameters['M']
        if parameters:
            raise self._error('M600 accepts no parameters; use CHANGE_FILAMENT for explicit values')
        self.start('CHANGE', gcmd=gcmd)

    def cmd_confirm(self, gcmd):
        self._command_keys(gcmd, {'TOKEN', 'PHASE'})
        self.confirm(gcmd.get_int('TOKEN', minval=0), gcmd.get_int('PHASE', minval=0))

    def cmd_purge(self, gcmd):
        self._command_keys(gcmd, {'TOKEN', 'PHASE'})
        self.purge(gcmd.get_int('TOKEN', minval=0), gcmd.get_int('PHASE', minval=0))

    def cmd_cancel(self, gcmd):
        self._command_keys(gcmd, {'TOKEN'})
        self.cancel('G-code FILAMENT_CANCEL', gcmd.get_int('TOKEN', None, minval=0))

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_FILAMENT ' + json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))

    def _command_keys(self, gcmd, allowed):
        unknown = set(gcmd.get_command_parameters()) - allowed
        if unknown:
            raise self._error('unsupported parameters: ' + ', '.join(sorted(unknown)))


def load_config(config):
    return M300Filament(config)
