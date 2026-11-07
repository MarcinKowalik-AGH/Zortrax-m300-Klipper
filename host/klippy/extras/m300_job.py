# SPDX-License-Identifier: GPL-3.0-or-later
"""M300 M02 job lifecycle on native Klippy resources.

No automatic ARM, raw steps, second ADC owner, or flash writes.
Qualified M04 binary input is fully compiled and checked before native feeding.
Temperature waits and ordinary park/return sequences advance from reactor ticks.
Native contact homing is optional and separately qualified; its cancellation
uses shutdown because native homing cannot be safely resumed halfway through.
"""
from collections import deque
import copy
import json
import logging
import math

from .m300_job_state import JobState, JobStateError, ACTIVE_STATES, bounded_park
from .m300_job_sd import JobSD, PreparationCancelled

PERIOD = .100
TERMINAL = {'IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR', 'FAULT'}


class M300Job:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.board = self.printer.load_object(config, 'm300_mcu')
        self.pause_resume = self.printer.load_object(config, 'pause_resume')
        self.workflow_qualified = config.getboolean('workflow_qualified', False)
        self.binary_zcode_qualified = config.getboolean('binary_zcode_qualified', False)
        self.homing_mode = config.get('homing_mode', 'require_homed')
        if self.homing_mode not in ('require_homed', 'native_contact'):
            raise config.error('M300 job homing_mode must be require_homed or native_contact')
        self.contact_homing_qualified = config.getboolean('contact_homing_qualified', False)
        self.park_xy = (self._option('park_x', 0., -1000., 1000.),
                        self._option('park_y', 0., -1000., 1000.))
        self.home_xy = (self._option('home_x', 150., -1000., 1000.),
                        self._option('home_y', 158., -1000., 1000.))
        self.z_hop = self._option('z_hop', 5., 0., 20.)
        self.min_clearance = self._option('min_park_clearance', 1., .01, 20.)
        self.travel_speed = self._option('travel_speed', 20., .1, 100.)
        self.z_speed = self._option('z_speed', 1., .1, 5.)
        self.retract_mm = self._option('pause_retract', 2., 0., 10.)
        self.retract_speed = self._option('retract_speed', 2., .1, 10.)
        self.m08_cycle_enabled = config.getboolean('m08_cycle_enabled', False)
        # M08 resume is an explicit heat -> bounded purge -> operator clean -> return chain.
        # Ten millimetres is the recovered stock intent (9600 / S_E=960), but remains
        # a LAB candidate behind the existing qualification gates.
        self.resume_purge_mm = self._option('resume_purge_length', 10., 0., 20.)
        self.resume_purge_speed = self._option('resume_purge_speed', 1., .1, 10.)
        self.resume_clean_timeout = self._option('resume_clean_timeout', 600., 1., 7200.)
        self.heat_timeout = self._option('heat_timeout', 1200., 1., 7200.)
        self.move_timeout = self._option('move_timeout', 120., 1., 1200.)
        self.temperature_tolerance = self._option('temperature_tolerance', 2., .1, 10.)
        self.stable_time = self._option('temperature_stable_time', 2., 0., 30.)
        self.platform_soak_seconds = self._option('platform_soak_seconds', 60., 0., 600.)
        self.adc_max_age = self._option('adc_max_age', 1., .1, 1.)
        self.standby_after = self._option('pause_standby_after', 600., 0., 7200.)
        self.standby_temp = self._option('pause_standby_temperature', 150., 0., 300.)
        self.heater_off_after = self._option('pause_heater_off_after', 1800., 0., 14400.)
        self.pause_timeout = self._option('pause_timeout', 3600., 1., 28800.)
        if not 0. <= self.standby_after <= self.heater_off_after <= self.pause_timeout:
            raise config.error('M300 pause deadlines must satisfy standby <= heater_off <= pause_timeout')
        self.park_on_cancel = config.getboolean('park_on_cancel', True)
        self.release_motors = config.getboolean('release_motors_on_end', True)
        self.filament_pause = config.getboolean('filament_pause', False)
        self.filament_delay = self._option('filament_pause_delay', 1., .1, 10.)
        self.machine = JobState()
        self.ready = False
        self.installed = False
        self.prepared = None
        self.targets = {'hotend': 0., 'bed': 0.}
        self.pause_context = None
        self._pending_pause_targets = None
        self._filament_heat_off = False
        self.pause_started = None
        self.last_rejection = ''
        self.phase_deadline = None
        self.temperature_stable_since = None
        self.runout_since = None
        self._ops = deque()
        self._waiting = False
        self._wait_deadline = None
        self._executing = False
        self._native_homing = False
        self._cleanup_pending = False
        self._resume_checking = False
        self._releasing_motors = False
        self._idle_saved = None
        self._gcode_state_name = 'M300_M02_PAUSE'
        self._last_eof_token = None
        self._started_at = None
        self._counted_token = None
        self._completion_write_token = None
        self._resume_subphase = None
        self._resume_clean_token = None
        self._home_command_permit = None
        self.nvm_warning = ''
        self.toolhead = self.heaters = self.hotend = self.bed = None
        self.gcode_move = self.fan = self.steppers = self.idle = None
        self.sd = JobSD(self, config)
        self.board.get_mcu().register_config_callback(self._audit_config)
        self._timer = self.reactor.register_timer(self._tick)
        self._watchdog_timer = self.reactor.register_timer(self._watchdog)
        self.printer.register_event_handler('klippy:connect', self._connect)
        self.printer.register_event_handler('klippy:ready', self._ready)
        self.printer.register_event_handler('klippy:shutdown', self._shutdown)
        self.printer.register_event_handler('klippy:disconnect', self._disconnect)
        self.printer.register_event_handler('gcode:request_restart', self._restart)
        self.printer.register_event_handler('stepper_enable:motor_off', self._motor_off)
        self.printer.register_event_handler('homing:home_rails_begin', self._homing_begin)
        self.gcode.register_command('START_PRINT', self.cmd_start,
                                    desc='M300 checked file start; never arms MCU')
        self.gcode.register_command('END_PRINT', self.cmd_end,
                                    desc='M300 final file marker; completion waits for EOF and motion')
        self.gcode.register_command('ZORTRAX_JOB_STATUS', self.cmd_status,
                                    when_not_ready=True)
        self.gcode.register_command('ZORTRAX_RESUME_CLEAN_CONFIRM',
                                    self.cmd_resume_clean_confirm)

    def _option(self, name, default, low, high):
        value = self.config.getfloat(name, default, minval=low, maxval=high)
        if not math.isfinite(value):
            raise self.config.error('M300 job %s must be finite' % name)
        return value

    def _error(self, message):
        return self.printer.command_error('M300 job: ' + message)

    def _service(self):
        return self.printer.lookup_object('m300_filament', None)

    def service_busy(self):
        service = self._service()
        return (service is not None and service.is_busy()) or self.m04_service_busy()

    def preparation_service_busy(self, owner):
        service = self._service()
        return ((service is not None and service.is_busy())
                or self.m04_service_busy(sd_owner=owner))

    def m04_service_busy(self, sd_owner=None):
        for name in ('m300_calibration', 'm300_maintenance', 'm300_sd', 'm300_nvm',
                     'm300_motion', 'm300_fans', 'm300_thermal', 'm300_pad_mesh'):
            service = self.printer.lookup_object(name, None)
            if service is None:
                continue
            try:
                # Only the importer itself may observe its own card as idle.
                # Other job/filament/service starts still see SD ownership.
                if (name == 'm300_sd' and sd_owner is self.sd
                        and self.sd.is_preparing
                        and getattr(service, 'owner', None) is sd_owner
                        and getattr(service, 'owner_generation', None) == self.sd._generation):
                    continue
                status = getattr(service, 'get_ownership_status', service.get_status)(self.reactor.monotonic())
                if (not isinstance(status, dict) or status.get('busy') is not False
                        or not isinstance(status.get('state'), str) or not status['state'].strip()
                        or status['state'].upper() in ('FAULT', 'SLEEP', 'SLEEPING')):
                    return True
            except Exception:
                return True
        return False

    def _bind_resources(self):
        self.toolhead = self.printer.lookup_object('toolhead')
        self.gcode_move = self.printer.lookup_object('gcode_move')
        self.heaters = self.printer.lookup_object('heaters')
        self.hotend = self.heaters.lookup_heater('extruder')
        self.bed = self.heaters.lookup_heater('heater_bed')
        self.fan = self.printer.lookup_object('fan').fan
        self.steppers = self.printer.lookup_object('stepper_enable')
        self.idle = self.printer.lookup_object('idle_timeout')

    def _audit_config(self):
        # MCU config callbacks all finish before the configuration is sent.
        self._bind_resources()
        minimum, maximum = self._axis_bounds()
        for pair in (self.park_xy, self.home_xy):
            if not all(minimum[i] <= pair[i] <= maximum[i] for i in (0, 1)):
                raise self.config.error('M300 job park/home XY outside configured axis limits')
        if self.standby_temp > self.hotend.max_temp:
            raise self.config.error('M300 standby temperature exceeds native hotend limit')
        if self.retract_mm > self.toolhead.get_extruder().max_e_dist:
            raise self.config.error('M300 pause_retract exceeds native max_extrude_only_distance')

    def _connect(self):
        self._bind_resources()
        if getattr(self.board, 'native_control', False):
            self.installed = True
            return
        # M02 owns lifecycle commands. No hidden BASE_RESUME alias remains.
        handlers = {'PAUSE': self.cmd_pause, 'RESUME': self.cmd_resume,
                    'CANCEL_PRINT': self.cmd_cancel, 'CLEAR_PAUSE': self.cmd_clear_pause}
        for name, callback in handlers.items():
            self.gcode.register_command(name, None)
            self.gcode.register_command(name, callback)
        # Direct web actions do not wait behind a native homing G-code mutex.
        # The API manifest pins webhooks.py and pause_resume.py for this use.
        webhooks = self.printer.lookup_object('webhooks')
        for action, name in [('PAUSE', 'pause'), ('RESUME', 'resume'), ('CANCEL', 'cancel')]:
            path = 'pause_resume/' + name
            existing = webhooks._endpoints.get(path)
            if getattr(existing, '__self__', None) is not self.pause_resume:
                raise self.config.error('M300 requires exclusive native pause_resume web endpoint: ' + path)
            webhooks._endpoints[path] = self._web_action(action)
        for name in ('M109', 'M190', 'TEMPERATURE_WAIT'):
            original = self.gcode.register_command(name, None)
            if original is not None:
                def guarded_wait(gcmd, original=original):
                    if self.machine.active:
                        raise self._error('blocking temperature wait is disabled during M02; use job start/resume')
                    return original(gcmd)
                self.gcode.register_command(name, guarded_wait)
        # A per-stepper disable may not emit motor_off in upstream Klippy.
        # With shared PD14 it invalidates the position of the whole mechanism.
        for name in self.steppers.get_steppers():
            self.steppers.lookup_enable(name).register_state_callback(self._enable_changed)
        self.sd.install()
        self.installed = True

    def _web_action(self, action):
        def callback(request):
            thermal = self.printer.lookup_object('m300_thermal', None)
            if action == 'CANCEL' and thermal is not None and thermal.active:
                thermal.stop('Fluidd cancel')
                return
            result = self.request_ui(action, self.machine.token)
            if not result['accepted']:
                raise request.error(result['error'])
        return callback

    def _ready(self):
        if getattr(self.board, 'native_control', False):
            self.ready = True
            return
        # Fluidd requires a CANCEL_PRINT macro in config. Its connect-time
        # rename may run before or after this executor's command binding.
        # Rebind the reserved alias after ALL connect handlers, so neither
        # ordering leaves a native cancellation path around the M08 owner.
        cancel_macro = self.printer.lookup_object('gcode_macro CANCEL_PRINT', None)
        if getattr(cancel_macro, 'rename_existing', None) == 'ZORTRAX_CANCEL_OWNER':
            self.gcode.register_command('ZORTRAX_CANCEL_OWNER', None)
            self.gcode.register_command('ZORTRAX_CANCEL_OWNER', self.cmd_cancel)
        self.ready = True
        self.reactor.update_timer(self._timer, self.reactor.NOW)
        self.reactor.update_timer(self._watchdog_timer, self.reactor.NOW)

    def _shutdown(self):
        self.ready = False
        self._fault('Klippy shutdown', signal_shutdown=False)
        self.reactor.update_timer(self._timer, self.reactor.NEVER)
        self.reactor.update_timer(self._watchdog_timer, self.reactor.NEVER)

    def _disconnect(self):
        self.ready = False
        self._fault('MCU/host disconnected', signal_shutdown=False)
        self.reactor.update_timer(self._timer, self.reactor.NEVER)
        self.reactor.update_timer(self._watchdog_timer, self.reactor.NEVER)

    def _restart(self, *args):
        self.ready = False
        self._fault('restart invalidated job and position', signal_shutdown=False)
        self.reactor.update_timer(self._timer, self.reactor.NEVER)
        self.reactor.update_timer(self._watchdog_timer, self.reactor.NEVER)

    def _motor_off(self, *args):
        if self.machine.active and not self._releasing_motors:
            self._fault('motors disabled; saved position cannot be resumed')

    def _enable_changed(self, print_time, enabled):
        if (not enabled and self.machine.active and not self._native_homing
                and not self._releasing_motors):
            self._fault('shared motor enable disabled; position lost')

    def _homing_begin(self, *args):
        if self.machine.active and not self._native_homing:
            self._fault('external homing invalidated active job coordinates')

    def _axis_bounds(self):
        status = self.toolhead.get_kinematics().get_status(self.reactor.monotonic())
        return list(status['axis_minimum'])[:3], list(status['axis_maximum'])[:3]

    def _homed(self):
        status = self.toolhead.get_kinematics().get_status(self.reactor.monotonic())
        return set(status['homed_axes']) >= set('xyz')

    def _check_position(self):
        if not self._homed():
            raise self._error('XYZ must remain homed; blind resume is forbidden')
        minimum, maximum = self._axis_bounds()
        position = list(self.toolhead.get_position())
        if (len(position) != 4 or not all(math.isfinite(x) for x in position)
                or any(not minimum[i] <= position[i] <= maximum[i] for i in range(3))):
            raise self._error('position is non-finite or outside qualified limits')
        return position

    def _check_authority(self, require_position=False):
        if not self.ready or self.printer.is_shutdown():
            raise self._error('Klippy is not ready')
        if not self.workflow_qualified:
            raise self._error('workflow_qualified=False; M02 geometry/thermal workflow is unqualified')
        if self.board.mcu.is_fileoutput():
            raise self._error('FILEOUTPUT has no physical MCU acknowledgement; job execution refused')
        self.board.require_motion()
        self.board.require_heating()
        if self.gcode_move.move_transform not in (None, self.toolhead):
            raise self._error('M02 Cartesian motion requires qualification of any added transform')
        if require_position:
            self._check_position()

    def _temperature(self, name, heater, now):
        adc = self.board.adcs.get(name)
        if adc is None:
            raise self._error('missing native ADC owner: ' + name)
        timestamp, normalized = adc.get_last_value()
        age = self.board.mcu.estimated_print_time(now) - timestamp
        if (not all(math.isfinite(x) for x in (timestamp, normalized, age))
                or timestamp <= 0. or not 0. <= age <= self.adc_max_age
                or not 0. < normalized < 1.):
            raise self._error('stale or invalid native temperature sample: ' + name)
        measured, target = heater.get_temp(now)
        if (not all(math.isfinite(x) for x in (measured, target))
                or measured < heater.min_temp or measured > heater.max_temp):
            raise self._error('invalid temperature: ' + name)
        return measured, target

    def _temperatures(self, now):
        return {'hotend': self._temperature('extruder', self.hotend, now),
                'bed': self._temperature('heater_bed', self.bed, now)}

    def _validate_targets(self, targets):
        if set(targets) != {'hotend', 'bed'}:
            raise self._error('explicit hotend and bed targets are required')
        for key, heater in (('hotend', self.hotend), ('bed', self.bed)):
            value = targets[key]
            if (not isinstance(value, (int, float)) or not math.isfinite(value)
                    or value < 0. or value > heater.max_temp
                    or (value != 0. and value < heater.min_temp)):
                raise self._error('target outside native heater limits: ' + key)
        if targets['hotend'] < self.hotend.min_extrude_temp:
            raise self._error('job hotend target is below native minimum extrusion temperature')

    def _set_targets(self, targets):
        self._validate_targets(targets)
        self._check_authority()
        token, phase = self.machine.token, self.machine.state
        # Native set_temperature first flushes lookahead and may yield before
        # setting a target. Keep that barrier, then revalidate the session before
        # the synchronous native Heater.set_temp calls. Otherwise an old call
        # could turn heat back on after CANCEL during the lookahead flush.
        self.toolhead.register_lookahead_callback(lambda print_time: None)
        if token != self.machine.token or phase != self.machine.state:
            return False
        self._check_authority()
        self.hotend.set_temp(targets['hotend'])
        self.bed.set_temp(targets['bed'])
        self.targets = dict(targets)
        self.temperature_stable_since = None
        return True

    def _off(self):
        # Zero targets are allowed by M01 even when authority has expired.
        for heater in (self.hotend, self.bed):
            if heater is not None:
                try:
                    heater.set_temp(0.)
                except Exception:
                    logging.exception('M300 emergency target zero')
        # Lifecycle handlers clear ready before cleanup. Native restart and
        # MCU shutdown/watchdog then own the fan output; a disconnected serial
        # queue cannot accept a new PWM request (and protection must win).
        if self.fan is not None and self.ready and not self.printer.is_shutdown():
            try:
                self.fan.set_speed(0.)
            except Exception:
                logging.exception('M300 print fan stop')
        # Deliberately leave heater_fan / MCU protective cooling ownership intact.

    def _set_idle(self, value):
        command = self.gcode.create_gcode_command('SET_IDLE_TIMEOUT', 'SET_IDLE_TIMEOUT',
                                                 {'TIMEOUT': str(value)})
        self.idle.cmd_SET_IDLE_TIMEOUT(command)

    def _hold_idle(self):
        if self._idle_saved is None:
            self._idle_saved = self.idle.idle_timeout
        self._set_idle(max(self._idle_saved,
                           self.heat_timeout + self.pause_timeout + 2*self.move_timeout + 60.))

    def _restore_idle(self):
        if self._idle_saved is not None and self.idle is not None:
            saved, self._idle_saved = self._idle_saved, None
            self._set_idle(saved)

    def _close_context(self):
        self.pause_context = None
        self._pending_pause_targets = None
        self._filament_heat_off = False
        self.pause_started = None
        self.pause_resume.is_paused = False
        self.pause_resume.sd_paused = False
        self.pause_resume.pause_command_sent = False
        if self.gcode_move is not None:
            self.gcode_move.saved_states.pop(self._gcode_state_name, None)

    def _discard_ops(self):
        self._ops.clear()
        self._waiting = False
        self._wait_deadline = None
        self.phase_deadline = None
        self.temperature_stable_since = None

    def _fault(self, reason, signal_shutdown=True):
        was_fault = self.machine.state == 'FAULT'
        self._resume_subphase = None
        self._resume_clean_token = None
        self.machine.fail(str(reason), self.reactor.monotonic(), kind='FAULT')
        self._cleanup_pending = True
        self._discard_ops()
        self._close_context()
        # Fault dispatch must precede any file close, feeder wait or other yield.
        if signal_shutdown and not was_fault:
            from .m300_error_codes import report
            report(self.printer, reason, source='m300_job', fatal=True)
        if signal_shutdown and not was_fault and not self.printer.is_shutdown():
            self.printer.invoke_async_shutdown('M300 job fault: ' + str(reason))
        service = self._service()
        if service is not None:
            service.parent_fault(str(reason))
        self._off()
        try:
            self.sd.error(str(reason))
        except Exception:
            logging.exception('M300 fault file cleanup')
        if self.prepared is not None:
            try:
                self.prepared.close()
            except Exception:
                logging.exception('M300 fault snapshot close')

    def start_prepared(self, prepared, gcmd=None):
        if (self.machine.active or self.machine.state == 'FAULT'
                or self._cleanup_pending or self._ops or self._waiting
                or self._executing or self._native_homing or self._resume_checking
                or self.service_busy()):
            prepared.close()
            raise self._error('another job or service is active, or a fault is latched')
        try:
            self._check_authority()
            self._validate_targets(prepared.targets)
            self._temperatures(self.reactor.monotonic())
            if self.homing_mode == 'require_homed':
                self._check_position()
            elif not self.contact_homing_qualified:
                raise self._error('native_contact requires contact_homing_qualified=True')
            if self.filament_pause:
                inputs = self.board.get_status(self.reactor.monotonic())['inputs']
                if not inputs.get('status_fresh') or inputs.get('filament_module_present') is not True:
                    raise self._error('configured filament module is absent or stale')
                if inputs.get('filament_runout'):
                    raise self._error('filament is absent before start')
        except Exception as exc:
            self.last_rejection = str(exc)
            self._off()
            prepared.close()
            raise
        # Every fresh job gets a fresh logical E origin. Resume does not pass
        # through this boundary and therefore keeps the saved pause context.
        if self.m08_cycle_enabled:
            self.gcode.run_script_from_command('G92 E0')
        self.prepared = prepared
        self._close_context()
        self._discard_ops()
        self.last_rejection = ''
        now = self.reactor.monotonic()
        context = {'filename': prepared.filename, 'sha256': prepared.sha256,
                   'size': prepared.size, 'targets': dict(prepared.targets)}
        self._started_at = now
        token = self.machine.start(context, now)
        try:
            self._hold_idle()
            if token != self.machine.token or self.machine.state != 'PREFLIGHT':
                return
            self.machine.advance('preflight_ok', token, now)
            self.phase_deadline = now + self.heat_timeout
            if not self._set_targets(prepared.targets):
                return
            self.reactor.update_timer(self._timer, self.reactor.NOW)
        except Exception as exc:
            self._fault(str(exc))
            raise
        if gcmd is not None:
            gcmd.respond_info('M300 job accepted; waiting for temperature, no automatic ARM')

    def pause(self, reason='operator'):
        if self.machine.state in ('PAUSING', 'PAUSED'):
            return
        if self.machine.state != 'PRINTING':
            raise self._error('PAUSE requires a printing job')
        token = self.machine.token
        self.machine.advance('pause', token, self.reactor.monotonic())
        self.phase_deadline = self.reactor.monotonic() + self.move_timeout
        try:
            self.sd.pause()
        except Exception as exc:
            self._fault('file pause failed: ' + str(exc))
            raise
        if token != self.machine.token or self.machine.state != 'PAUSING':
            return
        self.pause_resume.is_paused = True
        self.pause_resume.sd_paused = True
        self.pause_resume.pause_command_sent = True
        self._ops = deque([('drain',), ('capture_pause', str(reason))])
        self.reactor.update_timer(self._timer, self.reactor.NOW)

    def _capture_pause(self, reason):
        self._check_authority(require_position=True)
        now = self.reactor.monotonic()
        temperatures = self._temperatures(now)
        position = self._check_position()
        minimum, maximum = self._axis_bounds()
        plan = bounded_park(position, minimum, maximum, self.park_xy,
                            self.z_hop, self.min_clearance)
        command = self.gcode.create_gcode_command('SAVE_GCODE_STATE', 'SAVE_GCODE_STATE',
                                                 {'NAME': self._gcode_state_name})
        self.gcode_move.cmd_SAVE_GCODE_STATE(command)
        targets = {key: value[1] for key, value in temperatures.items()}
        pending, self._pending_pause_targets = self._pending_pause_targets, None
        if pending is not None and pending[0] == self.machine.token:
            targets = dict(pending[1])
        self.pause_context = {'token': self.machine.token, 'position': position,
            'gcode': copy.deepcopy(self.gcode_move.saved_states[self._gcode_state_name]),
            'targets': targets, 'fan': self.fan.get_status(now)['speed'],
            'file': self.sd.get_context(), 'reason': reason, 'plan': plan,
            'retracted': 0., 'position_valid': True}
        self.targets = dict(targets)
        if (self.retract_mm and self.hotend.can_extrude
                and temperatures['hotend'][0] >= self.hotend.min_extrude_temp):
            self._ops.append(('extrude', -self.retract_mm, 'retract'))
        for xyz in plan['park_moves']:
            self._ops.append(('move', list(xyz)))
        self._ops.append(('paused',))

    def hold_filament_heat_off(self):
        # M03 may cancel while M02 is still draining/parking, before the pause
        # snapshot exists. Preserve only metadata for a later explicit RESUME;
        # this method never restores a positive hardware target.
        if (self.machine.state == 'PAUSING' and self.pause_context is None
                and self._pending_pause_targets is None):
            now = self.reactor.monotonic()
            self._pending_pause_targets = (self.machine.token, {
                'hotend': self.hotend.get_temp(now)[1],
                'bed': self.bed.get_temp(now)[1]})
        if self.machine.state in ('PAUSING', 'PAUSED'):
            self._filament_heat_off = True

    def _check_resume_context(self, context, thermal_ready=False):
        # Pure inspection: never read/seek the snapshot or yield the reactor.
        # Full digest verification is serialized in the explicit resume action.
        if (context is None or context['token'] != self.machine.token
                or not context['position_valid']):
            raise self._error('paused context belongs to a different session or lost position')
        self._check_authority(require_position=True)
        self.sd.verify_resume(context['file'], full=False)
        temperatures = self._temperatures(self.reactor.monotonic())
        self._validate_targets(context['targets'])
        if thermal_ready:
            for name, (measured, actual_target) in temperatures.items():
                target = context['targets'][name]
                if actual_target != target or (target and abs(measured-target) > self.temperature_tolerance):
                    raise self._error('return temperature or target changed: ' + name)
        if self.filament_pause:
            inputs = self.board.get_status(self.reactor.monotonic())['inputs']
            if (not inputs.get('status_fresh')
                    or inputs.get('filament_module_present') is not True
                    or inputs.get('filament_runout')):
                raise self._error('filament state does not permit resume')
        if self.gcode_move.saved_states.get(self._gcode_state_name) != context['gcode']:
            raise self._error('saved G-code context was replaced')

    def _resume_eligible(self):
        if self.machine.state != 'PAUSED' or self.pause_context is None:
            raise self._error('RESUME requires an intact paused job')
        if self.service_busy():
            raise self._error('filament service owns the paused job')
        if self.pause_context.get('filament_service_required'):
            raise self._error('filament service incomplete; finish LOAD or CHANGE before RESUME')
        self._check_resume_context(self.pause_context)

    def resume(self):
        if self._resume_checking:
            raise self._error('resume verification is already in progress')
        self._resume_eligible()
        token = self.machine.token
        context = self.pause_context
        self._resume_checking = True
        try:
            self.sd.verify_resume(context['file'])
        except PreparationCancelled as exc:
            raise self._error(str(exc))
        finally:
            self._resume_checking = False
        if token != self.machine.token or self.machine.state != 'PAUSED':
            raise self._error('resume was cancelled during file verification')
        self._resume_eligible()
        self.machine.advance('resume', token, self.reactor.monotonic())
        self._resume_subphase = 'HEAT' if self.m08_cycle_enabled else None
        self._resume_clean_token = None
        self.phase_deadline = self.reactor.monotonic() + self.heat_timeout
        try:
            if not self._set_targets(context['targets']):
                return
            self._filament_heat_off = False
        except Exception as exc:
            self._fault('resume heat setup failed: ' + str(exc))
            raise
        self.reactor.update_timer(self._timer, self.reactor.NOW)

    def _prepare_return(self):
        self._resume_subphase = 'RETURN'
        context = self.pause_context
        self._check_resume_context(context, thermal_ready=True)
        current = self._check_position()
        origin = context['position']
        minimum, maximum = self._axis_bounds()
        if any(not minimum[i] <= origin[i] <= maximum[i] for i in range(3)):
            raise self._error('return target outside current axis limits')
        # Fresh geometry also handles legitimate manual jogging while paused.
        height = max(current[2], context['plan']['lift'][2])
        if height > maximum[2]:
            raise self._error('no safe return height')
        if current[2] != height:
            self._ops.append(('move', [current[0], current[1], height]))
        if current[:2] != origin[:2]:
            if height - origin[2] < self.min_clearance:
                raise self._error('insufficient clearance for return XY')
            self._ops.append(('move', [origin[0], origin[1], height]))
        if height != origin[2]:
            self._ops.append(('move', origin[:3]))
        if context['retracted']:
            self._ops.append(('extrude', context['retracted'], 'unretract'))
        self._ops.append(('returned',))

    def confirm_resume_clean(self, token=None):
        if not self.m08_cycle_enabled:
            raise self._error('M08 resume-clean chain is disabled in this profile')
        if token is None:
            token = self.machine.token
        if (isinstance(token, bool) or not isinstance(token, int)
                or token != self.machine.token or token != self._resume_clean_token):
            raise self._error('stale resume-clean confirmation')
        if self.machine.state != 'RETURNING' or self._resume_subphase != 'CLEAN':
            raise self._error('resume-clean confirmation is unavailable')
        self._check_resume_context(self.pause_context, thermal_ready=True)
        if self.service_busy():
            raise self._error('service still owns the paused job')
        self._resume_clean_token = None
        self.phase_deadline = self.reactor.monotonic() + self.move_timeout
        self._prepare_return()
        self.reactor.update_timer(self._timer, self.reactor.NOW)
        return True

    def cancel(self, reason='operator'):
        # Also abort an in-progress cooperative scan or a selected idle file.
        now = self.reactor.monotonic()
        previous = self.machine.state
        token = self.machine.cancel(str(reason), now)
        self._resume_subphase = None
        self._resume_clean_token = None
        service = self._service()
        if service is not None:
            service.parent_cancel(str(reason))
        if previous == 'CANCELLING':
            self._off()
            return
        cleanup_was_pending = self._cleanup_pending
        self._cleanup_pending = True
        if token is not None:
            self._discard_ops()
            # Replace an expired PAUSED deadline before the first possible yield.
            self.phase_deadline = now + self.move_timeout
        if self._native_homing:
            self._fault('cancel during native homing requires firmware restart')
            return
        self._off()
        try:
            self.sd.cancel()
            self._close_context()
            if self.prepared is not None:
                self.prepared.close()
        except Exception as exc:
            self._fault('file cancellation failed: ' + str(exc))
            raise
        if token is None:
            self._cleanup_pending = cleanup_was_pending or self.machine.state == 'FAULT'
            return
        if token != self.machine.token or self.machine.state != 'CANCELLING':
            return
        self._ops.append(('drain',))
        if self.park_on_cancel and self._can_park():
            self._ops.append(('final_park',))
        self._ops.append(('cancelled',))
        self.reactor.update_timer(self._timer, self.reactor.NOW)

    def file_error(self, reason):
        had_active_job = self.machine.active
        token = self.machine.token
        self.machine.fail(str(reason), self.reactor.monotonic(), kind='FILE_ERROR')
        if self.machine.state != 'FILE_ERROR' or token == self.machine.token:
            return
        from .m300_error_codes import report
        report(self.printer, reason, source='m300_job_file', code=4)
        token = self.machine.token
        self._cleanup_pending = True
        self._discard_ops()
        self.phase_deadline = self.reactor.monotonic() + self.move_timeout
        self._off()
        self._close_context()
        try:
            self.sd.error(str(reason))
            if self.prepared is not None:
                self.prepared.close()
        except Exception as exc:
            self._fault('file error cleanup failed: ' + str(exc))
            return
        if token != self.machine.token or self.machine.state != 'FILE_ERROR':
            return
        # A file failure never initiates parking. Queued motion is drained only
        # while M01 remains healthy; otherwise its shutdown has priority.
        if had_active_job:
            self._ops.append(('drain',))
        # A rejected file before start has never fed motion. Do not create a
        # fictitious queue barrier or release motors owned by manual work.
        self._ops.append(('error_clean', had_active_job))
        if self.ready:
            self.reactor.update_timer(self._timer, self.reactor.NOW)

    def file_eof(self):
        if self.machine.state != 'PRINTING':
            if self.machine.state not in ('CANCELLING', 'CANCELLED', 'FILE_ERROR', 'FAULT'):
                self.file_error('EOF outside printing state')
            return
        token = self.machine.token
        self.machine.advance('eof', token, self.reactor.monotonic())
        self._last_eof_token = token
        self.phase_deadline = self.reactor.monotonic() + self.move_timeout
        self._ops = deque([('drain',), ('finish_outputs',), ('final_park',), ('completed',)])
        self.reactor.update_timer(self._timer, self.reactor.NOW)

    def _can_park(self):
        try:
            self._check_authority(require_position=True)
            return True
        except Exception:
            return False

    def _queue_drained(self, now):
        print_time, estimated, empty = self.toolhead.check_busy(now)
        return empty and estimated >= print_time

    def _begin_drain(self, now):
        token, phase = self.machine.token, self.machine.state
        self.toolhead.get_last_move_time()  # flush native lookahead
        if token != self.machine.token or phase != self.machine.state:
            return
        self._waiting = True
        self._wait_deadline = now + self.move_timeout

    def _execute_op(self, op, now):
        name = op[0]
        token, phase = self.machine.token, self.machine.state
        if name == 'drain':
            self._begin_drain(now)
        elif name == 'capture_pause':
            self._capture_pause(op[1])
        elif name == 'move':
            self._check_authority(require_position=True)
            if phase == 'RETURNING':
                self._check_resume_context(self.pause_context, thermal_ready=True)
            current = self._check_position()
            xyz = op[1]
            speed = self.z_speed if xyz[2] != current[2] else self.travel_speed
            self.toolhead.manual_move(list(xyz) + [None], speed)
            if token != self.machine.token or phase != self.machine.state:
                return
            self._begin_drain(now)
        elif name == 'resume_purge':
            self._check_authority(require_position=True)
            self._check_resume_context(self.pause_context, thermal_ready=True)
            measured, _ = self._temperature('extruder', self.hotend, now)
            if not self.hotend.can_extrude or measured < self.hotend.min_extrude_temp:
                raise self._error('cold extrusion refused before resume purge')
            current = self.toolhead.get_position()[3]
            self.toolhead.manual_move([None, None, None, current + op[1]], op[2])
            if token != self.machine.token or phase != self.machine.state:
                return
            self._begin_drain(now)
        elif name == 'extrude':
            self._check_authority(require_position=True)
            if phase == 'RETURNING':
                self._check_resume_context(self.pause_context, thermal_ready=True)
            measured, _ = self._temperature('extruder', self.hotend, now)
            if not self.hotend.can_extrude or measured < self.hotend.min_extrude_temp:
                raise self._error('cold extrusion refused before ' + op[2])
            current = self.toolhead.get_position()[3]
            self.toolhead.manual_move([None, None, None, current + op[1]], self.retract_speed)
            if token != self.machine.token or phase != self.machine.state:
                return
            if op[2] == 'retract':
                self.pause_context['retracted'] = -op[1]
            self._begin_drain(now)
        elif name == 'paused':
            self.machine.advance('parked', self.machine.token, now)
            self.pause_started = now
            self.phase_deadline = now + self.pause_timeout
        elif name == 'resume_clean_wait':
            self._check_resume_context(self.pause_context, thermal_ready=True)
            self._resume_subphase = 'CLEAN'
            self._resume_clean_token = token
            self.phase_deadline = now + self.resume_clean_timeout
        elif name == 'returned':
            context = self.pause_context
            self._check_resume_context(context, thermal_ready=True)
            command = self.gcode.create_gcode_command('RESTORE_GCODE_STATE', 'RESTORE_GCODE_STATE',
                {'NAME': self._gcode_state_name, 'MOVE': '0'})
            self.gcode_move.cmd_RESTORE_GCODE_STATE(command)
            self.fan.set_speed(context['fan'])
            if token != self.machine.token or phase != self.machine.state:
                return
            self._check_resume_context(context, thermal_ready=True)
            self.machine.advance('returned', self.machine.token, now)
            self._resume_subphase = None
            self._resume_clean_token = None
            self.phase_deadline = None
            self._close_context()
            self.sd.resume()
        elif name == 'finish_outputs':
            self._off()
        elif name == 'final_park':
            if not self._can_park():
                return
            position = self._check_position()
            minimum, maximum = self._axis_bounds()
            plan = bounded_park(position, minimum, maximum, self.park_xy,
                                self.z_hop, self.min_clearance)
            for xyz in reversed(plan['park_moves']):
                self._ops.appendleft(('move', list(xyz)))
        elif name == 'completed':
            if self._last_eof_token != self.machine.token:
                raise self._error('completion belongs to an obsolete EOF')
            self._cleanup_pending = True
            if not self._terminal_cleanup():
                return
            self.sd.complete()
            if token != self.machine.token or phase != self.machine.state:
                return
            # The EOF movement/file cleanup budget is finished. Retain the
            # cleanup owner while storage yields, without charging filesystem
            # latency against the already-completed motion phase deadline.
            self.phase_deadline = None
            # Keep COMPLETING visible while the native NVM executor yields.
            # This permit is issued only after EOF, queue drain, file close,
            # and terminal output cleanup; ordinary COMPLETING has no permit.
            self._completion_write_token = token
            try:
                self._record_completion(token)
            finally:
                self._completion_write_token = None
        elif name == 'cancelled':
            self._cleanup_pending = True
            if not self._terminal_cleanup():
                return
            self.machine.advance('cancelled', token, self.reactor.monotonic())
            self._finish_cleanup()
        elif name == 'error_clean':
            if self._terminal_cleanup(release_motors=op[1]):
                self._finish_cleanup()
        else:
            raise self._error('unknown internal operation: ' + name)

    def _finish_cleanup(self):
        self.phase_deadline = None
        self._cleanup_pending = False

    def completion_write_authorized(self, token):
        """Authorize only this session's post-cleanup completion counter write.

        The NVM adapter calls this without yielding. Cancellation/restart/fault
        revokes the session token before cleanup and therefore revokes this
        permission even while an already-submitted atomic write is pending.
        """
        return (type(token) is int and token == self.machine.token
                and token == self._last_eof_token
                and token == self._completion_write_token
                and self.machine.state == 'COMPLETING'
                and self._cleanup_pending and not self._waiting and not self._ops
                and self.ready and not self.printer.is_shutdown())

    def _record_completion(self, token):
        phase = self.machine.state
        if (self._counted_token == token or token != self.machine.token
                or (phase != 'COMPLETE' and not self.completion_write_authorized(token))):
            return
        self._counted_token = token
        now = self.reactor.monotonic()
        seconds = max(0., now-(self._started_at if self._started_at is not None else now))
        filename = self.machine.context.get('filename', '')
        nvm = self.printer.lookup_object('m300_nvm', None)
        if nvm is not None:
            try:
                if phase == 'COMPLETING':
                    nvm.record_completed_job(seconds, token=token)
                else:
                    nvm.record_completed_job(seconds)
            except Exception as exc:
                self.nvm_warning = 'Completed job counter was not persisted: ' + str(exc)
                logging.exception('M300 completion NVM')
        # An atomic write may have completed after cancellation or shutdown.
        # Its EOF counter is attempted once; never resurrect that old session
        # or publish its repeat action when the yielding continuation resumes.
        if (token != self.machine.token or phase != self.machine.state
                or not self.ready or self.printer.is_shutdown()):
            return
        if phase == 'COMPLETING':
            self.machine.advance('completed', token, self.reactor.monotonic())
            self._finish_cleanup()
        # No yield separates COMPLETE, the released NVM owner, and the menu
        # event. A consumer observing COMPLETE can immediately select repeat.
        self.printer.send_event('m300:job_completed', filename, seconds)

    def _terminal_cleanup(self, release_motors=True):
        token, phase = self.machine.token, self.machine.state
        self._off()
        if token != self.machine.token or phase != self.machine.state:
            return False
        self._close_context()
        self._restore_idle()
        if token != self.machine.token or phase != self.machine.state:
            return False
        if self.prepared is not None:
            self.prepared.close()
        if token != self.machine.token or phase != self.machine.state:
            return False
        if release_motors and self.release_motors and self.steppers is not None:
            self._releasing_motors = True
            try:
                self.steppers.motor_off()
            finally:
                self._releasing_motors = False
        return token == self.machine.token and phase == self.machine.state

    def _native_home(self, token):
        if self.homing_mode == 'require_homed':
            self._check_position()
            return
        if not self.contact_homing_qualified:
            raise self._error('contact homing is unqualified')
        motion = self.printer.lookup_object('m300_motion', None)
        if motion is not None:
            self._native_homing = True
            try:
                motion.home(owner_job=self, job_token=token, axes='xyz')
                if token != self.machine.token or self.printer.is_shutdown():
                    raise self._error('M06 homing session cancelled')
                self._check_position()
            finally:
                self._native_homing = False
            return
        # Compatibility with explicit pre-M06 profiles. The M06 full profile
        # requires/auto-loads m300_motion through m300_resources, so it cannot
        # silently fall back here by omitting only the motion section.
        self._native_homing = True
        def home_axis(axis):
            if token != self.machine.token or self.printer.is_shutdown():
                raise self._error('homing session cancelled')
            self._home_command_permit = (token, axis)
            try:
                self.gcode.run_script_from_command('G28 ' + axis)
            finally:
                self._home_command_permit = None
        try:
            home_axis('Y')
            home_axis('X')
            if token != self.machine.token or self.printer.is_shutdown():
                raise self._error('homing session cancelled')
            self.toolhead.manual_move([self.home_xy[0], self.home_xy[1], None, None], self.travel_speed)
            self.toolhead.wait_moves()
            if token != self.machine.token or self.printer.is_shutdown():
                raise self._error('homing session cancelled')
            home_axis('Z')
            self._check_position()
        finally:
            self._native_homing = False

    def _heat_tick(self, now):
        temperatures = self._temperatures(now)
        stable = True
        for key, (measured, actual_target) in temperatures.items():
            expected = self.targets[key]
            if actual_target != expected:
                raise self._error('temperature target changed during controlled wait: ' + key)
            if expected and abs(measured - expected) > self.temperature_tolerance:
                stable = False
        if not stable:
            self.temperature_stable_since = None
            return
        if self.temperature_stable_since is None:
            self.temperature_stable_since = now
        stable_time = self.stable_time
        nvm = self.printer.lookup_object('m300_nvm', None)
        if (self.machine.state == 'HEATING' and nvm is not None
                and nvm.get_setting('full_platform_preheat', False)):
            stable_time += self.platform_soak_seconds
        if now - self.temperature_stable_since < stable_time:
            return
        if self.machine.state == 'HEATING':
            self.machine.advance('heated', self.machine.token, now)
            self.phase_deadline = now + self.move_timeout
        else:
            self.machine.advance('reheated', self.machine.token, now)
            self.phase_deadline = now + self.move_timeout
            if self.m08_cycle_enabled:
                self._resume_subphase = 'PURGE'
                if self.resume_purge_mm:
                    # Reuse the already guarded native E move; speed is temporarily
                    # scoped to M08 and restored immediately after the queue request.
                    self._ops.append(('resume_purge', self.resume_purge_mm, self.resume_purge_speed))
                self._ops.append(('resume_clean_wait',))
            else:
                self._prepare_return()

    def _pause_tick(self, now):
        if self.service_busy():
            return  # M03 owns the hotend; M02 watchdog/overall pause deadline remain.
        elapsed = now - self.pause_started
        context = self.pause_context
        if context is None:
            raise self._error('pause context lost')
        self._temperatures(now)
        if self._filament_heat_off or elapsed >= self.heater_off_after:
            self.hotend.set_temp(0.)
        elif elapsed >= self.standby_after:
            self.hotend.set_temp(min(self.standby_temp, context['targets']['hotend']))

    def _filament_tick(self, now):
        if not self.filament_pause:
            return
        inputs = self.board.get_status(now)['inputs']
        bad = (not inputs.get('status_fresh')
               or inputs.get('filament_module_present') is not True
               or inputs.get('filament_runout'))
        if not bad:
            self.runout_since = None
        elif self.runout_since is None:
            self.runout_since = now
        elif now - self.runout_since >= self.filament_delay:
            self.pause('filament signal')
            self.runout_since = None

    def _watchdog(self, now):
        # This separate timer remains runnable while the operation timer is
        # yielding inside a native move/homing call or waiting for a mutex.
        if not self.ready or self.printer.is_shutdown():
            return self.reactor.NEVER
        if self.machine.active or self._cleanup_pending:
            try:
                if self.machine.active:
                    self._check_authority()
                    self._temperatures(now)
                if self.phase_deadline is not None and now > self.phase_deadline:
                    if self.machine.state == 'PAUSED':
                        self.cancel('pause deadline expired')
                    else:
                        raise self._error('phase deadline expired: ' + self.machine.state)
            except Exception as exc:
                self._fault(str(exc))
        return now + PERIOD if self.ready else self.reactor.NEVER

    def _tick(self, now):
        if not self.ready or self.printer.is_shutdown():
            return self.reactor.NEVER
        if not self.machine.active and not self._ops and not self._waiting:
            return now + PERIOD
        try:
            # Monitoring is independent of the G-code mutex; faults preempt a
            # pending operation. Ordinary operations acquire it for one step.
            if self.machine.active:
                self._check_authority()
            if self.phase_deadline is not None and now > self.phase_deadline:
                if self.machine.state == 'PAUSED':
                    self.cancel('pause deadline expired')
                else:
                    raise self._error('phase deadline expired: ' + self.machine.state)
            if self._executing:
                return now + PERIOD
            if self._waiting:
                if now > self._wait_deadline:
                    raise self._error('native motion queue drain timeout')
                if not self._queue_drained(now):
                    return now + PERIOD
                self._waiting = False
            if self.gcode.get_mutex().test():
                return now + PERIOD
            with self.gcode.get_mutex():
                self._executing = True
                try:
                    if self.machine.state in ('HEATING', 'RESUMING'):
                        self._heat_tick(now)
                    elif self.machine.state == 'HOMING':
                        token = self.machine.token
                        # Heating and second-job setup may leave a native lookahead
                        # callback pending. Homing never races an undrained queue.
                        if self.m08_cycle_enabled and not self._queue_drained(now):
                            self._begin_drain(now)
                            return now + PERIOD
                        self._native_home(token)
                        if token != self.machine.token or self.machine.state != 'HOMING':
                            return now + PERIOD
                        self.machine.advance('homed', token, now)
                        try:
                            self.sd.begin(self.prepared)
                        except PreparationCancelled:
                            if token == self.machine.token and self.machine.state == 'PRINTING':
                                raise
                            # A known invalidation during the AIO seek is an
                            # expected cancellation, not a new hardware fault.
                            return now + PERIOD
                        if token == self.machine.token and self.machine.state == 'PRINTING':
                            self.phase_deadline = None
                    elif self._ops:
                        token = self.machine.token
                        op = self._ops.popleft()
                        self._execute_op(op, now)
                        if token != self.machine.token:
                            return now + PERIOD
                    elif self.machine.state == 'PAUSED':
                        self._pause_tick(now)
                    elif self.machine.state == 'PRINTING':
                        self._filament_tick(now)
                finally:
                    self._executing = False
        except Exception as exc:
            logging.exception('M300 job phase failure')
            self._fault(str(exc))
        return now + PERIOD if self.ready else self.reactor.NEVER

    def request_ui(self, action, token):
        try:
            if token != self.machine.token:
                raise self._error('stale panel session')
            if action not in ('PAUSE', 'RESUME', 'CANCEL'):
                raise self._error('unsupported panel action')
            status = self.get_status(self.reactor.monotonic())
            if not status['can_' + action.lower()]:
                raise self._error('action unavailable in ' + self.machine.state)
            # State/token changes happen before delayed physical operations.
            # No mutex acquisition here: cancellation can preempt native homing.
            if action == 'CANCEL':
                self.cancel('panel/web request')
            elif action == 'PAUSE':
                self.pause('panel/web request')
            else:
                self.resume()
            return {'accepted': True, 'error': None}
        except Exception as exc:
            self.last_rejection = str(exc)
            return {'accepted': False, 'error': str(exc)}

    def cmd_start(self, gcmd):
        if self.sd.v_sd.is_cmd_from_sd():
            if self.machine.state != 'PRINTING' or self.prepared is None:
                raise self._error('START_PRINT marker outside checked file')
            for arg, name in (('EXTRUDER_TEMP', 'hotend'), ('BED_TEMP', 'bed')):
                value = gcmd.get_float(arg, self.prepared.targets[name])
                if not math.isfinite(value) or value != self.prepared.targets[name]:
                    raise self._error('START_PRINT marker differs from validated file')
            return
        if not gcmd.get('FILENAME', ''):
            raise self._error('START_PRINT requires FILENAME; streaming jobs are outside M02')
        self.sd.start_file(gcmd)

    def cmd_end(self, gcmd):
        if not self.sd.v_sd.is_cmd_from_sd() or self.machine.state != 'PRINTING':
            raise self._error('END_PRINT is a final file marker; completion requires verified EOF')
        # File preflight already requires this marker to be the last command.
        # Native feeder EOF, followed by queue drain, owns actual completion.

    def cmd_pause(self, gcmd):
        self.pause('G-code PAUSE')

    def cmd_resume(self, gcmd):
        self.resume()

    def cmd_resume_clean_confirm(self, gcmd):
        token = gcmd.get_int('TOKEN', self.machine.token, minval=0)
        self.confirm_resume_clean(token)

    def cmd_cancel(self, gcmd):
        thermal = self.printer.lookup_object('m300_thermal', None)
        if thermal is not None and thermal.active:
            thermal.stop('CANCEL_PRINT')
            return
        self.cancel('G-code CANCEL_PRINT')

    def cmd_clear_pause(self, gcmd):
        if self.machine.active or self.service_busy():
            raise self._error('CLEAR_PAUSE cannot discard an active M02 context; use CANCEL_PRINT')
        self._close_context()

    def get_status(self, now):
        state = self.machine.state
        context = self.machine.context
        sd_context = self.sd.get_context() or {}
        size = context.get('size', 0)
        position = sd_context.get('position', 0)
        progress = (min(1., max(0., position / float(size))) if size else 0.)
        if state == 'COMPLETE':
            progress = 1.
        can_resume = False
        resume_block_reason = ''
        if state == 'PAUSED' and self.ready and not self.printer.is_shutdown():
            try:
                if self._resume_checking:
                    raise self._error('resume verification is already in progress')
                self._resume_eligible()
                can_resume = True
            except Exception as exc:
                resume_block_reason = str(exc)
        live = self.ready and not self.printer.is_shutdown()
        hot_target = self.hotend.get_temp(now)[1] if self.hotend is not None else 0.
        bed_target = self.bed.get_temp(now)[1] if self.bed is not None else 0.
        return {'version': '0.8.0-LAB_M01_M02_M03_M04_M05_M06_M07_M08', 'model': 'M300_CLASSIC',
                'state': state, 'session_token': self.machine.token,
                'filename': context.get('filename'), 'file_sha256': context.get('sha256'),
                'reason': self.machine.reason or '', 'last_rejection': self.last_rejection,
                'progress': progress, 'busy': bool(self.machine.active or self.sd.is_preparing
                    or self._cleanup_pending or self._ops or self._waiting or self._executing),
                'can_pause': live and state == 'PRINTING',
                'can_resume': can_resume,
                'resume_phase': self._resume_subphase if self.m08_cycle_enabled else None,
                'can_confirm_resume_clean': (self.m08_cycle_enabled and live and state == 'RETURNING'
                    and self._resume_subphase == 'CLEAN'
                    and self._resume_clean_token == self.machine.token),
                'resume_block_reason': resume_block_reason,
                'can_cancel': live and (self.machine.active or self.sd.is_preparing),
                'target_hotend': hot_target, 'target_bed': bed_target,
                'phase_remaining': (None if self.phase_deadline is None
                                    else max(0., self.phase_deadline - now)),
                'workflow_qualified': self.workflow_qualified,
                'homing_mode': self.homing_mode, 'hardware_qualified': False,
                'installed': self.installed, 'ready': live,
                'zcode_execution': bool(getattr(self.sd, 'binary_zcode_qualified', False)),
                'nvm_warning': self.nvm_warning, 'automatic_arm': False,
                'native_adc_owners_added': 0,
                'history': self.machine.snapshot().get('history', [])}

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_JOB ' + json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))


def load_config(config):
    return M300Job(config)
