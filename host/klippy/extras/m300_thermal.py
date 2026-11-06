# SPDX-License-Identifier: GPL-3.0-or-later
"""Thermal commissioning and optional native heater control/PID integration.

No PID mathematics, new ADC/GPIO owners, motion, automatic ARM, or automatic
SAVE_CONFIG. Native PID runs cooperatively outside the G-code mutex so Stop
and the shared operator view remain usable during the native temperature wait.
"""
import json
import math

NAMES = ('extruder', 'heater_bed')
PEERS = ('m300_job', 'm300_filament', 'm300_calibration', 'm300_motion',
         'm300_maintenance', 'm300_fans', 'm300_sd', 'm300_nvm')
IDLE = ('IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR')
PID_OPTIONS = ('control', 'pid_Kp', 'pid_Ki', 'pid_Kd')
# The configured/native PID envelope stays at 100%. Only this initial
# channel-response probe limits energy before a PID controller is measured.
CHECK_PWM = {'extruder': .20, 'heater_bed': .50}
COAST_MIN_SECONDS = 90.
COAST_MAX_SECONDS = 600.


class M300Thermal:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.native_control = config.getboolean('native_control', False)
        self.ready = self.bound = self.running_native = False
        self.active = False
        self.state, self.reason = 'IDLE', ''
        self.token = self.phase = 0
        self.selected = None
        self.target = self.deadline = self.started = 0.
        self.hold_since = None
        self.initial = {}
        self.checks, self.results = {}, {}
        self.observation = None
        self.coast_trace = []
        self.capture = None
        self.old_control = None
        self.idle_saved = None
        self.timer = self.reactor.register_timer(self._tick)
        self.printer.register_event_handler('klippy:connect', self._connect)
        self.printer.register_event_handler('klippy:ready', self._ready)
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self.invalidate)
        for name, callback in (
                ('THERMAL_STATUS', self.cmd_status), ('THERMAL_ARM', self.cmd_arm),
                ('THERMAL_CHECK', self.cmd_check), ('THERMAL_STOP', self.cmd_stop),
                ('THERMAL_SAVE', self.cmd_save)):
            self.gcode.register_command(name, callback, when_not_ready=name.endswith('STATUS'))

    def _error(self, message):
        return self.printer.command_error('Thermal test: ' + str(message))

    def _connect(self):
        self.board = self.printer.lookup_object('m300_mcu')
        self.heaters = {n: self.printer.lookup_object('heaters').lookup_heater(n) for n in NAMES}
        self.toolhead = self.printer.lookup_object('toolhead')
        self.configfile = self.printer.lookup_object('configfile')
        self.idle = self.printer.lookup_object('idle_timeout')
        if self.bound:
            return
        if getattr(self.board, 'native_control', False):
            self.native_require = self.board.require_heating
            self.bound = True
            return
        self.native_require = self.board.require_heating
        def require_heating():
            self.native_require()
            if not self.native_control and (not self.active or self.state not in ('CHECK_HEATING', 'CHECK_HOLD', 'PID_RUNNING')):
                raise self._error('positive heating belongs to an active thermal operation')
        self.board.require_heating = require_heating
        for name, heater in self.heaters.items():
            original_pwm = heater.set_pwm
            def probe_pwm(read_time, value, original=original_pwm, name=name):
                if self.active and self.state.startswith('CHECK_'):
                    value = (min(value, CHECK_PWM[name])
                             if name == self.selected and self.state == 'CHECK_HEATING'
                             else 0.)
                return original(read_time, value)
            heater.set_pwm = probe_pwm
            for method in ('set_temp', 'alter_target'):
                original = getattr(heater, method)
                def target(value, original=original, name=name):
                    if not math.isfinite(value):
                        raise self._error('nonfinite target')
                    if value > 0.:
                        if ((not self.native_control or self.active or self.running_native)
                                and (not self.active or name != self.selected
                                or self.state not in ('CHECK_HEATING', 'CHECK_HOLD', 'PID_RUNNING')
                                or value > self.target)):
                            raise self._error('heater/target is outside the current thermal operation')
                        self.native_require()
                    return original(value)
                setattr(heater, method, target)
        self.native_pid = self.gcode.register_command('PID_CALIBRATE', None)
        if self.native_pid is None:
            raise self._error('native PID_CALIBRATE must be registered before the thermal module')
        self.gcode.register_command('PID_CALIBRATE', self.cmd_pid)
        # Stop commands remain usable because PID executes in a cooperative
        # callback rather than holding the serial G-code command mutex.
        for name in ('M104', 'M140', 'SET_HEATER_TEMPERATURE', 'TURN_OFF_HEATERS'):
            original = self.gcode.register_command(name, None)
            if original is None:
                continue
            def external_target(gcmd, original=original, name=name):
                value = (0. if name == 'TURN_OFF_HEATERS' else
                         gcmd.get_float('TARGET' if name == 'SET_HEATER_TEMPERATURE' else 'S', 0.))
                if value > 0. and (not self.native_control or self.active or self.running_native):
                    raise self._error('use a thermal check or PID; manual positive targets are disabled in this test profile')
                if self.active:
                    self.stop('external heater-off command')
                return original(gcmd)
            self.gcode.register_command(name, external_target)
        for name in ('M106', 'M107', 'SET_FAN_SPEED', 'SAVE_CONFIG',
                     'M109', 'M190', 'TEMPERATURE_WAIT'):
            original = self.gcode.register_command(name, None)
            if original is None:
                continue
            def command(gcmd, original=original, name=name):
                if self.active or self.running_native:
                    raise self._error(name + ' is unavailable during the current thermal operation')
                return original(gcmd)
            self.gcode.register_command(name, command)
        self.native_config_set = self.configfile.set
        def capture_result(section, option, value):
            if self.running_native and section == self.selected and option in PID_OPTIONS:
                if self.state != 'PID_RUNNING' or not self.active:
                    raise self._error('cancelled PID result was discarded')
                self.capture[option] = str(value)
                return
            return self.native_config_set(section, option, value)
        self.configfile.set = capture_result
        self.bound = True

    def _ready(self):
        self.ready = True
        if getattr(self.board, 'native_control', False):
            return
        self.reactor.update_timer(self.timer, self.reactor.monotonic() + .2)

    def _temperatures(self, now):
        result = {}
        for name, heater in self.heaters.items():
            stamp, raw = self.board.adcs[name].get_last_value()
            age = self.board.get_mcu().estimated_print_time(now) - stamp
            current, target = heater.get_temp(now)
            if (stamp <= 0. or not 0. <= age < 1. or not math.isfinite(raw)
                    or not 0. < raw < 1. or not math.isfinite(current)
                    or not heater.min_temp <= current <= heater.max_temp):
                raise self._error('stale/invalid native temperature: ' + name)
            result[name] = (current, target)
        return result

    def _idle(self):
        if self.native_control:
            maintenance = self.printer.lookup_object('m300_maintenance', None)
            wake = getattr(maintenance, 'wake_for_operator_control', None)
            if wake is not None:
                wake()
        if not self.ready or self.printer.is_shutdown():
            raise self._error('Klipper is not Ready')
        if self.active or self.running_native or self.state == 'FAULT':
            raise self._error('operation active or fault latched')
        for name in PEERS:
            peer = self.printer.lookup_object(name, None)
            if peer is None:
                continue
            status = peer.get_status(self.reactor.monotonic())
            state = status.get('state') if isinstance(status, dict) else None
            if (not isinstance(status, dict) or status.get('busy') is not False
                    or not isinstance(state, str) or state.upper() not in IDLE):
                raise self._error(name + ' owns resources')
        queued, current, empty = self.toolhead.check_busy(self.reactor.monotonic())
        if not empty or queued > current:
            raise self._error('native motion queue must be drained')

    def _profile(self):
        if ((not self.native_control and (self.board.allow_motion or self.board.gates != 2))
                or (self.native_control and not self.board.gates & 2)
                or not self.board.allow_actuators or not self.board.allow_heating):
            raise self._error('requires explicit heating permissions' if self.native_control else
                              'requires the explicit heating-only profile: gates=2, motion=False')
        if self.board.get_mcu().is_fileoutput():
            raise self._error('FILEOUTPUT cannot qualify physical heating')

    def _preflight(self, heater, target, check=False):
        self._profile()
        self._idle()
        self.native_require()  # Fresh acknowledged native MCU ARM, unchanged.
        if heater not in NAMES or type(target) not in (int, float) or not math.isfinite(target):
            raise self._error('finite target and a known heater are required')
        cap = 60. if check else self.heaters[heater].max_temp - 5.
        if not 30. <= target <= min(cap, self.heaters[heater].max_temp - 5.):
            raise self._error('target outside bounded test/native limits')
        temps = self._temperatures(self.reactor.monotonic())
        if any(t[1] != 0. for t in temps.values()):
            raise self._error('both heater targets must start at zero')
        outside = ['%s=%.2fC' % (n, t[0]) for n, t in temps.items() if not 10. <= t[0] <= 45.]
        if check and outside:
            raise self._error('low-temperature checks start with both sensors at 10..45C; ' + ', '.join(outside))
        if check and target < temps[heater][0] + 5.:
            raise self._error('check target must be at least 5C above the initial reading')
        if not check and not self.native_control and set(self.checks) != set(NAMES):
            raise self._error('complete both low-temperature heater/sensor checks in this host session first')
        for name, obj in self.heaters.items():
            if not 0. < obj.get_max_power() <= 1.:
                raise self._error('power must be within native 0..1: ' + name)
        return temps

    def _begin(self, heater, target, state, seconds):
        self.token += 1
        self.phase += 1
        self.selected, self.target = heater, float(target)
        self.state, self.reason, self.active = state, '', True
        self.started = self.reactor.monotonic()
        self.deadline = self.started + seconds
        self.hold_since = None
        self.initial = {n: h.get_temp(self.started)[0] for n, h in self.heaters.items()}
        self.idle_saved = self.idle.idle_timeout
        self._idle_timeout(max(self.idle_saved, seconds + 60.))
        self.reactor.update_timer(self.timer, self.reactor.NOW)
        maintenance = self.printer.lookup_object('m300_maintenance', None)
        if maintenance is not None:
            maintenance.activity()

    def _idle_timeout(self, seconds):
        command = self.gcode.create_gcode_command('SET_IDLE_TIMEOUT', 'SET_IDLE_TIMEOUT',
                                                  {'TIMEOUT': str(seconds)})
        self.idle.cmd_SET_IDLE_TIMEOUT(command)

    def start_check(self, heater, target):
        self._preflight(heater, target, True)
        self._begin(heater, target, 'CHECK_HEATING', 180. if heater == 'extruder' else 600.)
        self.checks.pop(heater, None)
        self.observation = {'heater': heater, 'target': target,
                            'initial_temperature': self.initial[heater],
                            'peak_temperature': self.initial[heater],
                            'probe_pwm_limit': CHECK_PWM[heater],
                            'power_off_at': None, 'power_off_temperature': None,
                            'coast_elapsed': 0., 'qualified': False}
        self.coast_trace = []
        try:
            self.heaters[heater].set_temp(target)
        except Exception:
            self.stop('heater check could not start', fault=True)
            raise

    def cmd_pid(self, gcmd):
        heater = gcmd.get('HEATER')
        target = gcmd.get_float('TARGET')
        if gcmd.get_int('WRITE_FILE', 0) != 0:
            raise self._error('WRITE_FILE is disabled in the commissioning wrapper')
        self._preflight(heater, target)
        self._begin(heater, target, 'PID_RUNNING', 1200. if heater == 'extruder' else 2400.)
        token = self.token
        # Return control to GCodeIO. Its command lock is NOT held during the
        # native wait, allowing status and explicit stop to be processed.
        self.reactor.register_callback(lambda now: self._run_pid(token, gcmd))
        gcmd.respond_info('Native PID queued; PID_STOP remains available; SAVE_CONFIG is separate')

    def _run_pid(self, token, gcmd):
        if token != self.token or not self.active or not self.ready:
            return
        heater = self.heaters[self.selected]
        self.old_control = heater.control
        self.running_native, self.capture = True, {}
        try:
            self.native_pid(gcmd)  # Original native handler and PID mathematics.
            if token != self.token or not self.ready or self.state != 'PID_RUNNING' or not self.active:
                return
            values = dict(self.capture)
            if values.get('control') != 'pid' or set(values) != set(PID_OPTIONS):
                raise self._error('native PID returned an incomplete result')
            if any(not math.isfinite(float(values[k])) or float(values[k]) <= 0. for k in PID_OPTIONS[1:]):
                raise self._error('native PID result is not finite/positive')
            # Transactional publication: cancellation/timeout never saves a
            # partial controller. These are pending native SAVE_CONFIG values.
            for option in PID_OPTIONS:
                self.native_config_set(self.selected, option, values[option])
            self.results[self.selected] = values
            self._finish('Native PID complete; results pending explicit PID_SAVE/SAVE_CONFIG')
        except Exception as exc:
            if token == self.token and self.ready and self.state == 'PID_RUNNING':
                self.stop('Native PID failed: ' + str(exc), fault=True)
                gcmd.respond_info(self.reason)
        finally:
            self.running_native = False
            self.capture = self.old_control = None
            if token == self.token and self.ready and self.state == 'CANCELLING':
                self._finish('Thermal operation cancelled; no PID result published', cancelled=True)

    def _off(self):
        for heater in self.heaters.values():
            heater.set_temp(0.)
            # Existing native PWM owner only. Do not wait for a later ADC
            # callback to clear the last positive output request.
            heater.set_pwm(self.board.get_mcu().estimated_print_time(self.reactor.monotonic()), 0.)

    def _finish(self, reason, cancelled=False):
        self._off()
        self.active = False
        self.phase += 1
        self.state, self.reason = ('CANCELLED' if cancelled else 'COMPLETE'), reason
        if self.idle_saved is not None:
            saved, self.idle_saved = self.idle_saved, None
            self._idle_timeout(saved)
        maintenance = self.printer.lookup_object('m300_maintenance', None)
        if maintenance is not None:
            maintenance.activity()

    def stop(self, reason='operator stop', fault=False):
        if not self.active and not self.running_native:
            return
        if self.running_native and self.old_control is not None:
            self.heaters[self.selected].set_control(self.old_control)
        self.state = 'FAULT' if fault else 'CANCELLING'
        self.phase += 1
        self._off()
        self.reason = reason
        if fault:
            self.active = False
            self.printer.invoke_async_shutdown('Thermal test: ' + reason)
        elif not self.running_native:
            self._finish(reason, cancelled=True)

    def cancel(self, token, phase):
        if token != self.token or phase != self.phase or not self.active:
            raise self._error('expired thermal cancellation')
        self.stop()

    def invalidate(self, *args):
        self.token += 1
        self.phase += 1
        self.ready = self.active = False
        self.idle_saved = None
        self.checks.clear()
        if self.observation is not None:
            self.observation['qualified'] = False
        self.state, self.reason = 'IDLE', 'Host lifecycle ended thermal operation; no continuation'
        self.reactor.update_timer(self.timer, self.reactor.NEVER)
        # Native shutdown/request_restart zero targets and MCU PWM; no serial
        # request is attempted after its transport has been disconnected.

    def _tick(self, now):
        if not self.ready:
            return self.reactor.NEVER
        if not self.active or self.state == 'CANCELLING':
            return now + .25
        try:
            self.native_require()
            temps = self._temperatures(now)
            if now >= self.deadline:
                raise self._error('thermal deadline exceeded; no automatic power increase')
            other = next(n for n in NAMES if n != self.selected)
            if temps[other][1] != 0.:
                raise self._error('nonselected heater target changed')
            if self.state.startswith('CHECK_'):
                current = temps[self.selected][0]
                self.observation['peak_temperature'] = max(
                    self.observation['peak_temperature'], current)
                if current > self.target + 10.:
                    raise self._error('low-temperature peak %.2fC exceeded %.2fC' %
                                      (current, self.target+10.))
                rise = temps[self.selected][0] - self.initial[self.selected]
                other_rise = temps[other][0] - self.initial[other]
                if other_rise >= 3. and rise < 1.:
                    raise self._error('wrong sensor/channel appears to be warming')
                # Do not hold an untuned full-power watermark heater at the
                # target. Remove power on entry, then observe its delayed peak.
                if self.state == 'CHECK_HEATING' and current >= self.target - 2.:
                    self._off()
                    self.state = 'CHECK_COAST'
                    self.phase += 1
                    self.observation.update(power_off_at=now, power_off_temperature=current)
                    self.coast_trace = [(now, current)]
                    self.deadline = now + COAST_MAX_SECONDS
                    self._idle_timeout(max(self.idle_saved, COAST_MAX_SECONDS + 60.))
                elif self.state == 'CHECK_COAST':
                    if any(target != 0. for _, target in temps.values()):
                        raise self._error('heater target changed during zero-power observation')
                    elapsed = now - self.observation['power_off_at']
                    self.observation['coast_elapsed'] = elapsed
                    if not self.coast_trace or now - self.coast_trace[-1][0] >= 1.:
                        self.coast_trace.append((now, current))
                        while len(self.coast_trace) > 2 and self.coast_trace[1][0] < now - 20.:
                            self.coast_trace.pop(0)
                    first_time, first_temp = self.coast_trace[0]
                    cooling = (now-first_time >= 15. and current <= first_temp-.2
                               and self.observation['peak_temperature']-current >= 2.)
                    if elapsed >= COAST_MIN_SECONDS and cooling and current <= self.target + 2.:
                        self.observation['qualified'] = True
                        self.checks[self.selected] = {
                            'initial': self.initial[self.selected], 'target': self.target,
                            'power_off_temperature': self.observation['power_off_temperature'],
                            'peak_temperature': self.observation['peak_temperature'],
                            'coast_seconds': elapsed,
                            'physical_mapping_requires_operator_observation': True}
                        self._finish('Low-temperature response and delayed cooling peak checked; observe physical channel before PID')
        except Exception as exc:
            self.stop(str(exc), fault=True)
        return now + .1

    def led_rgb(self, now):
        indicators = self.printer.lookup_object('m300_maintenance', None)
        if indicators is not None and getattr(indicators, 'ready', False):
            # Ownership/temperature reads in the common policy do not call
            # this diagnostic, so the same state colors need no second writer.
            return indicators.status_led_rgb(now)
        if self.state == 'FAULT':
            return (1, 0, 0)
        try:
            temperatures = [h.get_temp(now) for h in self.heaters.values()]
            if self.state in ('CHECK_HEATING', 'PID_RUNNING') or any(
                    target > 0. and current < target-2. for current, target in temperatures):
                return (1, 0, 0)
            if self.active:
                return (1, 1, 1)
            if any(target > 0. for current, target in temperatures):
                return (1, 0, 0)
        except Exception:
            return (1, 0, 0)
        return (0, 1, 0)

    def get_ownership_status(self, now):
        return {'state': self.state if self.ready else 'FAULT',
                'busy': self.active or self.running_native}

    def get_status(self, now):
        temperatures = {}
        if self.bound:
            for name, heater in self.heaters.items():
                current, target = heater.get_temp(now)
                stamp, raw = self.board.adcs[name].get_last_value()
                age = self.board.get_mcu().estimated_print_time(now) - stamp
                temperatures[name] = {'temperature': current, 'target': target,
                                      'sample_fresh': stamp > 0. and 0. <= age < 1.,
                                      'power_request': getattr(heater, 'last_pwm_value', None)}
        if getattr(getattr(self, 'board', None), 'native_control', False):
            return {'installed': True, 'ready': self.ready,
                    'revision': '0.13.15-NATIVE-THERMAL',
                    'state': 'NATIVE', 'busy': False, 'native_control': True,
                    'native_heating': any(h.get_temp(now)[1] > 0. for h in self.heaters.values()),
                    'temperatures': temperatures, 'led_rgb': self.led_rgb(now),
                    'pid_owner': 'pid_calibrate', 'save_owner': 'configfile',
                    'can_cancel': False, 'can_confirm': False, 'can_purge': False,
                    'reason': '', 'phase_id': 0, 'session_token': 0,
                    'phase_remaining': None, 'automatic_save_config': False}
        return {'installed': True, 'ready': self.ready, 'revision': '0.13.12-THERMAL-R12-NATIVE',
                'native_control': self.native_control,
                'native_heating': bool(self.bound and self.native_control and
                    any(h.get_temp(now)[1] > 0. for h in self.heaters.values())),
                'state': self.state, 'busy': self.active or self.running_native,
                'session_token': self.token, 'phase_id': self.phase,
                'heater': self.selected, 'target': self.target,
                'target_hotend': self.heaters['extruder'].get_temp(now)[1] if self.bound else 0.,
                'target_bed': self.heaters['heater_bed'].get_temp(now)[1] if self.bound else 0.,
                'phase_remaining': max(0., self.deadline-now) if self.active else None,
                'can_cancel': self.active and self.state != 'CANCELLING',
                'can_confirm': False, 'can_purge': False, 'reason': self.reason,
                'low_temperature_checks': dict(self.checks), 'pending_pid_results': dict(self.results),
                'temperatures': temperatures,
                'check_observation': dict(self.observation) if self.observation is not None else None,
                'check_pwm_limits': dict(CHECK_PWM),
                'configured_max_power': {n: h.get_max_power() for n, h in self.heaters.items()} if self.bound else {},
                'coast_min_seconds': COAST_MIN_SECONDS,
                'led_rgb': self.led_rgb(now) if self.bound else None,
                'automatic_arm': False, 'automatic_save_config': False,
                'hardware_qualified': False, 'motion_enabled': self.board.allow_motion if self.bound else False,
                'thermal_procedure_moves': False}

    def cmd_status(self, gcmd):
        gcmd.respond_info('THERMAL ' + json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))

    def cmd_arm(self, gcmd):
        if getattr(self.board, 'native_control', False):
            raise self._error('native board initializes at startup; manual thermal ARM is unnecessary')
        self._profile()
        self._idle()
        temps = self._temperatures(self.reactor.monotonic())
        if not self.native_control and any(target != 0. or not 10. <= current <= 45.
                                           for current, target in temps.values()):
            raise self._error('arm only at zero targets and plausible cold readings 10..45C')
        command = self.gcode.create_gcode_command('ZORTRAX_ARM', 'ZORTRAX_ARM', {'ACK': 'M300_LAB_QUALIFIED'})
        self.board.cmd_arm(command)  # Explicit user ARM command; existing MCU acknowledgement still required.
        gcmd.respond_info('MCU ARM requested; wait for ZORTRAX_MCU_STATUS armed=true, gates=%d. '
                         'No motion or heating started.' % self.board.gates)

    def cmd_check(self, gcmd):
        if getattr(self.board, 'native_control', False):
            raise self._error('commissioning checks are closed; use native PID_CALIBRATE')
        self.start_check(gcmd.get('HEATER'), gcmd.get_float('TARGET'))

    def cmd_stop(self, gcmd):
        self.stop()

    def cmd_save(self, gcmd):
        # A convenience alias, not another calibration store or resource owner.
        # Native SAVE_CONFIG owns pending data, file backup and restart. Its
        # existing active-thermal-operation guard still applies. Passive OLED
        # sleep and an empty *thermal* results dict do not block other native
        # calibration results or a normal no-op save.
        self.gcode.run_script_from_command('SAVE_CONFIG')


def load_config(config):
    return M300Thermal(config)
