# SPDX-License-Identifier: GPL-3.0-or-later
"""M04/M07 native PC7 calibration adapter, bounded and default disabled.

Uses the existing [probe] MCU endstop and pinned native HomingMove. It creates
no GPIO/ADC owner, emits no raw steps, and never makes an unknown Z 'homed'.
All XYZ must already be known. Contact results are observations, not offsets.
"""
from .m300_temperature_policy import target_limit
import copy
import json
import logging
import math
from .m300_native_service import (lock_command, unlock_command,
                                  native_service_frame, native_temperature_ready, require_idle_print)
from .m300_native_probe import BoundedProbeToolhead, boundary_z
from .m300_stock_geometry import stock_xy_offsets
from .m300_calibration_state import CalibrationState, CalibrationError, POINTS, finite

PERIOD = .1
JOB_IDLE = {'IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR'}


class M300Calibration:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.job = self.printer.load_object(config, 'm300_job')
        self.board = self.job.board
        self.native_mode = bool(getattr(self.board, 'native_control', False))
        self.nvm = self.printer.load_object(config, 'm300_nvm')
        required = config.getsection('m300_resources').get('require_calibration_workflow', None)
        self.workflow = config.get('workflow', required or 'M04_OBSERVATION')
        if self.workflow not in ('M04_OBSERVATION', 'M07_STOCK'):
            raise config.error('M300 calibration workflow must be M04_OBSERVATION or M07_STOCK')
        if required is not None and self.workflow != required:
            raise config.error('M300 calibration workflow conflicts with required calibration workflow')
        self.qualified = config.getboolean('qualified', False)
        self.safe_z = self._option('safe_z', None, 0., 1000.)
        self.approach_distance = self._option('approach_distance', None, .01, 30.)
        self.release_distance = self._option('release_distance', None, .01, 10.)
        self.search_margin = self._option('probe_search_margin', 0., 0., 2.)
        self.procedure_temperature = self._option('procedure_temperature', 260., 170., 300.)
        self.screw_pitch = self._option('screw_pitch', None, .01, 10.)
        self.center_tolerance = self._option('center_tolerance', None, 0., 5.)
        self.directions = {key: config.get(key + '_positive_direction', None)
                           for key in ('rear_left', 'rear_right', 'front')}
        # OEM 1.3.1 sets F6000 for the XY hop in calibration_probe_one_point.
        stock_xy = self.native_mode and self.workflow == 'M07_STOCK'
        self.travel_speed = self._option('travel_speed', 100. if stock_xy else 10.,
                                         .1, 100. if stock_xy else 50.)
        self.z_speed = self._option('z_speed', 1., .05, 5.)
        self.probe_speed = self._option('probe_speed', .5, .05, 2.)
        self.release_speed = self._option('release_speed', .5, .05, 2.)
        self.min_clearance = self._option('min_clearance', .5, .01, 10.)
        self.move_timeout = self._option('move_timeout', 120., 1., 600.)
        self.heat_timeout = self._option('heat_timeout', 1200., 1., 7200.)
        self.confirm_timeout = self._option('confirm_timeout', 600., 1., 7200.)
        self.total_timeout = self._option('total_timeout', 3600., 1., 28800.)
        self.tolerance = self._option('temperature_tolerance', 2., .1, 10.)
        self.stable_time = self._option('temperature_stable_time', 2., 0., 30.)
        samples = config.getint('samples', 3, minval=1, maxval=9)
        spread = self._option('sample_spread', .05, 0., 1.)
        maximum = config.getint('max_adjustments', 40, minval=1, maxval=40)
        stock_scale = config.getint('stock_steps_per_mm', None)
        retries_option = config.get('max_sample_retries', None)
        retries = config.getint('max_sample_retries', 2, minval=0, maxval=10)
        try:
            if self.workflow == 'M07_STOCK':
                from .m300_leveling_state import LevelingState
                self.machine = LevelingState(samples, spread, self.center_tolerance,
                    self.screw_pitch, self.directions, maximum,
                    stock_steps_per_mm=stock_scale, max_sample_retries=retries)
            else:
                if stock_scale is not None or retries_option is not None:
                    raise CalibrationError('stock_steps_per_mm/max_sample_retries require M07_STOCK')
                self.machine = CalibrationState(samples, spread, self.center_tolerance,
                                                 self.screw_pitch, self.directions, maximum)
            if self.qualified:
                self.machine.validate_profile()
                if None in (self.safe_z, self.approach_distance, self.release_distance):
                    raise CalibrationError('qualified requires explicit safe_z/approach_distance/release_distance')
        except CalibrationError as exc:
            raise config.error('M300 calibration: ' + str(exc))
        # These candidates are audited coordinates, not a measured usable bed.
        # Explicit qualification is required before they can actuate the plate.
        self.points = tuple(POINTS)
        self.xy_offset = (0, 0)
        self.ready = self.installed = self._executing = self._native_active = False
        self._cleanup_pending = False
        self._cancel_generation = 0
        self._committing = False
        self.target, self._expected_hotend, self._stable_since = 0., 0., None
        self._moves = None
        self._pending_point = None
        self._samples = []
        self._wait_until = self._move_deadline = None
        self._permit_move = self._permit_heat = None
        self._native_move = self._native_drip = self._native_set_position = None
        self._native_heaters = {}
        self._ownership_methods, self._ownership_commands = [], []
        self._ownership_callbacks = False
        self._frame_offset = 0.
        self._cal_homing = self._homed_once = False
        self._idle_saved = None
        self.last_rejection = ''
        self.toolhead = self.hotend = self.bed = self.endstop = None
        self._timer = self.reactor.register_timer(self._tick)
        self._watch_timer = self.reactor.register_timer(self._watchdog)
        self.board.get_mcu().register_config_callback(self._audit_config)
        for event, callback in (('klippy:connect', self._connect),
                                ('klippy:ready', self._ready),
                                ('klippy:shutdown', self._shutdown),
                                ('klippy:disconnect', self._shutdown),
                                ('gcode:request_restart', self._shutdown),
                                ('stepper_enable:motor_off', self._motor_off),
                                ('homing:home_rails_begin', self._foreign_home)):
            self.printer.register_event_handler(event, callback)
        for name, fn in (('ZORTRAX_CALIBRATE', self.cmd_start),
                         ('ZORTRAX_CALIBRATION_CONFIRM', self.cmd_confirm),
                         ('ZORTRAX_CALIBRATION_CANCEL', self.cmd_cancel)):
            self.gcode.register_command(name, fn)
        self.gcode.register_command('ZORTRAX_CALIBRATION_STATUS', self.cmd_status, when_not_ready=True)
        webhooks = self.printer.lookup_object('webhooks', None)
        if self.workflow == 'M07_STOCK':
            if not callable(getattr(webhooks, 'register_endpoint', None)):
                raise config.error('M07 requires native webhook cancellation capability')
            webhooks.register_endpoint('m300/calibration/cancel', self._webhook_cancel)

    def _error(self, message):
        prefix = 'M300 calibration: '
        message = str(message)
        return self.printer.command_error(prefix + message.removeprefix(prefix))

    def _option(self, name, default, lo, hi):
        value = self.config.getfloat(name, default, minval=lo, maxval=hi)
        if value is not None and not math.isfinite(value):
            raise self.config.error('M300 calibration %s must be finite' % name)
        return value

    def _bind(self):
        self.job._bind_resources()
        self.toolhead, self.hotend, self.bed = self.job.toolhead, self.job.hotend, self.job.bed
        self.probe = self.printer.lookup_object('probe')
        # Pinned 2026 upstream exposes the one actual PC7 mcu_endstop here.
        # The Z virtual endstop is a different adapter with no steppers.
        wrapper = getattr(self.probe, 'mcu_probe', None)
        self.endstop = getattr(wrapper, 'mcu_endstop', None)
        if self.endstop is None:
            raise self.config.error('M300 calibration requires pinned native [probe] endstop')

    def _audit_config(self):
        self._bind()
        hardware = getattr(self.job.board, 'hardware', None)
        factory_scale = hardware.selected_z_steps() if hardware is not None else None
        if self.workflow == 'M07_STOCK' and factory_scale is not None:
            # The factory scale and the native step generator share one source.
            # No existing calibration result or configuration file is rewritten.
            self.machine.stock_steps_per_mm = factory_scale
        if self.workflow == 'M07_STOCK' and self.printer.lookup_object('m300_motion', None) is None:
            raise self.config.error('M07 calibration requires the M06 motion owner')
        probe_config = self.config.getsection('probe')
        for option in ('activate_gcode', 'deactivate_gcode'):
            if probe_config.get(option, '').strip():
                raise self.config.error('M300 fixed contact requires empty probe ' + option)
        if any(self.probe.get_offsets()[i] != 0. for i in (0, 1)):
            raise self.config.error('M300 nozzle contact requires zero native XY probe offsets')
        if self.qualified:
            self._geometry()
            if self.workflow == 'M07_STOCK':
                steppers = self.endstop.get_steppers()
                if (len(steppers) != 1 or steppers[0].get_name() != 'stepper_z'
                        or abs(steppers[0].get_step_dist() * self.machine.stock_steps_per_mm - 1.) > 1.e-9):
                    raise self.config.error('M07 stock_steps_per_mm must match the native Z step distance')
                origin = self.probe.get_offsets()[2] * self.machine.stock_steps_per_mm
                if not math.isfinite(origin) or abs(origin-round(origin)) > 1.e-6:
                    raise self.config.error('M07 probe.z_offset must lie on the qualified Z count grid')
                margin = self.search_margin * self.machine.stock_steps_per_mm
                if abs(margin-round(margin)) > 1.e-6:
                    raise self.config.error('M07 probe_search_margin must lie on the native Z count grid')

    def _geometry(self):
        self.machine.validate_profile()
        if None in (self.safe_z, self.approach_distance, self.release_distance):
            raise self._error('safe_z/approach_distance/release_distance are not qualified')
        minimum, maximum = self.job._axis_bounds()
        if not minimum[2]+self.min_clearance < self.safe_z <= maximum[2]:
            raise self._error('safe_z outside axis limits/clearance')
        if self.release_distance < self.min_clearance:
            raise self._error('release_distance must cover min_clearance')
        if self.search_margin and (not self.native_mode or self.workflow != 'M07_STOCK'):
            raise self._error('probe_search_margin requires native M07')
        if self.safe_z + self.search_margin > maximum[2]:
            raise self._error('safe_z plus probe search margin outside native Z range')
        if self.native_mode and self.approach_distance < self.safe_z + self.search_margin - minimum[2]:
            raise self._error('approach_distance must cover safe_z plus probe search margin')
        if self.approach_distance/self.probe_speed + 1. >= self.move_timeout:
            raise self._error('probe distance/speed exceeds move_timeout')
        if self.release_distance/self.release_speed + 1. >= self.move_timeout:
            raise self._error('release distance/speed exceeds move_timeout')
        for point in self.points:
            if not all(minimum[i] <= point[i] <= maximum[i] for i in (0, 1)):
                raise self._error('calibration point outside axis bounds')
        result = dict(points=[list(p) for p in self.points], safe_z=self.safe_z,
                    approach_distance=self.approach_distance,
                    release_distance=self.release_distance, screw_pitch=self.screw_pitch,
                    positive_directions=dict(self.directions),
                    center_tolerance=self.center_tolerance, sample_spread=self.machine.sample_spread)
        if self.workflow == 'M07_STOCK':
            result.update(workflow=self.workflow, stock_steps_per_mm=self.machine.stock_steps_per_mm,
                          contract_version=self.machine.contract_version,
                          stock_coefficient=self.machine.get_status()['stock_coefficient'])
        if self.native_mode:
            result['probe_search_margin'] = self.search_margin
            result['nominal_points'] = [list(p) for p in POINTS]
            result['sampling_xy_offset'] = list(self.xy_offset)
        return result

    def _connect(self):
        self._bind()
        self._native_move = self.toolhead.move
        self._native_drip = self.toolhead.drip_move
        self._native_set_position = self.toolhead.set_position
        if getattr(self.job.board, 'native_control', False):
            self.installed = True
            return
        self._install_ownership()

    def _own_method(self, obj, name, replacement):
        self._ownership_methods.append((obj, name, getattr(obj, name), replacement))
        setattr(obj, name, replacement)

    def _install_ownership(self):
        if self._ownership_methods:
            return
        def move(position, speed):
            if self.is_busy() and not self._cal_homing:
                permit, self._permit_move = self._permit_move, None
                if permit != (self.machine.token, self.machine.phase_id, list(position), speed):
                    raise self._error('calibration owns motion; external move refused')
                self._guard(require_temperature=True)
            return self._native_move(position, speed)
        self._own_method(self.toolhead, 'move', move)
        for name, original in (('drip_move', self._native_drip),
                               ('set_position', self._native_set_position)):
            def locked(*args, original=original, name=name, **kwargs):
                if self.is_busy() and not self._cal_homing:
                    raise self._error('calibration owns position; external ' + name + ' refused')
                return original(*args, **kwargs)
            self._own_method(self.toolhead, name, locked)
        for heater in (self.hotend, self.bed):
            original = heater.set_temp
            self._native_heaters[heater] = original
            def set_temp(value, heater=heater, original=original):
                if self.is_busy() and not (self._cal_homing and value == self.target):
                    permit, self._permit_heat = self._permit_heat, None
                    if permit != (heater, value):
                        if value == 0.:
                            self.cancel('external heater-off')
                        else:
                            raise self._error('calibration owns heaters')
                return original(value)
            self._own_method(heater, 'set_temp', set_temp)
        self._native_parser_move = self.job.gcode_move.move_with_transform
        self._bind_parser()
        blocked = ('G0', 'G1', 'G28', 'G90', 'G91', 'G92', 'M82', 'M83', 'M204',
                   'M220', 'M221', 'SAVE_GCODE_STATE', 'RESTORE_GCODE_STATE',
                   'SET_GCODE_OFFSET', 'SET_KINEMATIC_POSITION', 'FORCE_MOVE',
                   'STEPPER_BUZZ', 'SET_VELOCITY_LIMIT', 'PROBE', 'PROBE_ACCURACY',
                   'PROBE_CALIBRATE', 'BED_MESH_CALIBRATE', 'SCREWS_TILT_CALCULATE',
                   'BED_MESH_CLEAR', 'BED_MESH_PROFILE', 'BED_MESH_OFFSET',
                   'Z_TILT_ADJUST', 'QUAD_GANTRY_LEVEL', 'PID_CALIBRATE',
                   'M109', 'M190', 'TEMPERATURE_WAIT', 'SAVE_CONFIG',
                   'SDCARD_PRINT_FILE', 'M23', 'M24', 'PAUSE', 'RESUME')
        for name in blocked:
            def guarded(gcmd,name=name):
                raise self._error('calibration owns resources; ' + name + ' refused')
            record=lock_command(self.gcode,name,guarded)
            if record is not None:self._ownership_commands.append(record)
        if not self._ownership_callbacks:
            for name in self.job.steppers.get_steppers():
                self.job.steppers.lookup_enable(name).register_state_callback(self._enable_changed)
            self._ownership_callbacks = True
        self.installed = True

    def _release_ownership(self):
        if not self.native_mode or not self._ownership_methods:
            return
        for record in self._ownership_commands:
            unlock_command(self.gcode,record)
        self._ownership_commands.clear()
        for obj, name, original, guarded in reversed(self._ownership_methods):
            if getattr(obj, name) == guarded:
                setattr(obj, name, original)
        self._ownership_methods.clear()
        self.job.gcode_move.move_with_transform = self._native_parser_move
        self._native_heaters.clear()

    def _bind_parser(self):
        move = self.job.gcode_move.move_with_transform
        if move == self._native_move:
            self.job.gcode_move.move_with_transform = self.toolhead.move

    def _ready(self):
        if getattr(self.job.board, 'native_control', False):
            self.ready = True
            self.reactor.update_timer(self._timer, self.reactor.NOW)
            self.reactor.update_timer(self._watch_timer, self.reactor.NOW)
            return
        self._bind_parser()
        self.ready = True
        self.reactor.update_timer(self._timer, self.reactor.NOW)
        self.reactor.update_timer(self._watch_timer, self.reactor.NOW)

    def _shutdown(self, *args):
        self.ready = False
        if self.is_busy():
            self._fault('shutdown/disconnect/restart invalidated calibration', shutdown=False)
        self.reactor.update_timer(self._timer, self.reactor.NEVER)
        self.reactor.update_timer(self._watch_timer, self.reactor.NEVER)

    def _motor_off(self, *args):
        if self.machine.active:
            self._fault('motors disabled; calibration position lost')

    def _enable_changed(self, print_time, enabled):
        if not enabled:
            self._motor_off()

    def _foreign_home(self, *args):
        if self.machine.active and not self._cal_homing:
            self._fault('foreign homing during calibration')

    def is_busy(self):
        return bool(self.machine.active or self.machine.state == 'FAULT'
                    or self._executing or self._cleanup_pending or self._committing)

    def _peer_guard(self):
        now = self.reactor.monotonic()
        if self.native_mode:
            require_idle_print(self.printer,now)
        try:
            status = self.job.get_status(now)
        except Exception as exc:
            raise self._error('job ownership status unavailable: ' + str(exc))
        if (not isinstance(status, dict) or status.get('state') not in JOB_IDLE
                or status.get('busy') is not False):
            raise self._error('job owns resources')
        for name in ('m300_filament', 'm300_maintenance', 'm300_sd', 'm300_motion', 'm300_fans', 'm300_thermal'):
            if name == 'm300_motion' and self._cal_homing:
                continue
            obj = self.printer.lookup_object(name, None)
            if obj is not None:
                try:
                    status = obj.get_status(now)
                except Exception as exc:
                    raise self._error(name + ' ownership status unavailable: ' + str(exc))
                if (not isinstance(status, dict) or status.get('busy') is not False
                        or not isinstance(status.get('state'), str) or not status['state'].strip()
                        or status['state'].upper() in ('FAULT', 'SLEEP', 'SLEEPING')):
                    raise self._error(name + ' owns resources')

    def _guard(self, require_temperature=False):
        if not self.ready or not self.qualified or self.printer.is_shutdown():
            raise self._error('not ready/qualified or printer shutdown')
        if self.native_mode:
            # Native M07 owns its own profile. Enabling leveling does not enable
            # the separately unqualified legacy M02 print/load workflows.
            self.board.require_motion()
            self.board.require_heating()
            if not native_service_frame(self.printer, self.job.gcode_move, self.toolhead):
                raise self._error('native M07 requires untransformed Cartesian motion')
            if self._homed_once and not self._cal_homing:
                self.job._check_position()
        else:
            self.job._check_authority(require_position=True)
        self._peer_guard()
        now = self.reactor.monotonic()
        readings = self.job._temperatures(now)
        if self.machine.active:
            if (readings['hotend'][1] != self._expected_hotend
                    or readings['bed'][1] != 0.):
                raise self._error('temperature target changed outside calibration')
            ready = (native_temperature_ready(*readings['hotend'],self.target,self.hotend)
                     if self.native_mode else abs(readings['hotend'][0]-self.target) <= self.tolerance)
            if require_temperature and not ready:
                raise self._error('nozzle temperature left calibration band')
            if now-self.machine.started > self.total_timeout:
                raise self._error('total calibration deadline exceeded')
        return readings

    def _heat(self, heater, value):
        self._permit_heat = (heater, value)
        try:
            heater.set_temp(value)
        finally:
            self._permit_heat = None

    def _off(self):
        self._expected_hotend = 0.
        for heater in (self.hotend, self.bed):
            if heater is not None:
                try:
                    self._heat(heater, 0.)
                except Exception:
                    logging.exception('M300 calibration heater cleanup')

    def start(self, temperature=None):
        generation = self._cancel_generation
        try:
            if self.is_busy():
                raise self._error('busy or latched fault')
            if self.native_mode:
                self._homed_once = False
                self.xy_offset = stock_xy_offsets(int(self.reactor.monotonic()*1000) & 0xffffffff)
                self.points = tuple((x+self.xy_offset[0], y+self.xy_offset[1]) for x,y in POINTS)
            self._bind()
            self._guard()
            self._geometry()
            self.target = finite(self.procedure_temperature if temperature is None else temperature,
                                 'temperature', self.hotend.min_extrude_temp, target_limit(self.hotend))
            queued, current, empty = self.toolhead.check_busy(self.reactor.monotonic())
            if not empty or queued > current:
                raise self._error('calibration requires an empty motion queue')
            if self.nvm.is_busy():
                raise self._error('NVM write in progress')
            if self.native_mode:
                def check_clearance():
                    if generation != self._cancel_generation:
                        raise self._error('calibration start cancelled during Z clearance')
                    self._guard()
                self.printer.lookup_object('m300_motion').ensure_xy_clearance(check_clearance)
            # Persistent contact after the Z-only clearance cannot enter
            # heating, homing XY or the calibration contact sequence.
            # The endstop query can yield: repeat all preconditions afterwards.
            contact = self.endstop.query_endstop(self.toolhead.get_last_move_time())
            if self.workflow == 'M07_STOCK' and generation != self._cancel_generation:
                raise self._error('calibration start cancelled during contact preflight')
            self._guard()
            if self.is_busy() or self.nvm.is_busy():
                raise self._error('resources changed during initial contact check')
            queued, current, empty = self.toolhead.check_busy(self.reactor.monotonic())
            if not empty or queued > current:
                raise self._error('motion queue changed during initial contact check')
            if contact:
                raise self._error('INITIAL_ACTIVE: release contact before calibration')
            token = self.machine.start(self.reactor.monotonic())
            self._homed_once = False
            if self.native_mode:
                self._install_ownership()
            self._moves = self._pending_point = None
            self._stable_since = self._wait_until = self._move_deadline = None
            self._off()
            # Keep the native idle watchdog beyond each explicit confirmation
            # deadline; restore it after finishing, not by inventing a homed pose.
            self._idle_saved = self.job.idle.idle_timeout
            self.job.idle.idle_timeout = max(self._idle_saved, self.total_timeout + 60.)
            if self.native_mode:
                self.reactor.update_timer(self._timer, self.reactor.NOW)
                self.reactor.update_timer(self._watch_timer, self.reactor.NOW)
                # The stock wizard heats first, then asks the hot-head and
                # three-knob questions. Starting the procedure is the heat
                # request; neither of those later confirmations is skipped.
                self.machine.confirm(token, self.machine.phase_id, self.reactor.monotonic())
                self._expected_hotend = self.target
                self._heat(self.hotend, self.target)
            self._present()
            return token
        except (CalibrationError, self.printer.command_error) as exc:
            self.last_rejection = str(exc)
            raise self._error(str(exc))

    def confirm(self, token, phase):
        if self._committing:
            raise self._error('calibration commit already in progress')
        try:
            self.machine.check(token, phase)
            self._guard(require_temperature=self.machine.state in
                        ('WAIT_WARNING', 'WAIT_TIGHTEN', 'ADJUST', 'WAIT_RETRY'))
            if self.native_mode and self.machine.state == 'WAIT_WARNING':
                self.machine._phase('HOMING', self.reactor.monotonic())
                self._present()
                try:
                    self._home_for_leveling()
                    self.machine.check(token)
                    self.machine._phase('WAIT_TIGHTEN', self.reactor.monotonic())
                    self._present()
                except Exception as exc:
                    self._fault(str(exc))
                    raise
                return self.get_status(self.reactor.monotonic())
            if self.native_mode and self.machine.state == 'WAIT_TIGHTEN':
                # Keep the pure M07 measurement/event ledger unchanged.
                self.machine.state = 'HEATING'
                self.machine.heated(token, self.reactor.monotonic())
                self._present()
                return self.get_status(self.reactor.monotonic())
            action = self.machine.confirm(token, phase, self.reactor.monotonic())
            if action == 'HEAT':
                self._expected_hotend = self.target
                self._heat(self.hotend, self.target)
                self._stable_since = None
            elif action == 'COMMIT':
                # NVM stages and publishes in the native worker. Keep this
                # session exclusive across yields and recheck before COMPLETE.
                queued, current, empty = self.toolhead.check_busy(self.reactor.monotonic())
                if not empty or queued > current:
                    raise self._error('motion queue has not drained')
                record = self.get_commit_observation(token, phase)
                self._committing = True
                try:
                    self.nvm.commit_calibration(record, token, phase)
                    self.machine.check(token, phase)
                    self._guard()
                    self.machine.complete(token, phase, self.reactor.monotonic())
                    self._finish_cleanup()
                finally:
                    self._committing = False
            return self.get_status(self.reactor.monotonic())
        except CalibrationError as exc:
            if self.machine.state == 'FAULT':
                self._fault(str(exc))
            raise self._error(str(exc))

    def get_commit_observation(self, token, phase):
        """Read-only complete result for the NVM service's exact-owner check."""
        self.machine.check(token, phase)
        self._guard()
        queued, current, empty = self.toolhead.check_busy(self.reactor.monotonic())
        if not empty or queued > current:
            raise self._error('motion queue has not drained')
        return self.machine.observation(self.nvm.store.identity, self._geometry())

    def cancel(self, reason='user cancelled', token=None, phase=None):
        if token is not None:
            try:
                self.machine.check(token, phase)
            except CalibrationError as exc:
                raise self._error(str(exc))
        if self.workflow == 'M07_STOCK':
            self._cancel_generation += 1
        if not self.machine.active and not self._cleanup_pending:
            return
        active_native = self._native_active or self._cal_homing
        if self.workflow == 'M07_STOCK':
            queued, current, empty = self.toolhead.check_busy(self.reactor.monotonic())
            active_native = active_native or not empty or queued > current
        self.machine.terminate(reason, self.reactor.monotonic(), fault=active_native)
        self._moves = None
        self._cleanup_pending = True
        self._off()
        if active_native:
            self.printer.invoke_async_shutdown('M300 calibration cancelled during native contact move')

    def _fault(self, reason, shutdown=True):
        if self.machine.state == 'FAULT' and self.machine.reason:
            reason = self.machine.reason
        self.machine.terminate(reason, self.reactor.monotonic(), fault=True)
        from .m300_error_codes import report
        report(self.printer, reason, source='m300_calibration', fatal=shutdown)
        self._moves = None
        self._cleanup_pending = True
        self._off()
        if shutdown and not self.printer.is_shutdown():
            self.printer.invoke_async_shutdown('M300 calibration: ' + str(reason))

    def _finish_cleanup(self):
        self._off()
        if self._frame_offset:
            if not self.printer.is_shutdown():
                position = self.toolhead.get_position()
                position[2] -= self._frame_offset
                minimum, maximum = self.job._axis_bounds()
                if not minimum[2] <= position[2] <= maximum[2]:
                    raise self._error('cannot restore leveling frame within native Z bounds')
                self._native_set_position(position)
            self._frame_offset = 0.
        if self._idle_saved is not None:
            self.job.idle.idle_timeout = self._idle_saved
            self._idle_saved = None
        self.job.gcode_move.reset_last_position()
        self._cleanup_pending = False
        self._release_ownership()

    def _present(self):
        # One presenter owns OLED and Fluidd. No action is auto-confirmed.
        procedures = self.printer.lookup_object('m300_procedures', None)
        if procedures is not None:
            self.reactor.update_timer(procedures.timer, self.reactor.NOW)

    def _home_for_leveling(self):
        self._cal_homing = self._executing = True
        self._present()
        try:
            self.printer.lookup_object('m300_motion').home_oem(self.points[2])
        finally:
            self._cal_homing = self._executing = False
        self._guard()
        self._homed_once = True
        # The known, freshly homed position is translated for this session
        # only. Native axis limits are never edited. One millimetre of bounded
        # contact search below the home reference avoids stopping at Z0 before
        # the electrical contact is sampled. Results are translated back.
        position = self.toolhead.get_position()
        position[2] += self.search_margin
        self._native_set_position(position)
        self._frame_offset = self.search_margin
        self.job.gcode_move.reset_last_position()

    def _queue_move(self, position, speed):
        self._guard(require_temperature=True)
        minimum, maximum = self.job._axis_bounds()
        if (len(position) != 4 or any(not math.isfinite(x) for x in position)
                or position[3] != self.toolhead.get_position()[3]
                or any(not minimum[i] <= position[i] <= maximum[i] for i in range(3))):
            raise self._error('calibration move outside qualified geometry')
        self._permit_move = (self.machine.token, self.machine.phase_id, list(position), speed)
        try:
            self.toolhead.move(list(position), speed)
        finally:
            self._permit_move = None
        self._wait_until = self.toolhead.get_last_move_time()
        self._move_deadline = self.reactor.monotonic() + self.move_timeout

    def _query_contact(self):
        self._guard(require_temperature=True)
        value = self.endstop.query_endstop(self.toolhead.get_last_move_time())
        self._guard(require_temperature=True)
        return bool(value)

    def _native_boundary_z(self, value):
        """Reconcile arithmetic roundoff at an axis boundary, never a step.

        Native HomingMove reconstructs e.g. -5.55e-17 for count zero after
        successive samples. Leave global bounds strict; only this retained
        native capability may normalize a value within eight floating ULPs.
        """
        minimum, maximum = self.job._axis_bounds()
        return boundary_z(value, (minimum[2],maximum[2]), self._error)

    def _native_contact(self, target, speed, triggered):
        from . import homing
        token, phase = self.machine.token, self.machine.phase_id
        def check():
            self.machine.check(token,phase)
            self._guard(require_temperature=True)
        proxy = BoundedProbeToolhead(self.toolhead,target,speed,check,
            self._native_drip,self._native_set_position,self._native_boundary_z,self._error)
        native = homing.HomingMove(self.printer, [(self.endstop, 'm300_contact')], toolhead=proxy)
        if not native.get_mcu_endstops():
            raise self._error('native PC7 probe has no Z stepper')
        self._native_active = True
        self._move_deadline = self.reactor.monotonic() + self.move_timeout
        try:
            result = native.homing_move(target, speed, probe_pos=True,
                                        triggered=triggered, check_triggered=True)
            if self.workflow == 'M07_STOCK':
                result = list(result)
                result[2] = self._native_boundary_z(result[2])
            self.machine.check(token, phase)
            self._guard(require_temperature=True)
            if native.check_no_movement() is not None:
                raise self._error('contact transition occurred without motion')
            if self.reactor.monotonic() > self._move_deadline:
                raise self._error('native contact deadline exceeded')
            return result
        finally:
            self._native_active = False
            self._move_deadline = None

    def _sample(self):
        token, phase = self.machine.token, self.machine.phase_id
        if self._query_contact():
            raise self._error('INITIAL_ACTIVE: contact must be released before approach')
        position = self.toolhead.get_position()
        minimum, maximum = self.job._axis_bounds()
        target = list(position)
        target[2] = max(minimum[2], position[2]-self.approach_distance)
        if target[2] >= position[2]:
            raise self._error('no permitted approach travel remains')
        measured = self._native_contact(target, self.probe_speed, True)
        if not self._query_contact():
            raise self._error('contact unstable after approach')
        z = finite(measured[2], 'measured Z', minimum[2], maximum[2])
        if z > self.safe_z+self._frame_offset-self.min_clearance:
            raise self._error('contact leaves insufficient safe_z clearance')
        target = self.toolhead.get_position()
        target[2] += self.release_distance
        if target[2] > maximum[2]:
            raise self._error('release endpoint outside axis limit')
        self._native_contact(target, self.release_speed, False)
        # HomingMove stops at the first opening edge, not at its target. On
        # the physical HW05 trace that edge was only 59 counts (0.1475 mm)
        # from contact and PC7 closed again before the next query. Complete
        # the already bounded retract to contact + release_distance before
        # requiring a stable opening. Never extend the search or axis limits.
        self.machine.check(token, phase)
        self._queue_move(target, self.release_speed)
        try:
            self.toolhead.dwell(.050)
            self.toolhead.wait_moves()
            self.machine.check(token, phase)
            self._guard(require_temperature=True)
            if self.reactor.monotonic() > self._move_deadline:
                raise self._error('release movement deadline exceeded')
        finally:
            self._wait_until = self._move_deadline = None
        if self._query_contact():
            raise self._error('NO_RELEASE: PC7 remains active')
        self.machine.check(token, phase)
        return z - self._frame_offset

    def _point_steps(self, point):
        position = self.toolhead.get_position()
        position[2] = self.safe_z + self._frame_offset
        yield ('move', position, self.z_speed)
        yield ('released',)
        position = list(position)
        position[:2] = self.points[point]
        yield ('move', position, self.travel_speed)
        for _ in range(self.machine.samples):
            yield ('sample',)
        position = self.toolhead.get_position()
        position[2] = self.safe_z + self._frame_offset
        yield ('move', position, self.z_speed)
        yield ('result',)

    def _tick(self, eventtime):
        if not self.ready:
            return self.reactor.NEVER
        if self._executing:
            return eventtime + PERIOD
        try:
            if self._cleanup_pending:
                queued, current, empty = self.toolhead.check_busy(eventtime)
                if empty and queued <= current:
                    self._finish_cleanup()
                return eventtime + PERIOD
            if not self.machine.active:
                return self.reactor.NEVER if self.native_mode else eventtime + PERIOD
            self._guard(require_temperature=self.machine.state in ('PROBING', 'ADJUST', 'WAIT_RETRY'))
            if self.machine.state == 'HEATING':
                temperature = self.job._temperatures(eventtime)['hotend'][0]
                if (native_temperature_ready(temperature,self._expected_hotend,self.target,self.hotend)
                        if self.native_mode else abs(temperature-self.target) <= self.tolerance):
                    if self._stable_since is None:
                        self._stable_since = eventtime
                    if eventtime-self._stable_since >= self.stable_time:
                        if self.native_mode:
                            self.machine._phase('WAIT_WARNING', eventtime)
                        else:
                            self.machine.heated(self.machine.token, eventtime)
                        self._present()
                else:
                    self._stable_since = None
                return eventtime + PERIOD
            if self.machine.state != 'PROBING':
                return eventtime + PERIOD
            if self._wait_until is not None:
                queued, current, empty = self.toolhead.check_busy(eventtime)
                if not empty or current < self._wait_until:
                    if eventtime > self._move_deadline:
                        raise self._error('motion drain deadline exceeded')
                    return eventtime + PERIOD
                self._wait_until = self._move_deadline = None
            if self._moves is None:
                self._pending_point = self.machine.next_point
                self._samples = []
                self._moves = self._point_steps(self._pending_point)
            step = next(self._moves)
            self._executing = True
            token, phase = self.machine.token, self.machine.phase_id
            if step[0] == 'move':
                self._queue_move(step[1], step[2])
            elif step[0] == 'sample':
                self._samples.append(self._sample())
            elif step[0] == 'released':
                if self._query_contact():
                    raise self._error('INITIAL_ACTIVE: contact active at safe_z; XY move refused')
            else:
                self.machine.measured(token, phase, self._pending_point,
                                      self._samples, self.reactor.monotonic())
                self._moves = None
                if self.machine.state == 'REVIEW':
                    self._off()
                    self.job.gcode_move.reset_last_position()
        except Exception as exc:
            self._fault(str(exc))
        finally:
            self._executing = False
        return eventtime + PERIOD

    def _watchdog(self, eventtime):
        if not self.ready:
            return self.reactor.NEVER
        if self.native_mode and not self.machine.active:
            return self.reactor.NEVER
        if self.machine.active:
            try:
                self._guard(require_temperature=self.machine.state in ('PROBING', 'ADJUST', 'WAIT_RETRY'))
                elapsed = eventtime-self.machine.phase_started
                if self.machine.state == 'HEATING' and elapsed > self.heat_timeout:
                    raise self._error('heating deadline exceeded')
                if self.machine.state in ('WAIT_PREPARE', 'WAIT_WARNING', 'WAIT_TIGHTEN', 'ADJUST', 'WAIT_RETRY', 'REVIEW') and elapsed > self.confirm_timeout:
                    self.cancel('operator confirmation timeout')
                if self._move_deadline is not None and eventtime > self._move_deadline:
                    raise self._error('native/motion deadline exceeded')
            except Exception as exc:
                self._fault(str(exc))
        return eventtime + PERIOD

    def get_status(self, eventtime):
        result = self.machine.get_status()
        result.update(busy=self.is_busy(), ready=self.ready, installed=self.installed,
                      workflow=self.workflow, calibration_api_version=1,
                      model='M300_CLASSIC', qualified=self.qualified,
                      hardware_qualified=False, target=self._expected_hotend,
                      xy_travel_speed_mm_s=self.travel_speed,
                      z_lift_speed_mm_s=self.z_speed, z_probe_speed_mm_s=self.probe_speed,
                      z_release_speed_mm_s=self.release_speed,
                      requested_target=self.target, last_rejection=self.last_rejection,
                      can_confirm=self.ready and self.machine.state in ('WAIT_PREPARE', 'WAIT_WARNING', 'WAIT_TIGHTEN', 'ADJUST', 'WAIT_RETRY', 'REVIEW'),
                      can_cancel=self.ready and self.machine.active)
        if self.native_mode:
            result.update(revision='0.13.16.6-EN-OEM-VALIDATED',
                          procedure_temperature=self.procedure_temperature,
                          probe_search_margin=self.search_margin,
                          measurement_frame_offset=self._frame_offset,
                          automatic_homing=True, legacy_job_enabled=self.job.workflow_qualified)
            result['measurement_stage'] = self.machine.stage
            result['sampling_xy_offset'] = list(self.xy_offset)
            if self._cal_homing:
                result['state'] = result['prompt'] = 'HOMING'
        return result

    def _webhook_cancel(self, request):
        token = request.get('token', None)
        phase = request.get('phase', None)
        if phase is not None and (type(phase) is not int or phase < 0):
            raise self._error('phase must be a nonnegative integer')
        self.cancel('operator webhook cancel', token=token, phase=phase)
        request.send(self.get_status(self.reactor.monotonic()))

    def cmd_start(self, gcmd):
        self.start(gcmd.get_float('TEMP', None))
        self.cmd_status(gcmd)

    def cmd_confirm(self, gcmd):
        self.confirm(gcmd.get('TOKEN'), gcmd.get_int('PHASE', minval=0))
        self.cmd_status(gcmd)

    def cmd_cancel(self, gcmd):
        self.cancel('operator cancelled', gcmd.get('TOKEN', None), gcmd.get_int('PHASE', None))
        self.cmd_status(gcmd)

    def cmd_status(self, gcmd):
        gcmd.respond_info(json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))


def load_config(config):
    return M300Calibration(config)
