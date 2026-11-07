# SPDX-License-Identifier: GPL-3.0-or-later
"""M04 bounded maintenance and sleep on the single native M300 resources.

No raw pins, motor position restoration, automatic ARM, or wake-up heating.
The configuration and physical qualification are deliberately separate.
"""
import json
import logging
import math

from .m300_nvm import MAX_BRIGHTNESS

IDLE_JOB = {'IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR'}
LED_ERROR_COLORS = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
LED_ERROR_SECONDS = 5.
LED_COLORS = {'READY': (0, 1, 0), 'HEATING': (1, 0, 0),
              'PAUSE': (1, 0, 1), 'WORKING': (1, 1, 1)}


def other_service(printer, names, now):
    """Optional services must report their ownership; malformed state is busy."""
    for name in names:
        obj = printer.lookup_object(name, None)
        if obj is None:
            continue
        try:
            status = getattr(obj, 'get_ownership_status', obj.get_status)(now)
            if (not isinstance(status, dict) or status.get('busy') is not False
                    or not isinstance(status.get('state'), str) or not status['state'].strip()):
                return name
            if status['state'].upper() in ('SLEEP', 'SLEEPING', 'FAULT'):
                return name
        except Exception:
            return name
    return None


class M300Maintenance:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.wake_on_motion = config.getboolean('wake_on_motion', False)
        self.wake_on_control = config.getboolean('wake_on_control', False)
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.job = self.printer.load_object(config, 'm300_job')
        self.board = self.printer.load_object(config, 'm300_mcu')
        self.qualified = config.getboolean('qualified', False)
        self.timeout = self._number('service_timeout', 300., 1., 1200.)
        self.jog_distance = self._number('max_jog_distance', 5., .1, 10.)
        self.jog_speed = self._number('jog_speed', 1., .1, 5.)
        self.fan_time = self._number('fan_test_seconds', 5., .1, 30.)
        self.state, self.reason, self.operation = 'IDLE', '', None
        self.token = 0
        self.ready = False
        self._executing = False
        self._move_permit = None
        self._deadline = None
        self._expected_targets = None
        self._fan_kind = None
        self._old_fan_speed = None
        self._lights = None
        self._light_state = 'READY'
        self._light_error_since = None
        self._beep_until = 0.
        self._last_activity = self.reactor.monotonic()
        self._timer = self.reactor.register_timer(self._tick)
        self.printer.register_event_handler('m300:setting_changed', self._setting_changed)
        for event, callback in (('klippy:connect', self._connect),
                                ('klippy:ready', self._ready),
                                ('klippy:shutdown', self._stop_lifecycle),
                                ('klippy:disconnect', self._stop_lifecycle),
                                ('gcode:request_restart', self._stop_lifecycle)):
            self.printer.register_event_handler(event, callback)
        for name, callback in (
                ('ZORTRAX_SERVICE', self.cmd_service),
                ('ZORTRAX_SERVICE_STOP', self.cmd_stop),
                ('ZORTRAX_SLEEP', self.cmd_sleep), ('ZORTRAX_WAKE', self.cmd_wake),
                ('ZORTRAX_MAINTENANCE_STATUS', self.cmd_status)):
            self.gcode.register_command(name, callback,
                when_not_ready=name.endswith('_STATUS'))

    def _number(self, name, default, low, high):
        value = self.config.getfloat(name, default, minval=low, maxval=high)
        if not math.isfinite(value):
            raise self.config.error('M300 maintenance finite ' + name + ' required')
        return value

    def _error(self, message):
        return self.printer.command_error('M300 maintenance: ' + message)

    def _connect(self):
        self.toolhead = self.printer.lookup_object('toolhead')
        self.gcode_move = self.printer.lookup_object('gcode_move')
        self.hotend, self.bed = self.job.hotend, self.job.bed
        self.fan = self.job.fan
        self.hotend_fan = self.printer.lookup_object('heater_fan hotend', None)
        if getattr(self.board, 'native_control', False):
            return
        old_move = self.toolhead.move
        def guarded_move(position, speed):
            if self.is_busy():
                permit, self._move_permit = self._move_permit, None
                if (permit is None or permit != (self.token, list(position), speed)
                        or self.state != 'MOVING'):
                    raise self._error('maintenance/sleep owns motion')
                self._authority(True)
            return old_move(position, speed)
        self.toolhead.move = guarded_move
        if self.gcode_move.move_with_transform == old_move:
            self.gcode_move.move_with_transform = guarded_move
        self._wrapped_native_move = old_move
        for name in ('drip_move', 'set_position'):
            original = getattr(self.toolhead, name, None)
            if original is None:
                continue
            def guarded_direct(*args, original=original, **kwargs):
                if self.is_busy():
                    raise self._error('maintenance/sleep owns motion and coordinates')
                return original(*args, **kwargs)
            setattr(self.toolhead, name, guarded_direct)
        for name in ('G0', 'G1', 'G28', 'G90', 'G91', 'G92', 'M82', 'M83',
                     'RESTORE_GCODE_STATE', 'SET_GCODE_OFFSET', 'SET_KINEMATIC_POSITION',
                     'FORCE_MOVE', 'STEPPER_BUZZ', 'PROBE', 'PROBE_ACCURACY',
                     'PROBE_CALIBRATE', 'PID_CALIBRATE', 'M109', 'M190',
                     'TEMPERATURE_WAIT', 'SET_EXTRUDER_ROTATION_DISTANCE',
                     'SYNC_EXTRUDER_MOTION', 'M106', 'M107', 'SET_FAN_SPEED'):
            original = self.gcode.register_command(name, None)
            if original is None:
                continue
            def guarded(gcmd, original=original, name=name):
                if name in ('G0', 'G1', 'G28', 'G90', 'G91'):
                    self.wake_for_operator_motion()
                elif name in ('PID_CALIBRATE', 'M109', 'M190', 'TEMPERATURE_WAIT',
                              'M106', 'M107', 'SET_FAN_SPEED'):
                    self.wake_for_operator_control()
                if self.is_busy():
                    raise self._error(name + ' refused while maintenance/sleep owns resources')
                self.activity()
                return original(gcmd)
            self.gcode.register_command(name, guarded)
        for name in ('M104', 'M140', 'SET_HEATER_TEMPERATURE', 'TURN_OFF_HEATERS'):
            original = self.gcode.register_command(name, None)
            if original is None:
                continue
            def guarded_heat(gcmd, original=original, name=name):
                # A new operator request may leave passive sleep, but it
                # never resumes the old target or a maintenance operation.
                # Heater-off remains valid while asleep and need not wake.
                target = (0. if name == 'TURN_OFF_HEATERS' else
                          gcmd.get_float('TARGET' if name == 'SET_HEATER_TEMPERATURE' else 'S', 0.))
                if target > 0.:
                    self.wake_for_operator_control()
                if self.is_busy():
                    if target != 0.:
                        raise self._error('external positive temperature while service/sleep active')
                    if self.state != 'SLEEP':
                        self.stop('external heater off')
                self.activity()
                return original(gcmd)
            self.gcode.register_command(name, guarded_heat)

    def _ready(self):
        self.ready = True
        self.activity()
        self.reactor.update_timer(self._timer, self.reactor.NOW)

    def _stop_lifecycle(self, *args):
        self.token += 1
        self.ready = False
        self._move_permit = None
        self.state, self.reason = 'FAULT', 'host lifecycle invalidated the service'
        self.reactor.update_timer(self._timer, self.reactor.NEVER)
        # Native MCU shutdown owns final electrical levels.

    def activity(self):
        self._last_activity = self.reactor.monotonic()

    def is_busy(self):
        return self.state not in ('IDLE', 'COMPLETE') or self._executing

    def _idle(self):
        if not self.ready or self.printer.is_shutdown():
            raise self._error('Klippy is not ready')
        if self.is_busy():
            raise self._error('service is active or sleep/fault is latched')
        if (self.job.machine.state not in IDLE_JOB or self.job.machine.active
                or self.job._ops or self.job._waiting or self.job._executing
                or self.job._cleanup_pending or self.job._resume_checking
                or self.job.sd.is_preparing or self.job.sd.is_session_active()):
            raise self._error('M02 job/file operation owns resources')
        owner = other_service(self.printer, ('m300_filament', 'm300_calibration', 'm300_sd', 'm300_nvm', 'm300_motion', 'm300_fans', 'm300_thermal'),
                              self.reactor.monotonic())
        if owner:
            raise self._error(owner + ' owns resources')
        if not self.job._queue_drained(self.reactor.monotonic()):
            raise self._error('motion queue must be empty')

    def _authority(self, position=False):
        if not self.qualified:
            raise self._error('qualified=False; maintenance hardware is unqualified')
        self.job._check_authority(require_position=position)
        return self.job._temperatures(self.reactor.monotonic())

    def _off(self):
        failures = []
        for heater in (self.hotend, self.bed):
            try:
                heater.set_temp(0.)
            except Exception as exc:
                logging.exception('M300 maintenance target zero')
                failures.append(str(exc))
        return failures

    def start(self, operation, value=None):
        self._idle()
        if operation not in ('HOTEND', 'BED', 'JOG_Z', 'FAN_PRINT', 'FAN_HOTEND'):
            raise self._error('unknown maintenance operation')
        resources = self.printer.lookup_object('m300_resources', None)
        if (operation == 'JOG_Z' and resources is not None
                and getattr(resources, 'require_motion_owner', False)):
            # The complete M06/M07 profile has one contact-aware manual-Z
            # workflow. The old direct move remains only in explicit legacy
            # profiles; a public service command must not bypass the panel's
            # release/press session, contact check or motion qualifications.
            raise self._error('JOG_Z is owned by M06; use ZORTRAX_Z_JOG '
                              'and the encoder hold-to-move view')
        self._authority(operation == 'JOG_Z')
        if operation in ('HOTEND', 'BED', 'JOG_Z'):
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise self._error('explicit finite value is required')
        if operation in ('HOTEND', 'BED'):
            heater = self.hotend if operation == 'HOTEND' else self.bed
            if not heater.min_temp <= value <= heater.max_temp or value <= 0.:
                raise self._error('temperature outside native heater limits')
        if operation == 'JOG_Z':
            if value == 0. or abs(value) > self.jog_distance:
                raise self._error('Z jog exceeds configured bounded distance')
            position = list(self.toolhead.get_position())
            position[2] += value
            minimum, maximum = self.job._axis_bounds()
            if not minimum[2] <= position[2] <= maximum[2]:
                raise self._error('Z jog exceeds native axis limits')
        self.token += 1
        token = self.token
        self.operation, self.reason = operation, ''
        self._deadline = self.reactor.monotonic() + self.timeout
        self.state = ('MOVING' if operation == 'JOG_Z' else
                      'FAN_TEST' if operation.startswith('FAN_') else 'HEATING')
        self._executing = True
        try:
            self.toolhead.register_lookahead_callback(lambda pt: None)
            if token != self.token or self.printer.is_shutdown():
                return
            self._authority(operation == 'JOG_Z')
            if operation == 'JOG_Z':
                self._move_permit = (token, position, self.jog_speed)
                self.toolhead.manual_move(position, self.jog_speed)
                self._move_permit = None
            elif operation in ('HOTEND', 'BED'):
                self._expected_targets = {'hotend': float(value) if operation == 'HOTEND' else 0.,
                                          'bed': float(value) if operation == 'BED' else 0.}
                self.hotend.set_temp(self._expected_targets['hotend'])
                self.bed.set_temp(self._expected_targets['bed'])
            else:
                if operation == 'FAN_HOTEND' and self.hotend_fan is None:
                    raise self._error('native hotend fan is unavailable')
                self._fan_kind = operation
                self._old_fan_speed = self.fan.get_status(self.reactor.monotonic()).get('speed', 0.)
                (self.fan if operation == 'FAN_PRINT' else self.hotend_fan.fan).set_speed(1.)
                self._deadline = self.reactor.monotonic() + self.fan_time
            self.activity()
        except Exception as exc:
            self._fault(str(exc))
            raise
        finally:
            self._executing = False

    def _restore_fan(self):
        kind = self._fan_kind
        if kind == 'FAN_PRINT':
            self.fan.set_speed(self._old_fan_speed or 0.)
        elif kind == 'FAN_HOTEND' and self.hotend_fan is not None:
            # Force the native thermostat to reevaluate; never command a
            # hard-coded zero on protective cooling.
            self.hotend_fan.last_speed = -1.
            self.hotend_fan.callback(self.reactor.monotonic())
        self._fan_kind = None

    def stop(self, reason='operator'):
        if self.state in ('IDLE', 'COMPLETE', 'SLEEP'):
            return
        if self.state == 'FAULT':
            self._off()
            return
        moving = self.state == 'MOVING'
        self.token += 1
        token = self.token
        self._move_permit = None
        previous_executing = self._executing
        self._executing = True
        try:
            failures = self._off()
            if failures:
                raise self._error('heater cleanup failed: ' + '; '.join(failures))
            self._restore_fan()
            if token != self.token or self.printer.is_shutdown():
                return
            self._expected_targets = None
            self.state, self.reason, self.operation = 'IDLE', reason, None
            self.activity()
            if moving:
                self._fault('cancelled during queued Z jog; position is untrusted')
        except Exception as exc:
            self._fault('service cleanup failed: ' + str(exc))
            raise
        finally:
            self._executing = previous_executing

    def _fault(self, reason):
        self.token += 1
        self._move_permit = None
        self.state, self.reason = 'FAULT', reason
        from .m300_error_codes import report
        report(self.printer, reason, source='m300_maintenance', fatal=True)
        try:
            self._off()
        finally:
            if not self.printer.is_shutdown():
                self.printer.invoke_async_shutdown('M300 maintenance: ' + reason)

    def sleep(self):
        self._idle()
        self.token += 1
        token = self.token
        self.state, self.reason = 'SLEEPING', ''
        self._executing = True
        try:
            failures = self._off()
            if failures:
                raise self._error('Sleep heater cleanup failed: ' + '; '.join(failures))
            self.job.sd.cancel()
            self.toolhead.wait_moves()
            if token != self.token or not self.ready or self.printer.is_shutdown():
                return
            self.job.steppers.motor_off()
            if token == self.token:
                self.state = 'SLEEP'
        except Exception as exc:
            self._fault('Sleep failed: ' + str(exc))
            raise
        finally:
            self._executing = False

    def wake(self):
        if self.state not in ('SLEEP', 'SLEEPING'):
            raise self._error('wake requires sleep')
        self.token += 1
        failures = self._off()
        if failures:
            self._fault('Wake heater cleanup failed: ' + '; '.join(failures))
            raise self._error('Wake heater cleanup failed')
        self.state, self.reason, self.operation = 'IDLE', '', None
        self.activity()
        # No homing, enable, target restoration, file selection or ARM.

    def wake_for_operator_motion(self):
        """Explicit operator motion may leave passive SLEEP, never an active job.

        Wake keeps all lost native homing state invalid and never restores a
        heater target, position, file or ARM. The requested native command is
        still subject to its normal motion/clearance/MCU authority checks.
        """
        if (self.wake_on_motion and self.ready and self.state == 'SLEEP'
                and not self._executing and not self.printer.is_shutdown()):
            self.wake()

    def wake_for_operator_control(self):
        """An explicit heater/fan/PID request may leave passive sleep.

        This only releases the passive UI sleep owner. Native temperature,
        MCU authority and concurrent-service checks still apply to the new
        request. No old target, move, file, calibration or ARM is replayed.
        """
        if (getattr(self, 'wake_on_control', False) and self.ready
                and self.state == 'SLEEP' and not self._executing
                and not self.printer.is_shutdown()):
            self.wake()

    def _setting(self, name, default):
        nvm = self.printer.lookup_object('m300_nvm', None)
        return default if nvm is None else nvm.get_setting(name, default)

    def _setting_changed(self, name, value):
        if not self.ready:
            return
        if name == 'sound' and not value:
            self._pin('m300_buzzer', 0)
            self._beep_until = 0.
        if name in ('light_mode', 'led_brightness'):
            self._indicators(self.reactor.monotonic())

    def _pin(self, name, value):
        output = self.printer.lookup_object('output_pin ' + name, None)
        if output is not None:
            if not getattr(output, 'is_pwm', True):
                value = bool(value)
            output.gcrq.send_async_request(float(value))

    def click(self):
        self.activity()
        if self.ready and self._setting('sound', True):
            self._pin('m300_buzzer', 1)
            self._beep_until = self.reactor.monotonic() + .05

    def _indicator_state(self, now):
        """One printer-state policy, independent of the open OLED/Fluidd page."""
        if self.state == 'FAULT':
            return 'ERROR'
        errors = self.printer.lookup_object('m300_errors', None)
        current = getattr(errors, 'current', None)
        if current is not None and (not isinstance(current, dict) or current.get('fatal')
                                    or current.get('severity', 'error') != 'info'):
            return 'ERROR'
        busy = self.is_busy()
        paused = False
        heating = self.state == 'HEATING'
        stats = self.printer.lookup_object('print_stats', None)
        if stats is not None:
            try:
                native_state = stats.get_status(now).get('state')
                if native_state == 'error':
                    return 'ERROR'
                paused = native_state == 'paused'
                busy = busy or native_state == 'printing'
            except Exception:
                return 'ERROR'
        native_pause = self.printer.lookup_object('pause_resume', None)
        control=self.printer.lookup_object('m300_print_control',None)
        if control is not None and control.state in ('STARTING','ENDING','CANCELLING'):
            paused=False  # Native SD worker barrier is not an operator pause.
        paused = paused or bool(getattr(native_pause, 'is_paused', False))
        for name in ('m300_job', 'm300_filament', 'm300_calibration',
                     'm300_motion', 'm300_sd', 'm300_nvm', 'm300_fans',
                     'm300_thermal', 'm300_pad_mesh', 'm300_print_control'):
            obj = self.job if name == 'm300_job' else self.printer.lookup_object(name, None)
            if obj is None:
                continue
            try:
                status = getattr(obj, 'get_ownership_status', obj.get_status)(now)
                if (not isinstance(status, dict) or type(status.get('busy')) is not bool
                        or not isinstance(status.get('state'), str) or not status['state'].strip()):
                    return 'ERROR'
                state = status['state'].upper()
                if state in ('FAULT', 'FAILED', 'FILE_ERROR', 'ERROR'):
                    return 'ERROR'
                paused = paused or state in ('PAUSING', 'PAUSED', 'RESUMING')
                phase = str(status.get('phase', '')).upper()
                heating = heating or (status['busy'] and (
                    state in ('HEATING', 'CHECK_HEATING', 'PID_RUNNING')
                    or phase in ('HEATING', 'Z_PREHEAT', 'PREHEAT')))
                busy = busy or status['busy'] or state in ('SLEEP', 'SLEEPING')
            except Exception:
                return 'ERROR'
        targets = False
        try:
            for heater in (self.job.hotend, self.job.bed):
                measured, target = heater.get_temp(now)
                if not all(math.isfinite(v) for v in (measured, target)) or target < 0.:
                    return 'ERROR'
                targets = targets or target > 0.
                heating = heating or target > 0. and measured < target - 2.
        except Exception:
            return 'ERROR'
        if paused:
            return 'PAUSE'
        if heating:
            return 'HEATING'
        if busy:
            return 'WORKING'
        return 'HEATING' if targets else 'READY'

    def status_led_rgb(self, now):
        self._light_state = self._indicator_state(now)
        if self._light_state == 'ERROR':
            if self._light_error_since is None:
                self._light_error_since = now
            phase = int(max(0., now - self._light_error_since) // LED_ERROR_SECONDS)
            return LED_ERROR_COLORS[phase % len(LED_ERROR_COLORS)]
        self._light_error_since = None
        return LED_COLORS[self._light_state]

    def _dynamic_lights(self, now):
        return self.status_led_rgb(now)

    def _indicators(self, now):
        if self._beep_until and now >= self._beep_until:
            self._pin('m300_buzzer', 0)
            self._beep_until = 0.
        light = self._setting('light_mode', 'DYNAMIC')
        asleep = self.state in ('SLEEP', 'SLEEPING')
        automatic = self.status_led_rgb(now)
        if self._light_state == 'ERROR':
            values = automatic
        elif light == 'DISABLE' or asleep and not self._setting('sleep_light', False):
            values = (0, 0, 0)
        elif light == 'WHITE':
            values = (1, 1, 1)
        else:
            values = automatic
        brightness = self._setting('led_brightness', MAX_BRIGHTNESS) / MAX_BRIGHTNESS
        values = tuple(value * brightness for value in values)
        if values != self._lights:
            for color, value in zip('rgb', values):
                self._pin('m300_led_' + color, value)
            self._lights = values

    def _tick(self, now):
        if not self.ready or self.printer.is_shutdown():
            return self.reactor.NEVER
        try:
            self._indicators(now)
            if getattr(self.board, 'native_control', False):
                # Native idle_timeout owns inactivity. OEM RGB is observation
                # only and must not acquire a sleep/maintenance motion lock.
                return now + .5
            if self.state in ('HEATING', 'HOLD', 'MOVING', 'FAN_TEST'):
                temperatures = self._authority(self.state == 'MOVING')
                if self._expected_targets is not None:
                    for name, (_, target) in temperatures.items():
                        if target != self._expected_targets[name]:
                            raise self._error('service temperature changed externally')
                    if all(target == 0. or abs(measured-target) <= 2.
                           for measured, target in temperatures.values()):
                        self.state = 'HOLD'
                if self.state == 'MOVING' and self.job._queue_drained(now):
                    self.state, self.operation = 'COMPLETE', None
                elif now >= self._deadline:
                    if self.state == 'FAN_TEST':
                        token = self.token
                        self._restore_fan()
                        if token == self.token and not self.printer.is_shutdown():
                            self.state, self.operation = 'COMPLETE', None
                    elif self.state == 'MOVING':
                        raise self._error('Z jog deadline exceeded')
                    else:
                        self.stop('service timeout; heating switched off')
            elif self.state in ('IDLE', 'COMPLETE'):
                seconds = {'OFF': 0, '15MIN': 900, '30MIN': 1800, '60MIN': 3600}.get(
                    self._setting('sleep_mode', '15MIN'), 0)
                if seconds and now-self._last_activity >= seconds:
                    if any(h.get_temp(now)[1] for h in (self.hotend, self.bed)):
                        self.activity()
                    else:
                        try:
                            self._idle()
                        except Exception:
                            self.activity()
                        else:
                            self.sleep()
        except Exception as exc:
            self._fault(str(exc))
        return now + .1

    def get_status(self, now):
        return {'state': self.state, 'busy': self.is_busy(), 'ready': self.ready,
                'wake_on_motion': self.wake_on_motion,
                'wake_on_control': getattr(self, 'wake_on_control', False),
                'qualified': self.qualified, 'hardware_qualified': False,
                'session_token': self.token, 'operation': self.operation,
                'reason': self.reason, 'deadline': self._deadline,
                'sleep': self.state in ('SLEEP', 'SLEEPING'),
                'status_led': {'revision': '0.13.16.21-STATUS-LED',
                               'state': self._light_state, 'rgb': self._lights,
                               'error_step_seconds': LED_ERROR_SECONDS,
                               'error_since': self._light_error_since},
                'wake_heats': False, 'wake_restores_position': False}

    def cmd_service(self, gcmd):
        if set(gcmd.get_command_parameters()) - {'OP', 'VALUE'}:
            raise gcmd.error('ZORTRAX_SERVICE accepts OP and VALUE only')
        self.start(gcmd.get('OP').upper(), gcmd.get_float('VALUE', None))

    def cmd_stop(self, gcmd):
        self.stop()

    def cmd_sleep(self, gcmd):
        self.sleep()

    def cmd_wake(self, gcmd):
        self.wake()

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_MAINTENANCE ' + json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))


def load_config(config):
    board=config.get_printer().load_object(config,'m300_mcu')
    if getattr(board,'native_control',False):
        from .m300_native_maintenance import M300NativeMaintenance
        return M300NativeMaintenance(config)
    return M300Maintenance(config)
