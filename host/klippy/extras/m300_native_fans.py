# SPDX-License-Identifier: GPL-3.0-or-later
"""OEM interactive fan test over the two existing native fan queues.

Upper = channel 1 / PE14; lower = channel 0 / PE13. OEM requests toggle
0/150, not 0/255. The 50/45 C hotend thermostat is a floor, never disabled.
All temporary wrappers exist only during the explicitly owned test session.
"""
import math

from .m300_fans import M300Fans
from .m300_native_service import NativeServiceLease, lock_command, require_idle_print, unlock_command

OEM_DUTY = 150. / 255.
COOLING_ON = 50.
COOLING_OFF = 45.


class M300NativeFans(M300Fans):
    def __init__(self, config):
        super().__init__(config)
        # Bind before klippy:ready: heater_fan.handle_ready registers the
        # current callback with its existing timer. The native Fan/PWM queue
        # and shutdown speed remain the only host output owner.
        self._cooling_on = True  # Unknown startup state is protective.
        self.hotend = self.printer.load_object(config, 'heater_fan hotend')
        self.hotend.callback = self._cooling_callback
        self._output_methods, self._output_commands = [], []
        self.lease = NativeServiceLease(self, lambda: (self.token, self.phase),
            self._stationary, lambda reason: self.end_oem('CANCELLED', reason))

    def _ready(self):
        super()._ready()
        # A configured MCU can retain a preceding host's ON request. Reset
        # both host caches so native Fan._apply_speed cannot discard the
        # first cold OFF as an assumed no-op. The write still uses its queue.
        self.hotend.last_speed = self.owners['HOTEND'].last_fan_value = -1.
        self.toolhead = self.printer.lookup_object('toolhead')
        self.gcode_move = self.printer.lookup_object('gcode_move')
        self.job = self.printer.lookup_object('m300_job')
        self.timeout = self.printer.lookup_object('m300_maintenance').timeout

    def _stationary(self):
        raise self._error('fan test does not authorize movement')

    def _upper_policy(self, now):
        # Temperature alone drives automatic cooling. A heater target is not
        # evidence that a cold heatsink needs cooling yet. get_temp() returns
        # zero for stale data; unknown/invalid temperature stays protective.
        temperatures = []
        for heater in self.hotend.heaters:
            measured, target = heater.get_temp(now)
            if (not math.isfinite(measured) or not math.isfinite(target)
                    or not heater.min_temp < measured <= heater.max_temp):
                return 1.
            temperatures.append(measured)
        if not temperatures:
            return 1.
        hottest = max(temperatures)
        on = (True if hottest >= COOLING_ON else False if hottest <= COOLING_OFF
              else self._cooling_on)
        return self.hotend.fan_speed if on else 0.

    def _cooling_callback(self, now):
        try:
            speed = self._upper_policy(now)
            self._cooling_on = bool(speed)
            if speed != self.hotend.last_speed:
                self.hotend.last_speed = speed
                self.hotend.fan.set_speed(speed)
        except Exception as exc:
            self._failed(exc)
            return self.reactor.NEVER
        return now + 1.  # Keep the native heater_fan timer cadence.

    def _upper(self, value, *args, **kwargs):
        requested = OEM_DUTY if self.test and self.test['upper'] else 0.
        return self._hotend_async(max(value, requested,
            self._upper_policy(self.reactor.monotonic())), *args, **kwargs)

    def _apply_upper(self):
        self.hotend.last_speed = -1.
        self.hotend.callback(self.reactor.monotonic())

    def _lock_outputs(self):
        def blocked(*args, **kwargs):
            raise self._error('interactive fan test owns outputs; use its toggles or Back')
        for obj, name, wrapper in ((self.owners['PRINT'], 'set_speed', blocked),
                (self.owners['PRINT'], 'set_speed_from_command', blocked),
                (self.owners['HOTEND'], 'set_speed', self._upper)):
            self._output_methods.append((obj, name, getattr(obj, name), wrapper))
            setattr(obj, name, wrapper)
        for name in ('M106', 'M107', 'SET_FAN_SPEED'):
            record = lock_command(self.gcode, name, blocked)
            if record is not None:
                self._output_commands.append(record)

    def _unlock_outputs(self):
        for record in reversed(self._output_commands):
            unlock_command(self.gcode, record)
        self._output_commands.clear()
        for obj, name, original, wrapper in reversed(self._output_methods):
            if getattr(obj, name) == wrapper:
                setattr(obj, name, original)
        self._output_methods.clear()

    def start_oem(self):
        self._control()
        require_idle_print(self.printer, self.reactor.monotonic())
        if self.test is not None:
            raise self._error('a fan test is already active')
        self._peers_idle()
        # An already accepted future request must not overwrite this session.
        if any(owner.gcrq.rqueue for owner in self.owners.values()):
            raise self._error('wait for pending native fan requests to drain')
        now = self.reactor.monotonic()
        self.token += 1
        self.phase += 1
        self.test = dict(channel='BOTH', upper=False, lower=False,
            restore_speed=self.sources['PRINT'](now)['speed'],
            started=now, deadline=now+self.timeout)
        self.state, self.reason = 'FAN_TEST', ''
        try:
            self.lease.acquire(self.toolhead, self.gcode_move, (self.job.hotend, self.job.bed))
            self._lock_outputs()
            self._print_async(0.)
            self._apply_upper()
        except Exception as exc:
            self._unlock_outputs()
            self.lease.release()
            self._failed(exc)
            raise
        self.reactor.update_timer(self.timer, self.reactor.NOW)
        return self.token

    def toggle(self, channel, token, phase):
        if (channel not in ('UPPER', 'LOWER') or type(token) is not int
                or type(phase) is not int or token != self.token or phase != self.phase
                or self.test is None):
            raise self._error('expired or invalid fan-test action')
        self._control()
        key = channel.lower()
        self.test[key] = not self.test[key]
        self.phase += 1
        try:
            if key == 'upper':
                self._apply_upper()
            else:
                self._print_async(OEM_DUTY if self.test['lower'] else 0.)
        except Exception as exc:
            self._unlock_outputs()
            self.lease.release()
            self._failed(exc)
            raise

    def end_oem(self, state='COMPLETE', reason='Back to Maintenance'):
        test, self.test = self.test, None
        if test is None:
            return
        self.phase += 1
        self.state, self.reason = state, reason
        if state == 'FAULT':
            from .m300_error_codes import report
            report(self.printer, reason, source='m300_fans', fatal=self.printer.is_shutdown())
        self._unlock_outputs()
        self.lease.release()
        try:
            forced, fresh = self._cooling(self.reactor.monotonic())
            if fresh and forced is False:
                self._print_async(test['restore_speed'])
                self._apply_upper()  # Current native policy, never cached OFF.
        except Exception as exc:
            self._failed(exc)
        self.reactor.update_timer(self.timer, self.reactor.NEVER)

    def cancel(self, token):
        if type(token) is not int or token != self.token or self.test is None:
            raise self._error('expired fan-test cancellation')
        self.end_oem('CANCELLED', 'Operator cancelled fan test')

    def invalidate(self, *args):
        fault=(self.state,self.reason) if self.state=='FAULT' else None
        self._unlock_outputs()
        self.lease.release()
        super().invalidate(*args)
        if fault is not None:
            self.state,self.reason=fault

    def _tick(self, now):
        if not self.ready or self.test is None:
            return self.reactor.NEVER
        forced, fresh = self._cooling(now)
        if forced or not fresh:
            self.end_oem('FAULT', 'MCU protective cooling or stale status ended fan test')
            return self.reactor.NEVER
        if now >= self.test['deadline']:
            self.end_oem('CANCELLED', 'Fan-test deadline expired')
            return self.reactor.NEVER
        # Native heater_fan still owns its own thermostat callback/timing.
        return now+.1

    def get_ownership_status(self, now):
        # The common LED/lease observer needs no ADC/fan/MCU snapshot.
        return {'state': self.state, 'busy': self.test is not None or self.sync_pending}

    def get_status(self, now):
        status = super().get_status(now)
        test = self.test or {}
        return dict(status, native_control=True, operation='FAN_TEST',
            fan_revision='0.13.16.14-THERMOSTAT-50-45',
            hotend_auto_threshold=COOLING_ON, hotend_auto_off_threshold=COOLING_OFF,
            hotend_auto_hysteresis=COOLING_ON-COOLING_OFF,
            hotend_auto_uses_target=False, hotend_auto_latched_on=self._cooling_on,
            upper_enabled=test.get('upper', False),
            lower_enabled=test.get('lower', False), upper_cooling=bool(self._upper_policy(now))
            if self.hotend is not None else True,
            can_toggle_upper=self.ready and self.test is not None,
            can_toggle_lower=self.ready and self.test is not None,
            can_back=self.ready and self.test is not None, oem_test_duty=OEM_DUTY)

    def rows(self, now):
        if self.test is not None:
            return self.printer.lookup_object('m300_procedures').rows(now)
        return super().rows(now)
