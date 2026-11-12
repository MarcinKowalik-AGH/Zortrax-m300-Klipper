# SPDX-License-Identifier: GPL-3.0-or-later
"""M300 fan presentation and bounded tests over the existing native owners.

PE13 is print cooling; PE14 is the automatic hotend fan. No GPIO, heater,
stepper or MCU ARM owner is created here. MCU protective cooling wins.
"""
import math

CHANNELS = {'PRINT': ('fan', 'PE13'), 'HOTEND': ('heater_fan hotend', 'PE14')}
PEERS = ('m300_job', 'm300_filament', 'm300_calibration', 'm300_maintenance',
         'm300_motion', 'm300_sd', 'm300_nvm', 'm300_thermal')
IDLE = ('IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR')


class M300Fans:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.ready = self.bound = False
        self.board = self.hotend = None
        self.policy = 1
        self.thermal_ok = False
        self.sync_pending = False
        self.owners, self.sources = {}, {}
        self.test = None
        self.token = self.phase = 0
        self.state, self.reason = 'IDLE', ''
        self.timer = self.reactor.register_timer(self._tick)
        self.printer.register_event_handler('klippy:ready', self._ready)
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self.invalidate)
        for name, callback in (('ZORTRAX_FANS_STATUS', self.cmd_status),
                               ('ZORTRAX_FAN_SET', self.cmd_set),
                               ('ZORTRAX_FAN_TEST', self.cmd_test),
                               ('ZORTRAX_FAN_CANCEL', self.cmd_cancel)):
            self.gcode.register_command(name, callback,
                                        when_not_ready=name.endswith('STATUS'))

    def _error(self, message):
        return self.printer.command_error('M300 fans: ' + str(message))

    def _ready(self):
        self.board = self.printer.lookup_object('m300_mcu')
        constants = getattr(self.board.get_mcu(), 'get_constants', lambda: {})()
        self.policy = int(constants.get('M300_FAN_POLICY', 1))
        if self.policy not in (1, 2, 3):
            raise self._error('unknown MCU fan policy')
        if self.policy == 3 and int(constants.get('M300_LOCAL_COOLING_ABI', 0)) != 1:
            raise self._error('MCU fan policy 3 requires local cooling ABI 1')
        self.hotend = self.printer.lookup_object('heater_fan hotend')
        self.owners = {name: self.printer.lookup_object(key).fan
                       for name, (key, _) in CHANNELS.items()}
        if getattr(self.board, 'native_control', False):
            self.sources = {name: owner.get_status for name, owner in self.owners.items()}
            self._print_async = self.owners['PRINT'].set_speed
            self._print_command = self.owners['PRINT'].set_speed_from_command
            self._hotend_async = self.owners['HOTEND'].set_speed
            self.bound = self.ready = True
            self.thermal_ok = True
            self.sync_pending = False
            return
        if not self.bound:
            board_status = self.board.get_status
            def status_with_fan_policy(now):
                result = dict(board_status(now))
                result['fan_policy_abi'] = self.policy
                if self.policy == 2:
                    result['forced_cooling_policy'] = (
                        'both_PE13_PE14_HIGH_on_missing_configuration_stale_link_ADC_fault_or_shutdown; '
                        'native_PWM_when_healthy_independent_of_ARM')
                elif self.policy == 3:
                    result['forced_cooling_policy'] = (
                        'native_PWM_when_healthy_independent_of_ARM; '
                        'offline_local_hotend_thermostat_print_OFF; '
                        'invalid_or_stale_local_sample_or_critical_latch_both_HIGH')
                return result
            self.board.get_status = status_with_fan_policy
            self.sources = {name: owner.get_status for name, owner in self.owners.items()}
            self._print_async = self.owners['PRINT'].set_speed
            self._print_command = self.owners['PRINT'].set_speed_from_command
            self._hotend_async = self.owners['HOTEND'].set_speed
            for channel, owner in self.owners.items():
                def status(now, channel=channel):
                    raw = dict(self.sources[channel](now))
                    forced, fresh = self._cooling(now)
                    raw['requested_speed'] = raw['speed']
                    # The ordinary Fluidd widget follows the known electrical
                    # override. RPM is still native/None, never manufactured.
                    effective = self._effective(channel, now, raw['speed'])
                    if effective is not None:
                        raw['speed'] = effective
                    raw.update(forced_cooling=forced, mcu_status_fresh=fresh)
                    raw['effective_speed_known'] = effective is not None
                    return raw
                owner.get_status = status
            def print_command(value):
                if self.sync_pending:
                    raise self._error('native fan startup synchronization is pending')
                if self.test is not None:
                    raise self._error('fan test owns this output; cancel the current test first')
                return self._print_command(value)
            self.owners['PRINT'].set_speed_from_command = print_command
            def hotend_async(value, *args, **kwargs):
                if (self.test is not None and self.test['channel'] == 'HOTEND'
                        or not self._thermal_ready(self.reactor.monotonic())):
                    value = 1.  # Test may raise cooling only; auto cannot lower it.
                return self._hotend_async(value, *args, **kwargs)
            self.owners['HOTEND'].set_speed = hotend_async
            self.bound = True
        self.ready = True
        # RESTART may reuse a configured MCU holding the previous session's
        # fan values. Reassert through the existing native queues even for 0.
        self.sync_pending = True
        self.thermal_ok = False
        # Match native heater_fan's 100 ms Ready delay before the first PWM
        # request, respecting the native MCU output scheduling lead time.
        self.reactor.update_timer(self.timer, self.reactor.monotonic() + .100)

    def _thermal_ready(self, now):
        try:
            stamp, normalized = self.board.adcs['extruder'].get_last_value()
            age = self.board.get_mcu().estimated_print_time(now) - stamp
            heater = self.hotend.heaters[0]
            temperature, _ = heater.get_temp(now)
            return (stamp > 0 and 0. <= age < 1. and math.isfinite(normalized)
                    and 0. < normalized < 1. and math.isfinite(temperature)
                    and heater.min_temp <= temperature <= heater.max_temp)
        except Exception:
            return False

    def _refresh_thermal(self, now):
        good = self._thermal_ready(now)
        if not good:
            self._hotend_async(1.)
        elif not self.thermal_ok:
            self.hotend.last_speed = -1.
            self.hotend.callback(now)
        self.thermal_ok = good

    def _cooling_snapshot(self, now):
        if self.board is None:
            return None, False, {}
        try:
            status = self.board.get_status(now)
            local = status.get('local_cooling', {}) if self.policy == 3 else {}
            fresh = status.get('status_fresh') is True
            forced = status.get('forced_cooling')
            if self.policy == 3:
                if local.get('status_fresh') is not True:
                    return None, False, local
                if local.get('mode_code') == 2 and local.get('sample_valid') is not True:
                    return None, False, local
                # Both independent replies must agree before the host may
                # take ordinary control. A local override can be cold OFF.
                if local.get('mode_code') != 1:
                    return True, fresh, local
            if fresh and type(forced) is bool:
                return forced, True, local
        except Exception:
            pass
        return None, False, {}

    def _cooling(self, now):
        return self._cooling_snapshot(now)[:2]

    def _local_cooling(self, now):
        if self.board is None or self.policy != 3:
            return {}
        try:
            return self.board.get_status(now).get('local_cooling', {})
        except Exception:
            return {}

    def _effective(self, channel, now, requested, snapshot=None):
        forced, fresh, local = (self._cooling_snapshot(now)
                                if snapshot is None else snapshot)
        if self.policy != 3:
            return 1. if forced else requested if fresh else None
        if local.get('status_fresh') is not True:
            return None
        if local.get('mode_code') == 1:
            # Digital GPIO snapshots are not average native PWM duty. Use
            # the native queue value only while host/native ownership agrees.
            return requested if fresh and forced is False else None
        if local.get('mode_code') in (0, 2, 3):
            if local.get('mode_code') == 2 and local.get('sample_valid') is not True:
                return None
            level = local.get('print_on' if channel == 'PRINT' else 'hotend_on')
            return float(level) if type(level) is bool else None
        return None

    def _control(self):
        # Public set/test operations are explicit operator actions. Leaving
        # passive sleep is safe; an active service/fault remains exclusive.
        maintenance = self.printer.lookup_object('m300_maintenance', None)
        wake = getattr(maintenance, 'wake_for_operator_control', None)
        if wake is not None:
            wake()
        if not self.ready or self.printer.is_shutdown():
            raise self._error('Klipper is not ready')
        if self.sync_pending:
            raise self._error('native fan startup synchronization is pending')
        forced, fresh = self._cooling(self.reactor.monotonic())
        if not fresh:
            raise self._error('fresh MCU fan/guard status is required')
        if forced:
            raise self._error('MCU protective cooling/local thermostat owns outputs; no independent fan test')
        if self.board.get_mcu().is_fileoutput():
            raise self._error('FILEOUTPUT does not acknowledge physical fan operation')

    @staticmethod
    def _number(value, low, high):
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high

    def _peers_idle(self):
        now = self.reactor.monotonic()
        for name in PEERS:
            peer = self.printer.lookup_object(name, None)
            if peer is None:
                continue
            status = getattr(peer, 'get_ownership_status', peer.get_status)(now)
            # Physical SD uses lowercase states (idle/listing/importing),
            # unlike the job FSM. Preserve the strict busy/type checks and
            # compare their documented idle names without letter-case bias.
            state = status.get('state') if isinstance(status, dict) else None
            if (not isinstance(status, dict) or status.get('busy') is not False
                    or not isinstance(state, str)):
                raise self._error(name + ' owns resources')
            # A completed native homing attempt can retain a fault for the
            # operator even after releasing motion. The stationary fan test
            # still requires Ready, fresh MCU protection and a drained queue.
            historical_home_fault = (name == 'm300_motion' and state == 'FAULT'
                                     and status.get('normal_control') is True
                                     and status.get('ready') is True)
            if state.upper() not in IDLE and not historical_home_fault:
                raise self._error(name + ' owns resources')
        toolhead = self.printer.lookup_object('toolhead', None)
        if toolhead is not None:
            queued, current, empty = toolhead.check_busy(now)
            if not empty or queued > current:
                raise self._error('wait for the native motion queue to drain')

    def set_print(self, percent, from_command=False):
        if not self._number(percent, 0., 100.):
            raise self._error('PERCENT must be finite and within 0..100')
        self._control()
        if self.test is not None:
            raise self._error('cancel the current fan test first')
        now = self.reactor.monotonic()
        for name in ('m300_filament', 'm300_calibration', 'm300_maintenance', 'm300_motion'):
            peer = self.printer.lookup_object(name, None)
            if peer is not None and peer.get_status(now).get('busy') is not False:
                raise self._error(name + ' owns resources')
        (self._print_command if from_command else self._print_async)(percent / 100.)

    def start_test(self, channel, percent=100., seconds=5.):
        if getattr(self.board, 'native_control', False):
            raise self._error('commissioning fan tests are closed; use native M106/M107')
        if channel not in CHANNELS:
            raise self._error('CHANNEL must be PRINT or HOTEND')
        if not self._number(percent, 0., 100.) or not self._number(seconds, .5, 15.):
            raise self._error('use finite PERCENT 0..100 and SECONDS 0.5..15')
        if channel == 'HOTEND' and percent != 100.:
            raise self._error('hotend test supports 100% only; automatic cooling owns lower speeds')
        self._control()
        if self.test is not None:
            raise self._error('a fan test is already active')
        self._peers_idle()
        now = self.reactor.monotonic()
        self.token += 1
        self.phase += 1
        self.test = {'channel': channel, 'percent': percent, 'started': now,
                     'deadline': now + seconds,
                     'restore_speed': self.sources['PRINT'](now)['speed']}
        self.state, self.reason = 'TEST_' + channel, ''
        try:
            (self._print_async if channel == 'PRINT' else self._hotend_async)(percent / 100.)
        except Exception as exc:
            self._failed(exc)
            raise self._error(str(exc))
        self.reactor.update_timer(self.timer, self.reactor.NOW)
        return self.token

    def _finish(self, state, reason):
        test, self.test = self.test, None
        if test is None:
            return
        self.phase += 1
        self.state, self.reason = state, reason
        if state == 'FAULT':
            from .m300_error_codes import report
            report(self.printer, reason, source='m300_fans', fatal=self.printer.is_shutdown())
        try:
            forced, fresh = self._cooling(self.reactor.monotonic())
            if not fresh or forced:
                # Do not replay a cached OFF/old speed after a fault. The MCU
                # already owns protective cooling; there is no continuation.
                return
            if test['channel'] == 'PRINT':
                self._print_async(test['restore_speed'])
            else:
                # Restore the CURRENT native heater policy, not a saved OFF.
                self.hotend.last_speed = -1.
                self.hotend.callback(self.reactor.monotonic())
        except Exception as exc:
            self._failed(exc)
        finally:
            self.reactor.update_timer(self.timer, self.reactor.monotonic() + 2.)

    def _failed(self, exc):
        self.test = None
        self.phase += 1
        self.state, self.reason = 'FAULT', 'Fan output failure: ' + str(exc)
        from .m300_error_codes import report
        report(self.printer, self.reason, source='m300_fans', fatal=True)
        for write in (self._print_async, self._hotend_async):
            try:
                write(1.)
            except Exception:
                pass
        # The existing MCU shutdown path establishes final protective levels
        # even if a native output request itself cannot be queued.
        self.printer.invoke_async_shutdown('M300 fans: ' + self.reason)

    def cancel(self, token):
        if self.test is None or type(token) is not int or token != self.token:
            raise self._error('expired fan-test cancellation')
        self._finish('CANCELLED', 'Operator cancelled fan test')

    def invalidate(self, *args):
        self.token += 1
        self.phase += 1
        self.test = None
        self.sync_pending = False
        self.ready = False
        self.state, self.reason = 'IDLE', 'Lifecycle ended fan test; no saved continuation'
        self.reactor.update_timer(self.timer, self.reactor.NEVER)
        if self.bound:
            for write in (self._print_async, self._hotend_async):
                try:
                    write(1.)
                except Exception:
                    pass  # MCU shutdown/watchdog owns the final HIGH levels.

    def _tick(self, now):
        if not self.ready:
            return self.reactor.NEVER
        if self.sync_pending:
            self.sync_pending = False
            self.owners['PRINT'].last_fan_value = -1.
            self.owners['HOTEND'].last_fan_value = -1.
            self._print_async(0.)
        self._refresh_thermal(now)
        if self.test is None:
            return now + (2. if self.thermal_ok else .25)
        forced, fresh = self._cooling(now)
        if forced or not fresh:
            self._finish('FAULT', 'MCU protective cooling or stale guard status ended fan test')
            return now + 2.
        if now >= self.test['deadline']:
            self._finish('COMPLETE', 'Fan test completed; current native policy restored')
            return now + 2.
        return min(now + .25, self.test['deadline'])

    def get_status(self, now):
        snapshot = self._cooling_snapshot(now)
        forced, fresh, local = snapshot
        channels = {}
        for channel, (name, pin) in CHANNELS.items():
            raw = self.sources[channel](now) if channel in self.sources else {}
            requested = raw.get('speed')
            channels[channel.lower()] = {'object': name, 'pin': pin,
                'requested': requested,
                'effective_duty': self._effective(channel, now, requested, snapshot),
                'rpm': raw.get('rpm'), 'forced_cooling': forced,
                'speed_kind': 'electrical_duty_not_measured_airflow'}
        test = self.test or {}
        return {'installed': True, 'fan_revision': '0.13.14-FAN-R14-AUTOCOOL',
                'ready': self.ready and not self.sync_pending, 'state': self.state,
                'busy': self.test is not None or self.sync_pending, 'reason': self.reason,
                'session_token': self.token, 'phase_id': self.phase,
                'can_cancel': self.ready and self.test is not None,
                'can_confirm': False, 'can_purge': False,
                'channel': test.get('channel'), 'channels': channels,
                'phase_remaining': (max(0., test['deadline'] - now) if self.test else None),
                'forced_cooling': forced, 'mcu_status_fresh': fresh,
                'hotend_auto_threshold': getattr(self.hotend, 'heater_temp', None),
                'hotend_auto_speed': getattr(self.hotend, 'fan_speed', None),
                'hotend_temperature_fresh': self.thermal_ok,
                'marlin_reference_hotend_speed': 150. / 255.,
                'mcu_fan_policy': self.policy, 'mcu_upgrade_required': self.policy < 2,
                'local_cooling': local,
                'autonomous_thermostat_available': self.policy == 3,
                'hardware_qualified': False, 'automatic_arm': False,
                'tachometer_verified': False}

    def rows(self, now):
        status = self.get_status(now)
        rows = [('Back', ('page', 'maintenance')),
                ('Fan status: ' + status['state'], None)]
        for key in ('print', 'hotend'):
            channel = status['channels'][key]
            def percent(value):
                return 'unknown' if value is None else '%.0f%%' % (100. * value)
            rows.append((key.title() + ' ' + channel['pin'] + ': ' + percent(channel['effective_duty']), None))
            rows.append(('Requested: ' + percent(channel['requested']), None))
        if status['forced_cooling']:
            if self.policy == 3:
                rows.append(('MCU cooling: '+status['local_cooling'].get('mode', 'unknown'), None))
            else:
                rows.append(('MCU forced cooling: both 100%', None))
        elif not status['mcu_status_fresh']:
            rows.append(('MCU status stale: control unavailable', None))
        elif self.ready and not self.test and not getattr(self.board, 'native_control', False):
            rows += [('Print 100% / 5 s', ('fan_test', 'PRINT')),
                     ('Hotend 100% / 5 s', ('fan_test', 'HOTEND'))]
            rows.extend(('Print speed: %d%%' % value, ('fan_set', value))
                        for value in (0, 25, 50, 75, 100))
        if status['can_cancel']:
            rows.append(('Cancel current test', ('fan_cancel', self.token)))
        rows.append(('Hotend: native automatic cooling', None))
        if getattr(self.board, 'native_control', False):
            rows.extend(('Print speed: %d%%' % value, ('fan_set', value))
                        for value in (0, 25, 50, 75, 100))
        rows.append(('RPM: no verified tachometer input', None))
        if self.reason:
            rows.append((self.reason, None))
        return 'Fans', rows

    def cmd_status(self, gcmd):
        import json
        gcmd.respond_info('ZORTRAX_FANS ' + json.dumps(self.get_status(
            self.reactor.monotonic()), sort_keys=True))

    def cmd_set(self, gcmd):
        self.set_print(gcmd.get_float('PERCENT', minval=0., maxval=100.), True)

    def cmd_test(self, gcmd):
        self.start_test(gcmd.get('CHANNEL'), gcmd.get_float('PERCENT', 100.),
                        gcmd.get_float('SECONDS', 5.))

    def cmd_cancel(self, gcmd):
        self.cancel(gcmd.get_int('TOKEN', minval=0))


def load_config(config):
    board = config.get_printer().load_object(config, 'm300_mcu')
    if getattr(board, 'native_control', False):
        from .m300_native_fans import M300NativeFans
        return M300NativeFans(config)
    return M300Fans(config)
