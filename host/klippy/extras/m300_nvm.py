# SPDX-License-Identifier: GPL-3.0-or-later
"""M04 durable host settings. Never writes MCU Flash or restores live state.

Readers copy the last published snapshot and do not wait for fsync. Writers
serialize using a lock, fsync a private temporary file, replace, then fsync the
directory. SHA256 detects corruption, it is not authentication. Real power loss
and the storage device remain separate qualification work.
"""
import copy
import hashlib
import json
import logging
import math
import os
import stat
import struct
import tempfile
import threading
from datetime import datetime, timezone

from .m300_runtime import CHECKPOINT_SECONDS, DRAIN_POLL_SECONDS, PrintClock

SCHEMA_VERSION = 1
MAX_BYTES = 65536
MODEL = 'M300_CLASSIC'
DEFAULT_SETTINGS = dict(language='EN', light_mode='DYNAMIC', sound=True,
                        sleep_mode='15MIN', sleep_light=False,
                        sort_mode='NAME', full_platform_preheat=False)
MAX_BRIGHTNESS = 16
BRIGHTNESS_LEVELS = tuple(range(1, MAX_BRIGHTNESS + 1))
BRIGHTNESS_KEYS = frozenset(('oled_brightness', 'led_brightness'))
COSMETIC_SETTINGS = BRIGHTNESS_KEYS | {'light_mode', 'sound'}
CHOICES = dict(language=('EN', 'PL', 'FR', 'DE', 'ES'),
               light_mode=('DYNAMIC', 'WHITE', 'DISABLE'),
               sound=(False, True), sleep_mode=('OFF', '15MIN', '30MIN', '60MIN'),
               sleep_light=(False, True),
               sort_mode=('NAME', 'NAME_CASE', 'DATE', 'SIZE'),
               full_platform_preheat=(False, True))
CHOICES.update(dict.fromkeys(BRIGHTNESS_KEYS, BRIGHTNESS_LEVELS))
SLEEP_SECONDS = {'OFF': 0, '15MIN': 900, '30MIN': 1800, '60MIN': 3600}
LABELS = {'DYNAMIC': 'Dynamic light', 'WHITE': 'White light',
          'DISABLE': 'Light disabled', 'OFF': 'Disabled', '15MIN': '15 minutes',
          '30MIN': '30 minutes', '60MIN': '60 minutes', 'NAME': 'Name',
          'NAME_CASE': 'Name (case sensitive)', 'DATE': 'Date', 'SIZE': 'Size'}
LIVE_KEYS = {'armed', 'arm', 'homed_axes', 'position', 'live_pose', 'resume',
             'resume_cursor', 'heater_targets', 'allow_actuators', 'allow_motion',
             'allow_heating', 'workflow_qualified', 'z_offset', 'bed_mesh',
             'rotation_distance', 'position_endstop'}


class NVMError(ValueError):
    pass


def _finite(value, name, lo=None, hi=None):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (lo is not None and value < lo)
            or (hi is not None and value > hi)):
        raise NVMError('invalid ' + name)
    return value


def _identity(machine_id, mechanics_id):
    result = {'machine_id': machine_id, 'mechanics_id': mechanics_id}
    for key, value in result.items():
        if (not isinstance(value, str) or not 1 <= len(value) <= 128
                or any(ord(c) < 32 for c in value)):
            raise NVMError('invalid ' + key)
    return result


def validate_setting(name, value):
    if name not in CHOICES:
        raise NVMError('unknown setting: ' + str(name))
    allowed = CHOICES[name]
    if (type(value) is not type(allowed[0])) or value not in allowed:
        raise NVMError('invalid setting %s; choices=%r' % (name, allowed))
    return value


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise NVMError('non-serializable data: ' + str(exc))


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise NVMError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def _check_no_live(value, depth=0):
    if depth > 12:
        raise NVMError('excessive nested data')
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise NVMError('non-string JSON key')
            if key.lower() in LIVE_KEYS:
                raise NVMError('live control state cannot be persisted: ' + key)
            _check_no_live(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_no_live(item, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise NVMError('non-finite data')


def validate_calibration(record):
    if record is None:
        return
    if not isinstance(record, dict):
        raise NVMError('calibration must be an observation object')
    _check_no_live(record)
    required = {'valid', 'method', 'units', 'identity', 'session_token',
                'reference_mm', 'initial_points', 'final_points',
                'deltas_mm', 'corrections', 'samples_history', 'geometry'}
    if not required <= set(record):
        raise NVMError('incomplete calibration observation')
    if (record['valid'] is not True or record['units'] != 'mm'
            or record['method'] not in ('CONTACT_MEDIAN_FIVE_POINTS', 'M300_STOCK_FIVE_POINT_V1')):
        raise NVMError('unsupported calibration method/units/result')
    _identity(**record['identity'])
    if not isinstance(record['session_token'], str) or not record['session_token']:
        raise NVMError('calibration lacks session identity')
    _finite(record['reference_mm'], 'reference', -1000, 1000)
    if (len(record['initial_points']) != 4 or len(record['final_points']) != 5
            or len(record['deltas_mm']) != 5
            or len(record['corrections']) > 40 or len(record['samples_history']) > 100):
        raise NVMError('calibration point/history count invalid')
    for value in record['deltas_mm']:
        _finite(value, 'delta', -1000, 1000)
    for name, ids in (('initial_points', {0, 1, 3, 4}),
                      ('final_points', {0, 1, 2, 3, 4})):
        points = record[name]
        if {p['point_id'] for p in points} != ids:
            raise NVMError('calibration point IDs invalid')
        for point in points:
            _finite(point['median_mm'], 'point median', -1000, 1000)
            samples = point['samples_mm']
            if not 1 <= len(samples) <= 9:
                raise NVMError('sample count invalid')
            for value in samples:
                _finite(value, 'sample', -1000, 1000)
    if len(_canonical(record)) > 49152:
        raise NVMError('calibration observation too large')
    if record['method'] == 'M300_STOCK_FIVE_POINT_V1':
        from .m300_leveling_state import validate_observation, CalibrationError
        try:
            validate_observation(record)
        except CalibrationError as exc:
            raise NVMError(str(exc)) from exc


def _defaults(identity):
    return {'schema_version': SCHEMA_VERSION, 'model': MODEL,
            'identity': dict(identity), 'revision': 0,
            'settings': dict(DEFAULT_SETTINGS), 'calibration': None,
            'counters': {'completed_jobs': 0, 'print_seconds': 0.},
            'legacy_import': None}


def _validate_payload(data):
    if not isinstance(data, dict) or set(data) != set(_defaults({})):
        raise NVMError('unexpected NVM schema keys')
    if type(data['schema_version']) is not int or data['schema_version'] != SCHEMA_VERSION or data['model'] != MODEL:
        raise NVMError('unsupported NVM schema/model')
    _identity(**data['identity'])
    if type(data['revision']) is not int or not 0 <= data['revision'] < 2**63:
        raise NVMError('invalid revision')
    settings = data['settings']
    if not isinstance(settings, dict) or not DEFAULT_SETTINGS.keys() <= settings.keys() <= CHOICES.keys():
        raise NVMError('invalid settings keys')
    for key, value in settings.items():
        validate_setting(key, value)
    if set(data['counters']) != {'completed_jobs', 'print_seconds'}:
        raise NVMError('invalid counters')
    jobs = data['counters']['completed_jobs']
    if type(jobs) is not int or not 0 <= jobs < 2**63:
        raise NVMError('invalid completed job count')
    _finite(data['counters']['print_seconds'], 'print_seconds', 0., 1.e15)
    validate_calibration(data['calibration'])
    _check_no_live(data['legacy_import'])


def encode_document(data):
    _validate_payload(data)
    digest = hashlib.sha256(_canonical(data)).hexdigest()
    encoded = _canonical({'payload': data, 'sha256': digest}) + b'\n'
    if len(encoded) > MAX_BYTES:
        raise NVMError('NVM exceeds bounded size')
    return encoded


def decode_document(raw):
    if not 0 < len(raw) <= MAX_BYTES:
        raise NVMError('NVM file size invalid')
    try:
        envelope = json.loads(raw, object_pairs_hook=_unique_pairs,
                              parse_constant=lambda x: (_ for _ in ()).throw(NVMError(x)))
        if set(envelope) != {'payload', 'sha256'}:
            raise NVMError('invalid envelope')
        data = envelope['payload']
        if hashlib.sha256(_canonical(data)).hexdigest() != envelope['sha256']:
            raise NVMError('SHA256 integrity mismatch')
        _validate_payload(data)
        return data
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError,
            RecursionError) as exc:
        raise NVMError('invalid NVM: ' + str(exc))


def _read_regular(path, maximum):
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise NVMError('input must be a bounded regular file')
        with os.fdopen(fd, 'rb', closefd=False) as source:
            raw = source.read(maximum + 1)
        if len(raw) > maximum:
            raise NVMError('file changed beyond size limit')
        return raw
    finally:
        os.close(fd)


class HostNVM:
    def __init__(self, path, machine_id, mechanics_id):
        self.path = os.path.abspath(os.path.expanduser(path))
        self.identity = _identity(machine_id, mechanics_id)
        self._writer = threading.Lock()
        self._published = _defaults(self.identity)
        self._last_good = None
        self.source, self.warnings = 'defaults', []
        self.load()

    def snapshot(self):
        # Assignment of a completely built object is the publication point.
        return copy.deepcopy(self._published)

    def load(self):
        warnings = []
        for suffix, source in (('', 'primary'), ('.bak', 'backup')):
            try:
                raw = _read_regular(self.path + suffix, MAX_BYTES)
                data = decode_document(raw)
            except (OSError, NVMError) as exc:
                if not isinstance(exc, FileNotFoundError):
                    warnings.append(source + ': ' + str(exc))
                continue
            old_identity = data['identity']
            if old_identity != self.identity:
                data['calibration'] = None
                if old_identity['machine_id'] != self.identity['machine_id']:
                    data['counters'] = {'completed_jobs': 0, 'print_seconds': 0.}
                    data['legacy_import'] = None
                data['identity'] = dict(self.identity)
                warnings.append('identity changed; calibration invalidated; UI preserved')
            if (data['calibration'] is not None
                    and data['calibration']['identity'] != self.identity):
                data['calibration'] = None
                warnings.append('calibration identity mismatch; observation invalidated')
            self._published = copy.deepcopy(data)
            self._last_good = encode_document(data)
            self.source, self.warnings = source, warnings
            return
        self._published = _defaults(self.identity)
        self.source, self.warnings = 'defaults', warnings

    def _atomic_replace(self, path, raw):
        directory = os.path.dirname(path)
        os.makedirs(directory, mode=0o700, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.m300-', suffix='.tmp', dir=directory)
        try:
            with os.fdopen(fd, 'wb') as target:
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
            dirfd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def update(self, mutation):
        with self._writer:
            data = self.snapshot()
            mutation(data)
            data['identity'] = dict(self.identity)
            data['revision'] += 1
            raw = encode_document(data)
            # Never replace the valid backup with corrupt primary bytes.
            if self._last_good is not None:
                self._atomic_replace(self.path + '.bak', self._last_good)
            self._atomic_replace(self.path, raw)
            self._last_good = raw
            self._published = copy.deepcopy(data)
            self.source = 'primary'
            self.warnings = []
        return self.snapshot()


    def prepare_update(self, mutation):
        """Stage a complete document without publishing it; worker thread only."""
        with self._writer:
            data = self.snapshot()
            revision = data['revision']
            mutation(data)
            data['identity'] = dict(self.identity)
            data['revision'] += 1
            raw = encode_document(data)
            directory = os.path.dirname(self.path)
            os.makedirs(directory, mode=0o700, exist_ok=True)
            fd, path = tempfile.mkstemp(prefix='.m300-', suffix='.tmp', dir=directory)
            try:
                with os.fdopen(fd, 'wb') as target:
                    target.write(raw)
                    target.flush()
                    os.fsync(target.fileno())
            except BaseException:
                if os.path.exists(path):
                    os.unlink(path)
                raise
            return dict(path=path, raw=raw, data=data, revision=revision)

    def discard_update(self, staged):
        if staged is not None and os.path.exists(staged['path']):
            os.unlink(staged['path'])

    def publish_update(self, staged):
        """Publish only a previously accepted, complete staged document.

        Authorization occurs on the reactor before entry. Cancellation after
        that boundary revokes UI COMPLETE, not a potentially durable record.
        No position, ARM or live resume authority is ever restored from it.
        """
        try:
            with self._writer:
                if self._published['revision'] != staged['revision']:
                    raise NVMError('NVM revision changed during staging')
                if self._last_good is not None:
                    self._atomic_replace(self.path + '.bak', self._last_good)
                os.replace(staged['path'], self.path)
                dirfd = os.open(os.path.dirname(self.path), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                try:
                    os.fsync(dirfd)
                finally:
                    os.close(dirfd)
                self._last_good = staged['raw']
                self._published = copy.deepcopy(staged['data'])
                self.source, self.warnings = 'primary', []
            return self.snapshot()
        finally:
            self.discard_update(staged)


def parse_legacy(raw, page=None):
    """Read-only archival parser. Receiving pages are never promoted."""
    if len(raw) == 262144:
        pages = (raw[0x3e800:0x3f000], raw[0x3f000:0x3f800])
    elif len(raw) == 4096:
        pages = (raw[:2048], raw[2048:])
    else:
        raise NVMError('legacy requires 4096 B A+B or 256 KiB dump')
    states = {0: 'VALID', 0xeeee: 'RECEIVING', 0xffff: 'ERASED'}
    headers = [states.get(struct.unpack_from('<H', p)[0], 'INVALID') for p in pages]
    if page is not None and page not in ('A', 'B'):
        raise NVMError('PAGE must be A or B')
    valids = [i for i, state in enumerate(headers) if state == 'VALID']
    if not valids:
        raise NVMError('no VALID legacy page; receiving not promoted')
    if page is None:
        if len(valids) != 1:
            raise NVMError('both legacy pages VALID; explicit PAGE=A/B required')
        index = valids[0]
    else:
        index = 'AB'.index(page)
        if index not in valids:
            raise NVMError('selected legacy page is not VALID')
    data, offset, values, warnings = pages[index], 4, {}, []
    lengths = (4, 2, 2, 2, 2, 4, 4)
    while offset + 2 <= len(data):
        field = struct.unpack_from('<H', data, offset)[0]
        if field == 0xffff:
            if any(b != 0xff for b in data[offset:]):
                warnings.append('non-erased bytes after terminator ignored')
            break
        if field >= len(lengths):
            raise NVMError('unknown legacy ID at offset %d' % offset)
        end = offset + 2 + lengths[field]
        if end > len(data):
            warnings.append('truncated final legacy record ignored')
            break
        payload = data[offset+2:end]
        if all(b == 0xff for b in payload):
            warnings.append('erased/incomplete payload ID%d ignored' % field)
            break
        if field in (1, 2, 3, 4):
            v = struct.unpack('<H', payload)[0]
            valid = ((field == 1 and v <= 2)
                     or (field == 2 and not (v & ~0xf3))
                     or (field == 3 and v <= 4)
                     or (field == 4 and v <= 3))
            if not valid:
                warnings.append('invalid value ID%d ignored' % field)
                offset = end
                continue
        values[str(field)] = payload.hex()
        offset = end
    result = {'source_sha256': hashlib.sha256(raw).hexdigest(),
              'source_bytes': len(raw), 'page': 'AB'[index], 'headers': headers,
              'records_hex': values, 'warnings': warnings,
              'legacy_opaque': {key: values[key] for key in ('5', '6') if key in values}}
    return result


class M300NVM:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        path = config.get('path', '~/printer_data/config/m300_settings.json')
        try:
            self.store = HostNVM(path, config.get('machine_id', 'UNQUALIFIED_M300'),
                                 config.get('mechanics_id', 'UNQUALIFIED_MECHANICS'))
        except (NVMError, TypeError) as exc:
            raise config.error('M300 NVM: ' + str(exc))
        self.executor = self.printer.load_object(config, 'aio_executor').allocate_executor('m300-nvm')
        self._busy = False
        self._deferred_settings = {}
        self._settings_timer = self.reactor.register_timer(self._save_deferred_settings)
        self.print_clock = PrintClock()
        self._runtime_saved = (0., 0)
        self._runtime_target = None
        self._runtime_writing = False
        self._runtime_error = None
        self._runtime_timer = self.reactor.register_timer(self._save_runtime)
        for event in ('klippy:shutdown', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self._stop_runtime)
        self.printer.register_event_handler('klippy:disconnect', self._disconnect_runtime)
        for name, fn in (('ZORTRAX_SETTING', self.cmd_setting),
                         ('ZORTRAX_NVM_IMPORT', self.cmd_import),
                         ('ZORTRAX_NVM_STATUS', self.cmd_status)):
            self.gcode.register_command(name, fn, when_not_ready=name.endswith('STATUS'))

    def snapshot(self):
        return self.store.snapshot()

    def ui_snapshot(self):
        """Small independent UI snapshot; do not copy the observation ledger."""
        data = self.store._published
        return dict(revision=data['revision'], settings=dict(data['settings'], **self._deferred_settings),
                    identity=dict(data['identity']), counters=dict(data['counters']),
                    source=self.store.source)

    def get_ownership_status(self, eventtime):
        return dict(state='WRITING' if self._busy else 'IDLE',busy=self._busy)

    def get_setting(self, name, default=None):
        if name == 'language':
            return 'EN'
        if name in BRIGHTNESS_KEYS and default is None:
            default = MAX_BRIGHTNESS
        return self._deferred_settings.get(name, self.store._published['settings'].get(name, default))

    def is_busy(self):
        return self._busy

    def runtime_start(self, now):
        self.print_clock.start(now, self.printer.lookup_object('toolhead', None))
        self.reactor.update_timer(self._runtime_timer, self.reactor.NOW)

    def runtime_pause(self, now, *, drain=True):
        if drain:
            self.print_clock.request_stop(now)
        else:
            self.print_clock.stop(now)
        self.reactor.update_timer(self._runtime_timer, self.reactor.NOW)

    def runtime_drained(self, now):
        self.print_clock.drain(now, self.printer.lookup_object('toolhead', None))
        self.reactor.update_timer(self._runtime_timer, self.reactor.NOW)

    def runtime_complete(self):
        self.print_clock.completed += 1
        self.reactor.update_timer(self._runtime_timer, self.reactor.NOW)

    @property
    def runtime_error(self):
        return self._runtime_error

    def _stop_runtime(self, *args):
        # Shutdown callbacks cannot yield. The next timer writes any final
        # sample while the reactor still runs, and disconnect drains it too.
        now = self.reactor.monotonic()
        cutoff = self.print_clock.drain_since
        self.runtime_pause(now if cutoff is None else cutoff, drain=False)

    def _disconnect_runtime(self):
        now = self.reactor.monotonic()
        cutoff = self.print_clock.drain_since
        self.print_clock.stop(now if cutoff is None else cutoff)
        self._save_runtime(now, disconnected=True)

    def _save_runtime(self, now, disconnected=False):
        clock = self.print_clock
        if clock.drain_since is not None:
            toolhead = self.printer.lookup_object('toolhead', None)
            clock.drain(now, toolhead)
            if clock.drain_since is not None:
                # Write only measured time up to the stop request until the
                # native movement queue reports when its last move finished.
                now = clock.drain_since
        elapsed, jobs = sample = clock.snapshot(now)
        saved_elapsed, saved_jobs = self._runtime_saved
        seconds, completed = elapsed - saved_elapsed, jobs - saved_jobs
        if self._busy and not disconnected and (seconds > 0. or completed):
            # Let an already staged calibration retain its revision through
            # publication. Ordinary model printing takes no settings lease.
            return self.reactor.monotonic() + DRAIN_POLL_SECONDS
        if (not self._runtime_writing or disconnected) and (seconds > 0. or completed):
            def mutate(data):
                counters = data['counters']
                # An executor may finish after its reactor waiter stopped.
                # Persist an absolute target to make the final retry safe.
                counters['print_seconds'] = max(counters['print_seconds'], target_seconds)
                counters['completed_jobs'] = max(counters['completed_jobs'], target_jobs)

            if self._runtime_target is None:
                counters = self.ui_snapshot()['counters']
                self._runtime_target = (counters['print_seconds'] + seconds,
                                        counters['completed_jobs'] + completed, sample)
            target_seconds, target_jobs, committed_sample = self._runtime_target
            self._runtime_writing = True
            try:
                if disconnected:
                    # Disconnect runs after the reactor exits. Waiting on an
                    # executor completion here would no longer be serviced.
                    self.store.update(mutate)
                else:
                    self.executor.submit(self.store.update, mutate)
                self._runtime_saved = committed_sample
                self._runtime_target = None
                self._runtime_error = None
            except (NVMError, OSError, TypeError, KeyError) as exc:
                self._runtime_error = str(exc)
                logging.warning('M300 runtime checkpoint failed: %s', exc)
            finally:
                self._runtime_writing = False
            if disconnected and self._runtime_saved == committed_sample and sample != committed_sample:
                return self._save_runtime(now, disconnected=True)
        if clock.drain_since is not None:
            return self.reactor.monotonic() + DRAIN_POLL_SECONDS
        resumed = self.reactor.monotonic()
        if clock.since is not None or self._runtime_error is not None:
            return resumed + CHECKPOINT_SECONDS
        if clock.snapshot(resumed) != self._runtime_saved:
            return self.reactor.NOW
        return self.reactor.NEVER

    def _guard(self, calibration=False, completed_job=False, completion_token=None):
        if self._busy or self.printer.is_shutdown():
            raise self.printer.command_error('M300 NVM unavailable/busy')
        completion_authorized = False
        if completed_job and completion_token is not None:
            owner = self.printer.lookup_object('m300_job', None)
            try:
                completion_authorized = (
                    owner is not None
                    and owner.completion_write_authorized(completion_token) is True)
            except Exception:
                completion_authorized = False
            if not completion_authorized:
                raise self.printer.command_error('M300 NVM completion token is stale or unauthorized')
        now = self.reactor.monotonic()
        for name in ('m300_job', 'm300_filament', 'm300_calibration',
                     'm300_maintenance', 'm300_sd', 'm300_motion', 'm300_fans', 'm300_thermal'):
            obj = self.printer.lookup_object(name, None)
            if obj is None:
                continue
            try:
                status = obj.get_status(now)
                if not isinstance(status, dict):
                    raise ValueError('status is not a dictionary')
                state = status.get('state')
                if not isinstance(state, str) or not state.strip():
                    raise ValueError('owner state is missing or invalid')
                busy = (obj.is_busy() if hasattr(obj, 'is_busy') else
                        status.get('busy', status.get('active')))
                if type(busy) is not bool:
                    raise ValueError('ownership is not an explicit boolean')
            except Exception as exc:
                raise self.printer.command_error(
                    'M300 NVM blocked by invalid owner status: %s (%s)' % (name, exc))
            if state.upper() in ('FAULT', 'SLEEP', 'SLEEPING'):
                busy = True
            if name == 'm300_job':
                busy = busy or status.get('state') not in (
                    'IDLE', 'COMPLETE', 'CANCELLED', 'FILE_ERROR')
                if completed_job and status.get('state') == 'COMPLETE':
                    busy = False
                if (completed_job and completion_authorized
                        and status.get('state') == 'COMPLETING'):
                    busy = False
            if calibration and name == 'm300_calibration' and status.get('state') == 'REVIEW':
                continue
            if busy:
                raise self.printer.command_error('M300 NVM blocked by ' + name)

    def _write(self, mutation, calibration=False, completed_job=False,
               completion_token=None):
        self._guard(calibration=calibration, completed_job=completed_job,
                    completion_token=completion_token)
        self._busy = True
        try:
            return self.executor.submit(self.store.update, mutation)
        except (NVMError, OSError, TypeError, KeyError) as exc:
            from .m300_error_codes import report
            report(self.printer, exc, source='m300_nvm')
            raise self.printer.command_error('M300 NVM: ' + str(exc))
        finally:
            self._busy = False

    def set_setting(self, name, value):
        if name == 'light_mode' and value == 'DISABLED':
            value = 'DISABLE'
        if name == 'language' and value != 'EN':
            raise self.printer.command_error('This host supports English only')
        try:
            validate_setting(name, value)
        except NVMError as exc:
            raise self.printer.command_error(str(exc))
        if self.get_setting(name) == value:
            return self.ui_snapshot()
        if name in COSMETIC_SETTINGS:
            try:
                self._guard()
            except self.printer.command_error:
                if self.printer.is_shutdown():
                    raise
                self._deferred_settings[name] = value
                self.reactor.update_timer(self._settings_timer, self.reactor.NOW)
                self.printer.send_event('m300:setting_changed', name, value)
                return self.ui_snapshot()
        previous = self._deferred_settings.get(name)
        result = self._write(lambda data: data['settings'].__setitem__(name, value))
        if self._deferred_settings.get(name) == previous:
            self._deferred_settings.pop(name, None)
        self.printer.send_event('m300:setting_changed', name, self.get_setting(name))
        return result

    def _save_deferred_settings(self, now):
        if not self._deferred_settings or self.printer.is_shutdown():
            return self.reactor.NEVER
        try:
            self._guard()
        except self.printer.command_error:
            return now + 1.
        pending = dict(self._deferred_settings)
        try:
            self._write(lambda data: data['settings'].update(pending))
        except self.printer.command_error as exc:
            logging.warning('M300 UI settings awaiting storage: %s', exc)
            return self.reactor.monotonic() + 5.
        for key, value in pending.items():
            if self._deferred_settings.get(key) == value:
                del self._deferred_settings[key]
        return self.reactor.monotonic() + 1. if self._deferred_settings else self.reactor.NEVER

    def commit_calibration(self, record, token=None, phase=None):
        try:
            validate_calibration(record)
            if record is None or record['identity'] != self.store.identity:
                raise NVMError('calibration identity mismatch')
        except (NVMError, KeyError, TypeError) as exc:
            raise self.printer.command_error(str(exc))
        owner = self.printer.lookup_object('m300_calibration', None)
        if owner is None:
            raise self.printer.command_error('calibration commit requires the active owner')
        current = owner.get_status(self.reactor.monotonic())
        if (token is None or phase is None or current.get('state') != 'REVIEW'
                or current.get('session_token') != token
                or current.get('phase_id') != phase or record['session_token'] != token):
            raise self.printer.command_error('stale calibration commit token/phase')
        if current.get('workflow') == 'M07_STOCK':
            expected = owner.get_commit_observation(token, phase)
            if _canonical(record) != _canonical(expected):
                raise self.printer.command_error('M07 commit differs from the active complete observation')
        job = self.printer.lookup_object('m300_job', None)
        if job is not None:
            job._bind_resources()
            if any(h.get_temp(self.reactor.monotonic())[1] != 0.
                   for h in (job.hotend, job.bed)):
                raise self.printer.command_error('calibration commit requires heaters off')
        # Freeze caller data before yielding; never use a mutable UI record in I/O.
        record = copy.deepcopy(record)
        self._guard(calibration=True)
        self._busy = True
        staged = None
        self.calibration_write_phase = 'PREPARING'
        self.calibration_write_outcome = 'PENDING'
        def check_owner():
            if self.printer.is_shutdown():
                raise self.printer.command_error('calibration commit interrupted by shutdown')
            current = owner.get_status(self.reactor.monotonic())
            if (current.get('state') != 'REVIEW'
                    or current.get('session_token') != token
                    or current.get('phase_id') != phase):
                raise self.printer.command_error('calibration commit token/phase revoked during storage')
            # Also recheck current geometry, position, deadlines and heater state.
            expected = owner.get_commit_observation(token, phase)
            if _canonical(record) != _canonical(expected):
                raise self.printer.command_error('calibration observation changed during storage')
        try:
            staged = self.executor.submit(self.store.prepare_update,
                lambda data: data.__setitem__('calibration', record))
            check_owner()
            # Linearization boundary: complete observation has been confirmed
            # and is accepted for atomic publication. No synchronous fsync.
            self.calibration_write_phase = 'PUBLISHING'
            self.calibration_write_outcome = 'ACCEPTED_FOR_PUBLICATION'
            result = self.executor.submit(self.store.publish_update, staged)
            staged = None
            self.calibration_write_outcome = 'DURABLE'
            check_owner()  # never publish stale COMPLETE into a cancelled session
            return result
        except Exception as exc:
            if self.calibration_write_phase == 'PREPARING':
                self.calibration_write_outcome = 'NOT_PUBLISHED'
            elif self.calibration_write_outcome != 'DURABLE':
                self.calibration_write_outcome = 'PUBLICATION_UNCERTAIN'
            if isinstance(exc, (NVMError, OSError, ValueError, TypeError, KeyError)):
                from .m300_error_codes import report
                report(self.printer, exc, source='m300_nvm')
                raise self.printer.command_error('NVM: ' + str(exc))
            raise
        finally:
            try:
                if staged is not None:
                    self.executor.submit(self.store.discard_update, staged)
            finally:
                self.calibration_write_phase = 'IDLE'
                self._busy = False

    def record_completed_job(self, seconds, token=None, *, native=False):
        try:
            _finite(seconds, 'completed duration', 0., 1.e9)
        except NVMError as exc:
            raise self.printer.command_error(str(exc))
        def mutate(data):
            data['counters']['completed_jobs'] += 1
            data['counters']['print_seconds'] += seconds
        if native:
            # Native Klippy already published EOF. Serialize this accounting
            # write with other NVM updates without taking a printer resource
            # lease, so a ready Reprint stays usable while the disk flushes.
            return self.executor.submit(self.store.update, mutate)
        return self._write(mutate, completed_job=True, completion_token=token)

    def import_legacy(self, path, page=None):
        def mutate(data):
            # _write owns the service lock across this executor read and commit.
            legacy = parse_legacy(_read_regular(os.path.expanduser(path), 262144), page)
            data['legacy_import'] = legacy
            data['calibration'] = None
            records = legacy['records_hex']
            if '3' in records:
                data['settings']['language'] = CHOICES['language'][int.from_bytes(bytes.fromhex(records['3']), 'little')]
            if '2' in records:
                flags = int.from_bytes(bytes.fromhex(records['2']), 'little')
                data['settings']['sound'] = bool(flags & 1)
                data['settings']['full_platform_preheat'] = bool(flags & 2)
            # Preserve raw light/sleep/sort/usage; their numeric encodings/units
            # are not silently equated with the host's named policies.
        result = self._write(mutate)
        for name, value in self.store._published['settings'].items():
            self.printer.send_event('m300:setting_changed', name, value)
        return result

    def get_status(self, eventtime):
        data = self.snapshot()
        data.update(busy=self._busy, state='WRITING' if self._busy else 'IDLE',
                    calibration_write_phase=getattr(self, 'calibration_write_phase', 'IDLE'),
                    calibration_write_outcome=getattr(self, 'calibration_write_outcome', 'NONE'),
                    source=self.store.source, warnings=list(self.store.warnings),
                    runtime_checkpoint_error=self.runtime_error,
                    runtime_checkpoint_interval=CHECKPOINT_SECONDS,
                    hardware_qualified=False,
                    sleep_seconds=SLEEP_SECONDS[data['settings']['sleep_mode']],
                    setting_choices={name: [{'value': value, 'label': LABELS.get(value, str(value))}
                                            for value in choices]
                                     for name, choices in CHOICES.items()})
        data['settings']['language'] = 'EN'
        data['setting_choices']['language'] = [{'value':'EN','label':'English'}]
        data['language_profile'] = 'EN_ONLY'
        return data

    def cmd_setting(self, gcmd):
        name, raw = gcmd.get('NAME').lower(), gcmd.get('VALUE')
        if name in ('sound', 'sleep_light', 'full_platform_preheat'):
            if str(raw).lower() not in ('true', 'false', '0', '1'):
                raise gcmd.error('VALUE must be true/false/0/1')
            value = str(raw).lower() in ('true', '1')
        else:
            value = str(raw).upper()
        self.set_setting(name, value)
        self.cmd_status(gcmd)

    def cmd_import(self, gcmd):
        self.import_legacy(gcmd.get('FILE'), gcmd.get('PAGE', None))
        self.cmd_status(gcmd)

    def cmd_status(self, gcmd):
        gcmd.respond_info(json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))


def load_config(config):
    return M300NVM(config)
