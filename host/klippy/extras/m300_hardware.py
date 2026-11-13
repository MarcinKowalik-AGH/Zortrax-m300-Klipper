# SPDX-License-Identifier: GPL-3.0-or-later
"""Identify the stock M300 and optionally synchronize its print-minute counter.

Factory Flash updates are opt-in and performed only before MCU configuration.
FILEOUTPUT deliberately does not invent a factory identity or update Flash.
"""
import json
import logging
import math
import os

from .m300_counter_sync import (COMMIT_FORMAT, RESULT_FORMAT, STATE_FORMAT,
                                CounterJournal, CounterRecoveryError, CounterSync)

REVISION = '0.13.15.7-FACTORY-Z'
FACTORY_ADDRESS = 0x0803f848
FACTORY_HEADER = 0xaabb0103
FACTORY_FORMAT = ('m300_factory_state header=%u raw=%c valid=%c'
                  ' revision=%c z_steps=%hu')
FACTORY_INFO_FORMAT = 'm300_factory_info serial=%u time_valid=%c print_minutes=%u'


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


class M300Hardware:
    def __init__(self, board, config):
        self.board, self.config = board, config
        self.printer, self.mcu = board.printer, board.mcu
        self.profile = config.getchoice('z_profile', ['factory', 'config'], 'factory')
        self.counter_backup = config.get('factory_counter_backup', '').strip()
        self.counter_sync = CounterSync()
        self.counter_legacy_state = None
        self.counter_legacy_error = None
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
        if self._factory_info_query is not None:
            try:
                self._factory_info_query.send()
            except Exception as exc:
                self.factory_info_error = str(exc)

    def _sync_factory_counter(self, constants):
        nvm = self.printer.lookup_object('m300_nvm', None)
        supported = (constants.get('M300_MODEL') == 'M300_CLASSIC'
                     and constants.get('M300_FACTORY_COUNTER_ABI') == 1
                     and self.mcu.check_valid_response(STATE_FORMAT)
                     and self.mcu.check_valid_response(RESULT_FORMAT))
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
        validator = None
        if self.counter_backup:
            from .m300_counter_backup import validate_backup
            path = os.path.expanduser(self.counter_backup)

            def validator(serial):
                if not os.path.isabs(path):
                    raise ValueError('factory_counter_backup must be an absolute path')
                return nvm.executor.submit(validate_backup, path, serial)
        try:
            query = self.mcu.lookup_query_command('m300_factory_counter_query', STATE_FORMAT)
            commit = self.mcu.lookup_query_command(COMMIT_FORMAT, RESULT_FORMAT)
            bounded = self.board.startup_transport._bounded
            self.counter_sync.run(
                nvm.ui_snapshot(), lambda: nvm.executor.submit(journal.load),
                lambda data: nvm.executor.submit(journal.save, data),
                lambda: bounded('m300_factory_counter_query', query.send),
                lambda args: bounded('m300_factory_counter_commit',
                                     lambda: commit.send(args)), validator)
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
        if self.counter_sync.serial is not None:
            self.serial_number = self.counter_sync.serial
            if not self.counter_sync.display_blocked:
                self.factory_print_minutes = self.counter_sync.minutes

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
