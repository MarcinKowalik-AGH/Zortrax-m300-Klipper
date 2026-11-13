# SPDX-License-Identifier: GPL-3.0-or-later
"""Identify the stock M300 and optionally synchronize its print-minute counter.

Factory Flash updates are opt-in. A runtime-capable MCU accepts them while idle.
FILEOUTPUT deliberately does not invent a factory identity or update Flash.
"""
import json
import logging
import math
import os
from secrets import randbits

from .m300_counter_sync import (COMMIT_FORMAT, RESULT_FORMAT, STATE_FORMAT,
                                RUNTIME_COMMIT_FORMAT, RUNTIME_RESULT_FORMAT,
                                RUNTIME_QUERY_FORMAT, RUNTIME_STATE_FORMAT,
                                CounterJournal, CounterRecoveryError, CounterSync)
from .m300_maintenance import other_service

REVISION = '0.13.15.7-FACTORY-Z'
FACTORY_ADDRESS = 0x0803f848
FACTORY_HEADER = 0xaabb0103
FACTORY_FORMAT = ('m300_factory_state header=%u raw=%c valid=%c'
                  ' revision=%c z_steps=%hu')
FACTORY_INFO_FORMAT = 'm300_factory_info serial=%u time_valid=%c print_minutes=%u'
COUNTER_WINDOW = .350
COUNTER_TIMEOUT = .550
COUNTER_RETRY = .730
COUNTER_ERROR_RETRY = 3.170
COUNTER_OWNERS = ('m300_print_control', 'm300_job', 'm300_models', 'm300_filament',
                  'm300_calibration', 'm300_maintenance', 'm300_sd', 'm300_motion',
                  'm300_fans', 'm300_thermal', 'm300_pad_mesh', 'm300_nvm')


def decode_factory(header, raw):
    if type(header) is not int or not 0 <= header <= 0xffffffff:
        raise ValueError('factory header is not a uint32')
    if type(raw) is not int or not 0 <= raw <= 255:
        raise ValueError('factory revision byte is not a uint8')
    if header != FACTORY_HEADER or not 0xe0 <= raw < 0xff:
        return {'valid': False, 'revision': None, 'z_steps_per_mm': None}
    revision = raw - 0xe0
    return {'valid': True, 'revision': revision,
            'z_steps_per_mm': 800 if revision < 5 else 400}


class RuntimeCounterTransport:
    """Timed responses without modifying native serial acknowledgement state."""
    def __init__(self, mcu, reactor):
        self.mcu, self.reactor = mcu, reactor
        self.pending = None
        self.token = randbits(32)
        self.query_command = mcu.lookup_command(RUNTIME_QUERY_FORMAT)
        self.commit_command = mcu.lookup_command(RUNTIME_COMMIT_FORMAT)
        self.subscriptions = (
            mcu.register_serial_response(self._receive_state, RUNTIME_STATE_FORMAT),
            mcu.register_serial_response(self._receive_result, RUNTIME_RESULT_FORMAT),
        )

    def _receive_state(self, packet):
        self._receive('state', packet.get('token'), packet)

    def _receive_result(self, packet):
        self._receive('result', packet.get('deadline'), packet)

    def _receive(self, kind, token, packet):
        pending = self.pending
        if pending is None:
            return
        expected, expected_token, started, completion = pending
        if (kind == expected and token == expected_token
                and packet['#receive_time'] >= started):
            self.reactor.async_complete(completion, packet)

    def _request(self, command, args, kind, token, now):
        completion = self.reactor.completion()
        self.pending = kind, token, now, completion
        try:
            command.send(args)
            packet = completion.wait(now + COUNTER_TIMEOUT)
            if packet is None:
                raise TimeoutError('MCU factory counter %s response timed out' % kind)
            return packet
        finally:
            self.pending = None

    def query(self):
        now = self.reactor.monotonic()
        self.token = (self.token + 1) & 0xffffffff
        return self._request(self.query_command, (self.token,), 'state', self.token, now)

    def commit(self, args):
        now = self.reactor.monotonic()
        print_time = self.mcu.estimated_print_time(now) + COUNTER_WINDOW
        deadline = self.mcu.print_time_to_clock(print_time) & 0xffffffff
        return self._request(self.commit_command, [*args, deadline], 'result', deadline, now)


class M300Hardware:
    def __init__(self, board, config):
        self.board, self.config = board, config
        self.printer, self.mcu = board.printer, board.mcu
        self.profile = config.getchoice('z_profile', ['factory', 'config'], 'factory')
        self.counter_backup = config.get('factory_counter_backup', '').strip()
        self.counter_sync = CounterSync()
        self.counter_legacy_state = None
        self.counter_legacy_error = None
        self.counter_runtime_supported = False
        self.counter_runtime = self.counter_timer = None
        self.state, self.error = 'NOT_READ', None
        self.factory = {'valid': False, 'revision': None, 'z_steps_per_mm': None}
        self.header = self.raw = None
        self.serial_number = self.factory_print_minutes = None
        self.factory_info_error = None
        self._factory_info_query = None
        self.configured_rotation = self.effective_rotation = None
        self.effective_steps = None
        self.applied = False
        self.printer.register_event_handler('klippy:mcu_identify', self._identify)
        self.printer.register_event_handler('klippy:ready', self._request_factory_info)
        if self.counter_backup:
            self.printer.register_event_handler('m300:runtime_checkpoint', self._queue_counter)
            self.printer.register_event_handler('klippy:shutdown', self._stop_counter)
            self.printer.register_event_handler('klippy:disconnect', self._stop_counter)
            self.printer.register_event_handler('gcode:request_restart', self._stop_counter)
        board.gcode.register_command('ZORTRAX_HARDWARE_STATUS', self.cmd_status,
                                     when_not_ready=True)

    def _z_stepper(self):
        kin = self.printer.lookup_object('toolhead').get_kinematics()
        z = [s for s in kin.get_steppers() if s.get_name() == 'stepper_z']
        if len(z) != 1 or z[0].get_mcu() is not self.mcu:
            raise self.config.error('M300 factory Z requires one local stepper_z')
        return z[0]

    def _snapshot_stepper(self):
        stepper = self._z_stepper()
        rotation, steps = stepper.get_rotation_distance()
        if not all(math.isfinite(v) and v > 0 for v in (rotation, steps)):
            raise self.config.error('M300 Z rotation distance must be finite and positive')
        self.configured_rotation = self.effective_rotation = rotation
        self.effective_steps = steps / rotation
        return stepper

    def _query_factory(self):
        query = self.mcu.lookup_query_command('m300_factory_query', FACTORY_FORMAT)
        return self.board.startup_transport._bounded('m300_factory_query', query.send)

    def _configure_factory_info(self, constants):
        if (constants.get('M300_MODEL') != 'M300_CLASSIC'
                or constants.get('M300_FACTORY_INFO_ABI') != 1
                or not self.mcu.check_valid_response(FACTORY_INFO_FORMAT)):
            return
        try:
            query = self.mcu.lookup_command('m300_factory_info_query')
            self.mcu.register_serial_response(self._receive_factory_info,
                                              FACTORY_INFO_FORMAT)
            self._factory_info_query = query
        except Exception as exc:
            self.factory_info_error = str(exc)

    def _request_factory_info(self):
        if (self.counter_backup and self.counter_runtime_supported
                and self.printer.lookup_object('m300_nvm', None) is not None):
            try:
                reactor = self.printer.get_reactor()
                self.counter_runtime = RuntimeCounterTransport(self.mcu, reactor)
                self.counter_timer = reactor.register_timer(self._runtime_counter_tick)
                self._queue_counter()
            except Exception as exc:
                self.counter_sync.status = 'REFUSED'
                self.counter_sync.error = str(exc)
                logging.warning('M300 runtime factory counter setup failed: %s', exc)
            # The startup counter query already provided the serial and ID0.
            # An additional asynchronous response could overwrite later read-back.
            return
        if self._factory_info_query is not None:
            try:
                self._factory_info_query.send()
            except Exception as exc:
                self.factory_info_error = str(exc)

    def _queue_counter(self):
        if self.counter_timer is not None and not self.printer.is_shutdown():
            reactor = self.printer.get_reactor()
            reactor.update_timer(self.counter_timer, reactor.NOW)

    def _stop_counter(self, *args):
        self.counter_runtime = None
        if self.counter_timer is not None:
            reactor = self.printer.get_reactor()
            reactor.unregister_timer(self.counter_timer)
            self.counter_timer = None

    def _counter_validator(self, nvm):
        if not self.counter_backup:
            return None
        from .m300_counter_backup import validate_backup
        path = os.path.expanduser(self.counter_backup)

        def validator(serial):
            if not os.path.isabs(path):
                raise ValueError('factory_counter_backup must be an absolute path')
            return nvm.executor.submit(validate_backup, path, serial)

        return validator

    def _counter_has_backlog(self, snapshot):
        return (self.counter_sync.pending or
                snapshot['counters']['print_seconds'] - self.counter_sync.committed_seconds >= 60)

    def _counter_idle(self, nvm, now):
        if (self.printer.is_shutdown() or not self.board.ready
                or not nvm.runtime_is_checkpointed(now)):
            return False
        printer = self.printer
        sd = printer.lookup_object('virtual_sdcard', None)
        stats = printer.lookup_object('print_stats', None)
        pause = printer.lookup_object('pause_resume', None)
        control = printer.lookup_object('m300_print_control', None)
        if ((sd is not None and sd.is_active()) or
                (stats is not None and stats.get_status(now)['state'] in ('printing', 'paused'))
                or (pause is not None and pause.is_paused)
                or (control is not None and control.context is not None)
                or other_service(printer, COUNTER_OWNERS, now)):
            return False
        queued, estimated, empty = printer.lookup_object('toolhead').check_busy(now)
        if not empty or not all(math.isfinite(value) for value in (queued, estimated)) or queued > estimated:
            return False
        heaters = printer.lookup_object('heaters')
        current_clock = self.mcu.print_time_to_clock(self.mcu.estimated_print_time(now))
        for name in ('extruder', 'heater_bed'):
            heater = heaters.lookup_heater(name)
            status = heater.get_status(now)
            pwm = heater.mcu_pwm
            native_pwm = getattr(pwm, 'native', pwm)
            if (status['target'] != 0. or status['power'] != 0.
                    or pwm.get_mcu() is not self.mcu or native_pwm._last_clock > current_clock):
                return False
        return True

    def _runtime_counter_tick(self, eventtime):
        reactor = self.printer.get_reactor()
        transport = self.counter_runtime
        if transport is None or self.printer.is_shutdown():
            return reactor.NEVER
        nvm = self.printer.lookup_object('m300_nvm', None)
        if nvm is None:
            return reactor.NEVER
        snapshot = nvm.ui_snapshot()
        if not self._counter_has_backlog(snapshot):
            return reactor.NEVER
        mutex = self.board.gcode.get_mutex()
        journal = CounterJournal(nvm.store)

        def query():
            if self.counter_runtime is not transport or self.printer.is_shutdown():
                raise OSError('M300 factory counter synchronization stopped')
            return transport.query()

        def commit(args):
            # Disk I/O and read-only queries occur outside the G-code lock.
            # Recheck the complete idle window after durable intent is written.
            if mutex.test():
                return {'status': 2}
            with mutex:
                now = reactor.monotonic()
                if self.counter_runtime is not transport or not self._counter_idle(nvm, now):
                    return {'status': 2}
                return transport.commit(args)

        delay = COUNTER_RETRY
        previous_error = self.counter_sync.error
        try:
            if mutex.test() or not self._counter_idle(nvm, eventtime):
                if self.counter_sync.status != 'RECOVERY_REQUIRED':
                    self.counter_sync.status = 'AWAITING_IDLE'
                return reactor.monotonic() + delay
            self.counter_sync.run(
                snapshot, lambda: nvm.executor.submit(journal.load),
                lambda data: nvm.executor.submit(journal.save, data), query,
                commit, self._counter_validator(nvm), runtime=True)
            if self.counter_sync.status == 'RECOVERY_REQUIRED':
                self.counter_sync.error = 'MCU factory counter transfer is pending read-back or recovery'
        except (CounterRecoveryError, OSError, ValueError) as exc:
            self.counter_sync.status = ('RECOVERY_REQUIRED' if self.counter_sync.pending
                                        else 'REFUSED')
            if previous_error != str(exc):
                logging.warning('M300 runtime factory counter pending: %s', exc)
            self.counter_sync.error = str(exc)
            delay = COUNTER_ERROR_RETRY
        except Exception:
            self.counter_sync.status = 'REFUSED'
            self.counter_sync.error = 'unexpected runtime synchronization error'
            logging.exception('M300 runtime factory counter failed')
            delay = COUNTER_ERROR_RETRY
        self._publish_counter_observation()
        if self.counter_runtime is not transport or self.printer.is_shutdown():
            return reactor.NEVER
        if not self._counter_has_backlog(nvm.ui_snapshot()):
            return reactor.NEVER
        return reactor.monotonic() + delay

    def _publish_counter_observation(self):
        if self.counter_sync.serial is not None:
            self.serial_number = self.counter_sync.serial
            self.factory_print_minutes = (None if self.counter_sync.display_blocked
                                          else self.counter_sync.minutes)

    def _sync_factory_counter(self, constants):
        nvm = self.printer.lookup_object('m300_nvm', None)
        supported = (constants.get('M300_MODEL') == 'M300_CLASSIC'
                     and constants.get('M300_FACTORY_COUNTER_ABI') == 1
                     and self.mcu.check_valid_response(STATE_FORMAT)
                     and self.mcu.check_valid_response(RESULT_FORMAT))
        self.counter_runtime_supported = (
            supported and constants.get('M300_FACTORY_COUNTER_RUNTIME_ABI') == 1
            and self.mcu.check_valid_response(RUNTIME_RESULT_FORMAT)
            and self.mcu.check_valid_response(RUNTIME_STATE_FORMAT))
        if nvm is None:
            if self.counter_backup:
                self.counter_sync.status = 'HOST_NVM_UNAVAILABLE'
            if supported:
                query = self.mcu.lookup_query_command('m300_factory_counter_query',
                                                      STATE_FORMAT)
                bounded = self.board.startup_transport._bounded
                _, state, *_ = self.counter_sync.observe(
                    bounded('m300_factory_counter_query', query.send))
                if state == 2:
                    self.counter_sync.status = 'RECOVERY_REQUIRED'
                    self.counter_sync.error = (
                        'M300 factory counter recovery requires the original host NVM journal')
                    raise self.config.error(self.counter_sync.error)
            return
        journal = CounterJournal(nvm.store)
        if not supported:
            self.counter_sync.banks = 'UNAVAILABLE'
            try:
                data = nvm.executor.submit(journal.load)
                if data is not None:
                    if data['machine_id'] != nvm.ui_snapshot()['identity']['machine_id']:
                        raise ValueError('factory counter journal belongs to another printer')
                    self.counter_legacy_state = data
                    self.counter_sync.pending = data['pending'] is not None
            except (OSError, ValueError) as exc:
                self.counter_legacy_error = str(exc)
                self.counter_sync.error = str(exc)
            if self.counter_backup or self.counter_legacy_state or self.counter_legacy_error:
                self.counter_sync.status = 'MCU_ABI_UNAVAILABLE'
            return
        try:
            query = self.mcu.lookup_query_command('m300_factory_counter_query', STATE_FORMAT)
            commit = self.mcu.lookup_query_command(COMMIT_FORMAT, RESULT_FORMAT)
            bounded = self.board.startup_transport._bounded
            self.counter_sync.run(
                nvm.ui_snapshot(), lambda: nvm.executor.submit(journal.load),
                lambda data: nvm.executor.submit(journal.save, data),
                lambda: bounded('m300_factory_counter_query', query.send),
                lambda args: bounded('m300_factory_counter_commit',
                                     lambda: commit.send(args)), self._counter_validator(nvm))
        except CounterRecoveryError as exc:
            self.counter_sync.status = 'RECOVERY_REQUIRED'
            self.counter_sync.error = str(exc)
            raise self.config.error('M300 factory counter recovery: ' + str(exc)) from None
        except Exception as exc:
            self.counter_sync.status = 'REFUSED'
            self.counter_sync.error = str(exc)
            if self.counter_sync.banks == 'RECOVERY_REQUIRED':
                raise self.config.error('M300 factory counter recovery: ' + str(exc)) from None
            logging.warning('M300 factory counter synchronization refused: %s', exc)
        self._publish_counter_observation()

    def _receive_factory_info(self, result):
        self.printer.get_reactor().register_async_callback(
            lambda eventtime: self._apply_factory_info(result))

    def _apply_factory_info(self, result):
        try:
            serial, valid, minutes = (result[key] for key in
                                      ('serial', 'time_valid', 'print_minutes'))
            if (type(serial) is not int or not 0 <= serial < 0xffffffff
                    or type(valid) is not int or valid not in (0, 1)
                    or type(minutes) is not int or not 0 <= minutes < 0xffffffff
                    or not valid and minutes):
                raise ValueError('invalid factory information response')
            self.serial_number = 'Z%08X' % serial if serial else None
            self.factory_print_minutes = minutes if valid else None
            data = self.counter_legacy_state
            if (self.counter_legacy_error or self.counter_sync.status == 'REFUSED'
                    or self.counter_sync.display_blocked):
                self.factory_print_minutes = None
            elif data and data['serial'] == self.serial_number:
                pending = data['pending']
                if (not valid or minutes < data['last_minutes']
                        or pending is not None and minutes != pending['expected']):
                    self.factory_print_minutes = None
                    self.counter_sync.error = 'Factory counter needs the matching MCU ABI to reconcile its journal'
                else:
                    self.counter_sync.committed_seconds = 60 * data['committed']
            self.factory_info_error = None
        except Exception as exc:
            self.factory_info_error = str(exc)
            logging.warning('M300 factory information unavailable: %s', exc)

    def _identify(self):
        self.serial_number = self.factory_print_minutes = None
        self.factory_info_error = None
        self._factory_info_query = None
        self._snapshot_stepper()
        if self.mcu.is_fileoutput():
            self.state = 'FILEOUTPUT_NO_FACTORY_READ'
            return
        constants = self.mcu.get_constants()
        supported = (int(constants.get('M300_FACTORY_ABI', 0)) == 1
                     and int(constants.get('M300_FACTORY_HW_ADDRESS', 0)) == FACTORY_ADDRESS
                     and constants.get('M300_MODEL') == 'M300_CLASSIC'
                     and self.mcu.check_valid_response(FACTORY_FORMAT))
        if not supported:
            self.state = 'MCU_FACTORY_ABI_UNAVAILABLE'
            if self.profile == 'factory':
                self.error = ('M300 factory Z needs MCU R14.5 or newer with factory ABI 1; '
                              'install the matching MCU application. z_profile=config '
                              'explicitly keeps an operator-selected Z configuration')
                raise self.config.error(self.error)
            self._configure_factory_info(constants)
            self._sync_factory_counter(constants)
            return
        try:
            self._apply_identity(self._query_factory())
        except Exception as exc:
            self.state, self.error = 'ERROR', str(exc)
            raise self.config.error('M300 hardware identity: ' + self.error) from None
        self._configure_factory_info(constants)
        self._sync_factory_counter(constants)
        logging.info('M300_HARDWARE %s', json.dumps(self.get_status(), sort_keys=True))

    def _apply_identity(self, response):
        """Shared with software tests; caller must be in MCU identification."""
        self.header, self.raw = response['header'], response['raw']
        identity = decode_factory(self.header, self.raw)
        expected = (int(identity['valid']), identity['revision'] or 0,
                    identity['z_steps_per_mm'] or 0)
        if tuple(response[k] for k in ('valid', 'revision', 'z_steps')) != expected:
            raise ValueError('factory telemetry disagrees with the raw ID3 record')
        self.factory = identity
        if self.profile == 'config':
            self.state = 'CONFIG_OVERRIDE'
            return
        if not identity['valid']:
            raise ValueError('missing/corrupt factory ID3; read a full backup or explicitly '
                             'select z_profile=config with a verified Z scale')
        # The board sets Z MS pins to LLH. Do not compensate for an incorrect
        # software microstep/gear setting by silently changing the lead value.
        zconfig = self.config.getsection('stepper_z')
        if (zconfig.getint('microsteps') != 16
                or zconfig.getint('full_steps_per_rotation', 200) != 200
                or zconfig.get('gear_ratio', '').strip()
                or zconfig.get('step_pin').strip() not in ('PB7', self.board.mcu_name + ':PB7')):
            raise ValueError('factory Z requires PB7, 16 microsteps, 200 full steps and no gear_ratio')
        stepper = self._z_stepper()
        if self.mcu._config_helper.is_config_finalized():
            raise ValueError('factory Z may only be selected before MCU configuration')
        if self.printer.lookup_object('toolhead').get_status(
                self.printer.get_reactor().monotonic()).get('homed_axes'):
            raise ValueError('factory Z may not change a homed coordinate frame')
        _, steps = stepper.get_rotation_distance()
        if steps != 3200:
            raise ValueError('factory Z native steps_per_rotation must be 3200')
        rotation = steps / identity['z_steps_per_mm']
        stepper.set_rotation_distance(rotation)
        self.effective_rotation = rotation
        self.effective_steps = identity['z_steps_per_mm']
        self.applied, self.state = True, 'FACTORY_PROFILE_APPLIED'

    def selected_z_steps(self):
        return self.factory['z_steps_per_mm'] if self.applied else None

    def get_status(self):
        return {'revision': REVISION, 'state': self.state, 'error': self.error,
                'z_profile': self.profile, 'factory_valid': self.factory['valid'],
                'factory_header_address': '0x0803F848',
                'factory_header': self.header, 'factory_raw': self.raw,
                'hardware_revision': self.factory['revision'],
                'hardware_label': ('HW%02d' % self.factory['revision']
                                   if self.factory['valid'] else None),
                'serial_number': self.serial_number,
                'factory_print_minutes': self.factory_print_minutes,
                'factory_info_error': self.factory_info_error,
                'factory_counter_sync': self.counter_sync.status,
                'factory_counter_runtime_supported': self.counter_runtime_supported,
                'factory_counter_error': self.counter_sync.error,
                'factory_counter_pending': self.counter_sync.pending,
                'factory_counter_banks': self.counter_sync.banks,
                'factory_counter_active_bank': self.counter_sync.active_bank,
                'factory_counter_committed_seconds': self.counter_sync.committed_seconds,
                'stock_z_steps_per_mm': self.factory['z_steps_per_mm'],
                'configured_rotation_distance': self.configured_rotation,
                'effective_rotation_distance': self.effective_rotation,
                'effective_z_steps_per_mm': self.effective_steps,
                'factory_profile_applied': self.applied,
                'factory_flash_written': self.counter_sync.flash_written,
                'physical_scale_measured': False}

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_HARDWARE ' + json.dumps(self.get_status(), sort_keys=True))
