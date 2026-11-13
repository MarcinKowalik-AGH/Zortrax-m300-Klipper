# SPDX-License-Identifier: GPL-3.0-or-later
"""Durable host intent for the M300 Classic factory print-minute counter."""

import hashlib
import json
import math

from .m300_nvm import _canonical, _read_regular, _sync_directory, _unique_pairs


STATE_FORMAT = ('m300_factory_counter_state serial=%u state=%c source=%c'
                ' print_minutes=%u settings_crc=%u')
COMMIT_FORMAT = ('m300_factory_counter_commit serial=%u source=%c expected=%u'
                 ' target=%u settings_crc=%u')
RESULT_FORMAT = 'm300_factory_counter_result status=%c'
RUNTIME_COMMIT_FORMAT = ('m300_factory_counter_commit_runtime serial=%u source=%c expected=%u'
                         ' target=%u settings_crc=%u deadline=%u')
RUNTIME_RESULT_FORMAT = 'm300_factory_counter_runtime_result deadline=%u status=%c'
RUNTIME_QUERY_FORMAT = 'm300_factory_counter_query_runtime token=%u'
RUNTIME_STATE_FORMAT = ('m300_factory_counter_runtime_state token=%u serial=%u state=%c'
                        ' source=%c print_minutes=%u settings_crc=%u')
MAX_UINT = 0xffffffff
JOURNAL_KEYS = {'serial', 'machine_id', 'committed', 'last_minutes', 'pending'}
PENDING_KEYS = {'source', 'expected', 'target', 'settings_crc'}


class CounterRecoveryError(ValueError):
    """The pending Flash update needs another safe window."""


def _uint(value, limit=MAX_UINT):
    return type(value) is int and 0 <= value <= limit


def _validate_journal(data):
    if (not isinstance(data, dict) or data.keys() != JOURNAL_KEYS
            or not isinstance(data['serial'], str)
            or not isinstance(data['machine_id'], str)
            or not _uint(data['committed'], MAX_UINT - 1)
            or not _uint(data['last_minutes'], MAX_UINT - 1)
            or data['committed'] > data['last_minutes']):
        raise ValueError('invalid factory counter journal')
    pending = data['pending']
    if pending is not None and (
            not isinstance(pending, dict) or pending.keys() != PENDING_KEYS
            or not _uint(pending['source'], 1)
            or not _uint(pending['expected'], MAX_UINT - 1)
            or not _uint(pending['target'], MAX_UINT - 1)
            or not _uint(pending['settings_crc'])
            or not data['last_minutes'] <= pending['expected'] < pending['target']):
        raise ValueError('invalid pending factory counter transaction')
    return data


class CounterJournal:
    def __init__(self, store):
        self.path = store.path + '.runtime-sync'
        self.atomic_replace = store._atomic_replace

    def load(self):
        try:
            raw = _read_regular(self.path, 4096)
        except FileNotFoundError:
            return None
        document = json.loads(raw, object_pairs_hook=_unique_pairs)
        if (not isinstance(document, dict) or document.keys() != {'data', 'sha256'}
                or hashlib.sha256(_canonical(document['data'])).hexdigest()
                != document['sha256']):
            raise ValueError('factory counter journal checksum mismatch')
        return _validate_journal(document['data'])

    def load_for_sync(self, was_pending):
        data = self.load()
        if data is not None and (was_pending or data['pending'] is not None):
            # An earlier rename may have succeeded before directory fsync failed.
            _sync_directory(self.path)
        return data

    def save(self, data):
        _validate_journal(data)
        checksum = hashlib.sha256(_canonical(data)).hexdigest()
        self.atomic_replace(self.path, _canonical(dict(data=data, sha256=checksum)))


def decode_state(result):
    serial, state, source, minutes, crc = (result[key] for key in
        ('serial', 'state', 'source', 'print_minutes', 'settings_crc'))
    if (not _uint(serial, MAX_UINT - 1) or not _uint(state, 2)
            or not _uint(source, 255) or not _uint(minutes, MAX_UINT - 1)
            or not _uint(crc)
            or state == 1 and (not serial or source > 1)
            or state != 1 and (source != 255 or minutes or crc)):
        raise ValueError('invalid factory counter state response')
    return serial, state, source, minutes, crc


class CounterSync:
    def __init__(self):
        self.status = 'DISABLED'
        self.error = None
        self.committed_seconds = 0
        self.pending = False
        self.flash_written = False
        self.serial = self.minutes = None
        self.banks = 'NOT_CHECKED'
        self.active_bank = None
        self.display_blocked = False

    def observe(self, result):
        packet = decode_state(result)
        serial, state, source, minutes, _ = packet
        self.serial = 'Z%08X' % serial if serial else None
        self.minutes = minutes if state == 1 else None
        self.banks = ('UNAVAILABLE', 'NORMALIZED', 'RECOVERY_REQUIRED')[state]
        self.active_bank = 'AB'[source] if state == 1 else None
        return packet

    def run(self, snapshot, load, save, query, commit, validate_backup=None, *,
            runtime=False):
        self.status = 'CHECKING'
        self.error = None
        serial, state, source, minutes, crc = self.observe(query())
        try:
            data = load()
        except (OSError, ValueError) as exc:
            if state == 2:
                raise CounterRecoveryError(str(exc)) from exc
            raise
        if data is None:
            if state == 2:
                raise CounterRecoveryError('interrupted MCU factory banks require the original host journal')
            if validate_backup is None:
                self.status = 'DISABLED'
                return
        if not serial:
            error = CounterRecoveryError if state == 2 else ValueError
            raise error('MCU factory serial is unavailable')
        machine = snapshot['identity']['machine_id']
        total = snapshot['counters']['print_seconds']
        if (type(total) not in (int, float) or not math.isfinite(total)
                or total < 0):
            raise ValueError('invalid host model-print counter')

        fresh = data is None
        if fresh:
            data = dict(serial=self.serial, machine_id=machine, committed=0,
                        last_minutes=minutes, pending=None)
        elif data['serial'] != self.serial or data['machine_id'] != machine:
            error = CounterRecoveryError if state == 2 else ValueError
            raise error('factory counter journal belongs to another printer')
        self.committed_seconds = 60 * data['committed']
        pending = data['pending']
        self.pending = pending is not None
        if self.pending:
            before = (pending['source'], pending['expected'], pending['settings_crc'])
            after = (1 - pending['source'], pending['target'], pending['settings_crc'])
            self.display_blocked = state != 1 or (source, minutes, crc) != before
        elif state == 1:
            self.display_blocked = minutes < data['last_minutes'] or total < self.committed_seconds
            if self.display_blocked:
                raise ValueError('factory or host counter went backwards')
        if state == 2 and not self.pending:
            raise CounterRecoveryError('interrupted MCU factory banks have no matching host transaction')
        if validate_backup is None:
            if state != 1 and self.pending:
                raise CounterRecoveryError('configured Flash backup required to recover the pending update')
            self.status = 'BACKUP_REQUIRED'
            return
        if state != 1:
            try:
                validate_backup(self.serial)
            except (ValueError, OSError) as exc:
                raise CounterRecoveryError(str(exc)) from exc
        else:
            validate_backup(self.serial)
        if state != 1 and not self.pending:
            raise CounterRecoveryError('MCU factory banks need inspection before synchronization')

        if pending is None:
            whole_minutes = int(total // 60) - data['committed']
            if not whole_minutes:
                if fresh or minutes != data['last_minutes']:
                    save(dict(data, last_minutes=minutes))
                self.status = 'CURRENT'
                return
            target = minutes + whole_minutes
            if not _uint(target, MAX_UINT - 1):
                raise ValueError('factory counter target exceeds its uint32 range')
            pending = dict(source=source, expected=minutes, target=target,
                           settings_crc=crc)
            data = dict(data, last_minutes=minutes, pending=pending)
            # No command is sent until the exact absolute intent is durable.
            save(data)
            self.pending = True
        elif state == 1 and (source, minutes, crc) not in (before, after):
            raise ValueError('factory counter changed during a pending transaction')
        elif state == 0:
            raise CounterRecoveryError('pending transaction has no recoverable MCU bank')

        try:
            observed_banks = self.banks, self.active_bank
            previous_display_blocked = self.display_blocked
            self.banks, self.active_bank = 'RECOVERY_REQUIRED', None
            self.display_blocked = True
            result = commit([serial, pending['source'], pending['expected'],
                             pending['target'], pending['settings_crc']])
            status = result['status']
            if type(status) is int and status == 2:
                if runtime:
                    observed = self.observe(query())
                    before = (serial, 1, pending['source'], pending['expected'],
                              pending['settings_crc'])
                    self.display_blocked = observed != before
                    if observed[0] != serial or observed[1] == 0:
                        raise ValueError('MCU bank read-back unavailable after deferral')
                    self.status = 'AWAITING_IDLE' if observed == before else 'RECOVERY_REQUIRED'
                    return
                if state == 1:
                    self.banks, self.active_bank = observed_banks
                    self.display_blocked = previous_display_blocked
                    self.status = 'AWAITING_FIRMWARE_RESTART'
                    return
            if type(status) is not int or status not in (0, 1):
                raise ValueError('MCU refused factory counter transaction (status %r)' % status)
            self.flash_written = status == 0
            expected = (serial, 1, 1 - pending['source'], pending['target'],
                        pending['settings_crc'])
            if self.observe(query()) != expected:
                raise ValueError('MCU factory counter read-back did not match the pending transaction')
        except Exception as exc:
            raise CounterRecoveryError(str(exc)) from exc

        data = dict(data, pending=None, last_minutes=pending['target'],
                    committed=data['committed'] + pending['target'] - pending['expected'])
        try:
            save(data)
        except (OSError, ValueError) as exc:
            raise CounterRecoveryError(str(exc)) from exc
        self.committed_seconds = 60 * data['committed']
        self.minutes = pending['target']
        self.pending = False
        self.display_blocked = False
        self.status = 'SYNCED'
