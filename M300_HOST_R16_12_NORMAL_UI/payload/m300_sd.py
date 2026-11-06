# SPDX-License-Identifier: GPL-3.0-or-later
"""Physical SD on the M300 MCU SPI1, read-only, before print preparation.

Public API: list_files(path='/') -> list of entry dictionaries;
get_snapshot(path, checkpoint=None) -> (anonymous O_RDONLY binary stream, meta).
Call these from a cooperative reactor/G-code context, never an OS worker.
Each serial transaction yields with reactor.completion.wait(). A returned file
still needs the independent JobSD dialect/binary preflight before execution.
"""
import hashlib
import logging
import math
import os
import secrets
import tempfile

from .m300_fat import FATVolume, FATError, path_parts

DONE = 'm300_sd_done session=%u token=%u error=%c blocks=%u data=%*s'
DATA = 'm300_sd_data session=%u token=%u offset=%hu data=%*s'
SNAPSHOT_BATCH_BYTES = 64 * 1024
ERRORS = {1: 'card deadline', 2: 'SPI timeout', 3: 'card command response',
          4: 'card data token', 5: 'sector/register CRC16', 6: 'card capacity',
          7: 'stale/invalid card session', 8: 'card busy', 9: 'out-of-range read'}


class SDError(ValueError):
    pass


def _new_snapshot():
    fd, path = tempfile.mkstemp(prefix='m300_sd_', suffix='.snapshot')
    try:
        os.fchmod(fd, 0o400)
        return os.fdopen(fd, 'wb', buffering=SNAPSHOT_BATCH_BYTES), path
    except Exception:
        os.close(fd)
        os.unlink(path)
        raise


def _seal_snapshot(writer, path):
    writer.flush()
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.unlink(path)
        writer.close()
        return os.fdopen(fd, 'rb', buffering=0)
    except Exception:
        os.close(fd)
        raise


class M300SD:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.board = self.printer.load_object(config, 'm300_mcu')
        # Only disk I/O runs in the native executor. Card requests stay in the
        # cooperative reactor context so MCU completion callbacks remain safe.
        self.v_sd = self.printer.load_object(config, 'virtual_sdcard')
        self.executor = self.v_sd.executor
        self.mcu = self.board.get_mcu()
        self.qualified = config.getboolean('sd_qualified', False)
        self.rate = config.getint('spi_speed', 1000000, minval=500000, maxval=2000000)
        self.timeout = config.getfloat('request_timeout', 2., minval=1.1, maxval=10.)
        self.total_timeout = config.getfloat('import_timeout', 3600., minval=10., maxval=7200.)
        for name, value in (('request_timeout', self.timeout),
                            ('import_timeout', self.total_timeout)):
            if not math.isfinite(value):
                raise config.error('M300 SD %s must be finite' % name)
        self.max_file_bytes = config.getint('max_file_bytes', 16 * 1024 * 1024,
                                            minval=1024, maxval=128 * 1024 * 1024)
        self.connected = self.busy = False
        self.generation = self.session = self.token = 0
        self.pending = self.info = None
        self.state = 'disconnected'
        self.last_error = None
        self.bytes_copied = self.ignored_responses = 0
        self.work_generation = self.work_deadline = None
        self.external_checkpoint = None
        self.owner = self.owner_generation = None
        self.commands = {}
        self.cq = self.mcu.alloc_command_queue()
        self.mcu.register_config_callback(self._build_config)
        self.printer.register_event_handler('klippy:ready', self._ready)
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self._stop)
        self.gcode.register_command('ZORTRAX_SD_STATUS', self.cmd_status, when_not_ready=True)
        self.gcode.register_command('ZORTRAX_SD_LIST', self.cmd_list)
        self.gcode.register_command('ZORTRAX_SD_CANCEL', self.cmd_cancel)

    def _build_config(self):
        constants = self.mcu.get_constants()
        for name, value in {'M300_MODEL': 'M300_CLASSIC', 'M300_ABI': 1,
                            'M300_SD_ABI': 1, 'M300_SD_READ_ONLY': 1,
                            'M300_SD_MAX_CHUNK': 32,
                            'M300_SD_TASK_BYTES': 32,
                            'M300_SD_POLL_US': 1000}.items():
            if str(constants.get(name)) != str(value):
                raise self.printer.config_error('M300 SD ABI mismatch: ' + name)
        for response in (DONE, DATA):
            if not self.mcu.check_valid_response(response):
                raise self.printer.config_error('M300 SD missing response: ' + response)
        formats = {
            'config': 'm300_sd_config rate=%u',
            'open': 'm300_sd_open session=%u token=%u',
            'read': 'm300_sd_read session=%u token=%u lba=%u',
            'chunk': 'm300_sd_chunk session=%u token=%u read_token=%u offset=%hu count=%c',
            'close': 'm300_sd_close session=%u token=%u',
        }
        for name, fmt in formats.items():
            self.commands[name] = self.mcu.lookup_command(fmt, cq=self.cq)
        self.mcu.register_serial_response(self._done, DONE)
        self.mcu.register_serial_response(self._data, DATA)
        self.mcu.add_config_cmd('m300_sd_config rate=%d' % self.rate)

    def _ready(self):
        self.generation += 1
        self.connected = True
        self.state = 'idle'
        self.info = None

    def _stop(self, *args):
        self.cancel('host lifecycle stopped', send_close=False)
        self.connected = False
        self.state = 'disconnected'

    def _next_token(self):
        self.token += 1
        if self.token > 0xffffffff:
            raise SDError('SD request counter exhausted; restart host')
        return self.token

    def _receive(self, kind, params):
        generation = self.generation
        copied = dict(params)
        def deliver(eventtime):
            result = copied
            if generation != self.generation or not self.connected:
                self.ignored_responses += 1
                return
            pending = self.pending
            if (pending is None or copied.get('session') != pending['session']
                    or copied.get('token') != pending['token']):
                self.ignored_responses += 1
                return
            # MCU may report an error via DONE even if the caller requested
            # a DATA chunk. Other response-type mismatches cannot satisfy it.
            if kind != pending['kind'] and not (kind == 'done' and copied.get('error')):
                self.ignored_responses += 1
                return
            if kind == 'data':
                try:
                    data = bytes(copied.get('data', b''))
                except (TypeError, ValueError):
                    data = b''
                if (copied.get('offset') != pending['offset']
                        or len(data) != pending['count']):
                    result = {'failure': 'SD chunk offset/length mismatch'}
                else:
                    copied['data'] = data
            pending['completion'].complete(result)
        self.reactor.register_async_callback(deliver)

    def _done(self, params):
        self._receive('done', params)

    def _data(self, params):
        self._receive('data', params)

    def _request(self, command, args=(), timeout=None, offset=None, count=None):
        self._checkpoint()
        if self.pending is not None:
            raise SDError('overlapping SD transaction')
        token = self._next_token()
        pending = {'session': self.session, 'token': token,
                   'kind': 'data' if command == 'chunk' else 'done',
                   'offset': offset, 'count': count,
                   'completion': self.reactor.completion()}
        self.pending = pending
        try:
            self.commands[command].send([self.session, token, *args])
            end = self.reactor.monotonic() + (self.timeout if timeout is None else timeout)
            result = pending['completion'].wait(end)
            self._checkpoint()
            if result is None:
                raise SDError('SD response timeout')
            if result.get('failure'):
                raise SDError(result['failure'])
            if result.get('error', 0):
                raise SDError(ERRORS.get(result['error'], 'unknown SD error'))
            return result, token
        finally:
            if self.pending is pending:
                self.pending = None

    def _checkpoint(self):
        if (not self.connected or self.printer.is_shutdown()
                or self.work_generation != self.generation or not self.busy):
            raise SDError('SD operation cancelled or restarted')
        if self.reactor.monotonic() >= self.work_deadline:
            raise SDError('SD import/list deadline exceeded')
        self._check_services(self.owner)
        if self.owner is not None and (
                getattr(self.owner, '_generation', None) != self.owner_generation
                or not self.owner.is_preparing or getattr(self.owner, '_halted', False)):
            raise SDError('owning JobSD preparation changed or was cancelled')
        if self.external_checkpoint is not None:
            self.external_checkpoint()

    def _check_services(self, owner):
        if (self.v_sd.current_file is not None or self.v_sd.work_timer is not None):
            raise SDError('physical SD requires an idle native print')
        job = self.printer.lookup_object('m300_job', None)
        job_sd = getattr(job, 'sd', None)
        if owner is not None and (owner is not job_sd or not owner.is_preparing):
            raise SDError('SD preparation owner is not the current JobSD')
        if job is not None:
            machine = getattr(job, 'machine', None)
            if (machine is not None and (machine.active or machine.state == 'FAULT')):
                raise SDError('physical SD import requires an idle job')
            if any(bool(getattr(job, name, False)) for name in
                   ('_waiting', '_executing', '_native_homing', '_cleanup_pending',
                    '_resume_checking')) or getattr(job, '_ops', ()):
                raise SDError('job cleanup or motion remains active')
            if job_sd is not None and (any(bool(getattr(job_sd, name, False))
                    for name in ('_session', '_verifying', '_in_worker'))
                    or (getattr(job_sd, 'is_preparing', False) and owner is not job_sd)):
                raise SDError('another JobSD file operation is active')
        now = self.reactor.monotonic()
        for name in ('m300_filament', 'm300_calibration', 'm300_maintenance',
                     'm300_nvm', 'm300_motion', 'm300_fans', 'm300_thermal'):
            obj = self.printer.lookup_object(name, None)
            if obj is not None:
                try:
                    status = getattr(obj, 'get_ownership_status', obj.get_status)(now)
                except Exception as exc:
                    raise SDError(name + ' ownership status unavailable: ' + str(exc))
                if (not isinstance(status, dict) or status.get('busy') is not False
                        or not isinstance(status.get('state'), str) or not status['state'].strip()
                        or status['state'].upper() in ('FAULT', 'SLEEP', 'SLEEPING')):
                    raise SDError(name + ' is active or ownership status is invalid')

    def _ensure_available(self, owner=None):
        if not self.qualified:
            raise SDError('physical SD is not qualified; sd_qualified=False')
        if not self.connected or self.printer.is_shutdown():
            raise SDError('SD host/MCU is not ready')
        if self.mcu.is_fileoutput():
            raise SDError('FILEOUTPUT does not execute a physical SD card')
        if self.busy or self.pending is not None:
            raise SDError('another SD operation is active')
        self._check_services(owner)

    def _begin(self, state, owner=None, checkpoint=None):
        self._ensure_available(owner)
        self.generation += 1
        self.work_generation = self.generation
        self.work_deadline = self.reactor.monotonic() + self.total_timeout
        self.external_checkpoint = checkpoint
        self.owner = owner
        self.owner_generation = getattr(owner, '_generation', None)
        self.busy = True
        self.state = state
        self.last_error = None
        self.bytes_copied = 0

    def _open(self):
        self.session = secrets.randbits(32) or 1
        response, _ = self._request('open', timeout=max(6., self.timeout))
        data = bytes(response.get('data', b''))
        blocks = response.get('blocks')
        if len(data) != 32 or isinstance(blocks, bool) or not isinstance(blocks, int) \
                or not 1 <= blocks <= 0xffffffff:
            raise SDError('invalid SD CID/CSD/capacity response')
        self.info = {'cid': data[:16].hex(), 'csd': data[16:].hex(), 'blocks': blocks}
        return dict(self.info)

    def _read_sector(self, lba, size=512):
        self._checkpoint()
        if self.info is None or not 0 <= lba < self.info['blocks']:
            raise SDError('SD sector outside card')
        if not 1 <= size <= 512:
            raise SDError('invalid SD sector prefix size')
        response, read_token = self._request('read', [lba])
        if response.get('data') not in (None, b'', ''):
            raise SDError('unexpected read-completion payload')
        # The MCU checks the whole 512-byte sector CRC before any chunk is
        # available. Only transfer the bytes the file uses from its last sector.
        result = bytearray()
        for offset in range(0, size, 32):
            count = min(32, size - offset)
            part, _ = self._request('chunk', [read_token, offset, count],
                                    offset=offset, count=count)
            result.extend(part['data'])
        return bytes(result)

    def _write_batch(self, writer, digest, batch):
        self._checkpoint()
        if self.executor.submit(writer.write, batch) != len(batch):
            raise SDError('incomplete local SD snapshot write')
        self._checkpoint()
        digest.update(batch)
        batch.clear()

    def _close_silent(self):
        if self.connected and self.session and not self.printer.is_shutdown():
            try:
                self.commands['close'].send([self.session, self._next_token()])
            except Exception:
                pass

    def _end(self, error=None):
        self._close_silent()
        self.busy = False
        self.external_checkpoint = None
        self.owner = self.owner_generation = None
        self.work_generation = self.work_deadline = None
        if error is not None:
            self.last_error = str(error)
            from .m300_error_codes import report
            report(self.printer, error, source='m300_sd')
            self.state = 'error' if self.connected else 'disconnected'
            self.info = None
        else:
            self.state = 'idle'

    def cancel(self, reason='SD operation cancelled', send_close=True):
        self.generation += 1
        if send_close:
            self._close_silent()
        self.info = None
        self.last_error = reason
        self.state = 'cancelled'
        if self.pending is not None:
            self.pending['completion'].complete({'failure': reason})
        # busy is released by the owner finally block. An old cancelled
        # worker cannot coexist with a new importer in the meantime.

    def list_files(self, path='/', owner=None, checkpoint=None):
        path_parts(path)
        self._begin('listing', owner, checkpoint)
        error = None
        try:
            info = self._open()
            volume = FATVolume(self._read_sector, info['blocks'])
            candidates = volume.list_directory(path, limit=4096)
            extensions = {'.zcode', '.gcode', '.gco', '.g'}
            entries = [e for e in candidates if e.directory
                       or os.path.splitext(e.name)[1].lower() in extensions]
            if len(entries) > 50:
                raise SDError('directory exceeds 50 selectable SD entries')
            self._checkpoint()
            prefix = '/'.join(path_parts(path))
            return [{'name': e.name, 'path': (prefix + '/' if prefix else '') + e.name,
                     'size': e.size, 'directory': e.directory, 'modified': e.modified,
                     'fingerprint': e.fingerprint}
                    for e in entries]
        except Exception as exc:
            error = exc
            raise
        finally:
            self._end(error)

    def get_snapshot(self, path, owner=None, checkpoint=None, expected=None):
        path_parts(path)
        self._begin('importing', owner, checkpoint)
        writer = raw = None
        temporary = None
        error = None
        try:
            before_info = self._open()
            volume = FATVolume(self._read_sector, before_info['blocks'],
                               read_prefix=self._read_sector)
            entry = volume.resolve(path)
            if expected is not None and (expected['cid'] != before_info['cid']
                    or expected['fingerprint'] != entry.fingerprint
                    or expected['size'] != entry.size):
                raise SDError('SD card or selected file changed; reopen the directory')
            writer, temporary = self.executor.submit(_new_snapshot)
            self._checkpoint()
            digest = hashlib.sha256()
            batch = bytearray()
            for data in volume.iter_file(entry, self.max_file_bytes):
                self._checkpoint()
                batch.extend(data)
                self.bytes_copied += len(data)
                if len(batch) >= SNAPSHOT_BATCH_BYTES:
                    self._write_batch(writer, digest, batch)
            if batch:
                self._write_batch(writer, digest, batch)
            self._checkpoint()
            # Fresh card initialization and uncached metadata reads detect
            # replacement and obvious mutations; they do not promise a
            # globally atomic FAT image against an external concurrent writer.
            after_info = self._open()
            after_volume = FATVolume(self._read_sector, after_info['blocks'])
            after_entry = after_volume.resolve(path)
            if (before_info != after_info or volume.volume_id != after_volume.volume_id
                    or entry != after_entry or self.bytes_copied != entry.size):
                raise SDError('SD identity or file metadata changed during import')
            raw = self.executor.submit(_seal_snapshot, writer, temporary)
            temporary = writer = None
            self._checkpoint()
            metadata = {'source': 'physical_spi1_sd', 'path': path,
                        'size': entry.size, 'sha256': digest.hexdigest(),
                        'cid': before_info['cid'], 'csd': before_info['csd'],
                        'blocks': before_info['blocks'], 'fat_bits': volume.bits,
                        'readonly_snapshot': True,
                        'card_snapshot_atomic_against_external_writes': False}
            result, raw = raw, None
            return result, metadata
        except Exception as exc:
            error = exc
            raise
        finally:
            for stream in (writer, raw):
                if stream is not None:
                    try:
                        self.executor.submit(stream.close)
                    except Exception:
                        logging.exception('M300 SD snapshot close failed')
            if temporary is not None:
                try:
                    self.executor.submit(os.unlink, temporary)
                except OSError:
                    pass
                except Exception:
                    logging.exception('M300 SD temporary snapshot unlink failed')
            self._end(error)

    def get_status(self, eventtime):
        return {'available': True, 'connected': self.connected, 'busy': self.busy,
                'sd_qualified': self.qualified, 'state': self.state,
                'last_error': self.last_error, 'card': dict(self.info or {}),
                'bytes_copied': self.bytes_copied,
                'ignored_responses': self.ignored_responses,
                'read_only': True, 'physical_hardware_tests': False}

    def cmd_status(self, gcmd):
        gcmd.respond_info(str(self.get_status(self.reactor.monotonic())))

    def cmd_list(self, gcmd):
        try:
            entries = self.list_files(gcmd.get('PATH', '/'))
        except (SDError, FATError) as exc:
            raise gcmd.error('M300 SD: ' + str(exc))
        gcmd.respond_info('\n'.join('%s %s (%d B)' %
                                   ('DIR' if e['directory'] else 'FILE', e['path'], e['size'])
                                   for e in entries) or 'SD directory empty')

    def cmd_cancel(self, gcmd):
        self.cancel()
        gcmd.respond_info('SD import cancelled; no print was started')


def load_config(config):
    return M300SD(config)
