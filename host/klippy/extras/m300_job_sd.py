# SPDX-License-Identifier: GPL-3.0-or-later
"""M02 checked G-code snapshots and sole ownership of native virtual_sdcard.

Pinned upstream private APIs used here: VirtualSD current_file/file_position/
next_file_position/file_size/work_timer/cmd_from_sd/must_pause_work, work_handler,
_reset_file and _load_file; PrintStats note_* and state/error_message; its native
Executor submit/wrap_obj. Source hashes are part of the kit API manifest.

Files are UTF-8, have a final LF, and use the explicit dialect below. A complete
syntax/parameter preflight precedes any job callback capable of heating. This
is not a proof of all transformed XYZ trajectories; native kinematics still
enforces machine bounds. M04 adds qualified binary compilation and physical
SD imports, fully checked before publication to the same M02 owner.
"""
import hashlib
import io
import logging
import math
import os
import re
import stat
import tempfile
import uuid

CHUNK = 65536
MAX_PARAMETER = 1000000.
MAX_FEEDRATE = 60000.
MAX_OVERRIDE = 200.
EXTENSIONS = {'.gcode', '.g', '.gco'}
DIALECT = {'G0', 'G1', 'G4', 'G90', 'G91', 'G92', 'M82', 'M83',
           'M104', 'M140', 'M106', 'M107', 'M220', 'M221', 'M204',
           'M400', 'START_PRINT', 'END_PRINT', 'PAUSE', 'M600'}
NUMERIC = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)')
PARAMETER = re.compile(r'([A-Za-z])\s*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))')
COMMAND = re.compile(r'(?:[GM][0-9]+|[A-Z_]+)')


class FileRejected(ValueError):
    pass


class PreparationCancelled(FileRejected):
    pass


class ReadOnlySnapshot:
    """Read-only fd, with non-reentrant invalidation across cooperative I/O.

    Klippy shutdown callbacks forbid reactor.pause(). Invalidate immediately,
    then close outside that callback or after the pending buffered I/O returns.
    Repeated owners closing the same Prepared object cannot reenter close().
    """
    def __init__(self, stream, name, owner=None):
        self._stream, self.name, self._owner = stream, name, owner
        self._closed = self._close_in_progress = self._close_scheduled = False
        self._io_active = 0

    @property
    def closed(self):
        return self._closed or self._stream.closed

    def _io(self, operation, *args):
        if self.closed:
            raise PreparationCancelled('snapshot was invalidated before ' + operation)
        self._io_active += 1
        try:
            result = getattr(self._stream, operation)(*args)
        finally:
            self._io_active -= 1
            if self._closed and not self._io_active:
                self._finish_close()
        if self._closed:
            raise PreparationCancelled('snapshot was invalidated during ' + operation)
        return result

    def read(self, size=-1):
        return self._io('read', size)

    def seek(self, offset, whence=0):
        return self._io('seek', offset, whence)

    def tell(self):
        return self._io('tell')

    def close(self):
        self._closed = True
        self._finish_close()

    def _finish_close(self):
        if self._io_active or self._close_in_progress or self._stream.closed:
            return
        reactor = None if self._owner is None else self._owner.reactor
        if reactor is not None and hasattr(reactor, 'verify_can_pause'):
            try:
                reactor.verify_can_pause()
            except Exception:
                if not self._close_scheduled:
                    self._close_scheduled = True
                    reactor.register_callback(self._deferred_close)
                return
        self._close_in_progress = True
        try:
            self._stream.close()
        finally:
            self._close_in_progress = False

    def _deferred_close(self, eventtime):
        self._close_scheduled = False
        try:
            self._finish_close()
        except Exception as exc:
            logging.exception('M300 deferred snapshot close')
            from .m300_error_codes import report
            report(self._owner.printer, exc, source='m300_job_file', code=4, fatal=True)
            if not self._owner.printer.is_shutdown():
                self._owner.printer.invoke_async_shutdown('M300 snapshot close failed')

    def write(self, data):
        raise io.UnsupportedOperation('M300 snapshot is read-only')


class Prepared:
    def __init__(self, owner, filename, digest, size, targets, textfile,
                 command_count, has_start, has_end, requires_filament=False):
        self._owner = owner
        self.filename, self.sha256, self.size = filename, digest, size
        self.targets = dict(targets)
        self.textfile = textfile
        self.command_count = command_count
        self.has_start, self.has_end = has_start, has_end
        self.requires_filament = requires_filament
        self.identity = uuid.uuid4().hex

    @property
    def closed(self):
        return self.textfile.closed

    def close(self):
        self.textfile.close()


class FeederSnapshot:
    """Native EOF releases its handle, not the owner's immutable snapshot.

    A pause racing the final native read must be resumable at EOF. Keeping the
    owner reader alive also lets explicit RESUME verify its full digest. Only
    Prepared.close closes the underlying descriptor during terminal cleanup.
    """
    def __init__(self, owner, snapshot):
        self.owner, self.snapshot = owner, snapshot

    def __getattr__(self, name):
        return getattr(self.snapshot, name)

    def _io(self, operation, *args):
        try:
            return getattr(self.snapshot, operation)(*args)
        except Exception as exc:
            # Upstream catches read/seek exceptions internally. Retain the
            # failure so a simultaneous PAUSE cannot disguise it as a pause.
            if self.owner._active_worker():
                self.owner._error_reason = 'native snapshot %s failed: %s' % (operation, exc)
                raise
            # A cancelled worker may finish a cooperative read/seek later.
            # It receives EOF/no seek; it cannot redispatch an old buffer.
            return '' if operation == 'read' else None

    def read(self, size=-1):
        return self._io('read', size)

    def seek(self, offset, whence=0):
        return self._io('seek', offset, whence)

    def close(self):
        pass


def _number(text, description):
    try:
        value = float(text)
    except (ValueError, TypeError):
        raise FileRejected('%s must be a finite number' % description)
    if not math.isfinite(value):
        raise FileRejected('%s must be a finite number' % description)
    return value


class Dialect:
    """Incremental validation; retained bytes are executed without rewriting."""
    def __init__(self, limits, supplied, max_line, max_dwell_ms, max_accel):
        self.limits, self.supplied = limits, supplied
        self.max_line, self.max_dwell_ms, self.max_accel = max_line, max_dwell_ms, max_accel
        self.line = self.command_count = 0
        self.start = self.end = self.motion_seen = False
        self.requires_filament = False
        self.header = {}
        self.temperature_requests = []

    def reject(self, message):
        raise FileRejected('line %d: %s' % (self.line, message))

    def feed(self, raw):
        self.line += 1
        if len(raw) > self.max_line:
            self.reject('line exceeds %d bytes' % self.max_line)
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            self.reject('file must be valid UTF-8 text, not binary Z-code')
        if any((ord(char) < 32 and char not in '\t\r\n') or ord(char) == 127 for char in text):
            self.reject('control characters / binary data are forbidden')
        text = text.split(';', 1)[0].strip().upper()
        if not text:
            return
        if self.end:
            self.reject('END_PRINT must be the final executable command')
        match = COMMAND.match(text)
        if match is None:
            self.reject('unsupported command syntax (UTF-8 without BOM, no numbered/checksummed lines)')
        command, rest = match.group(), text[match.end():].strip()
        if command not in DIALECT:
            if command in ('M109', 'M190', 'TEMPERATURE_WAIT'):
                self.reject('blocking temperature wait is forbidden; M02 heats asynchronously before feeding')
            if command == 'G28':
                self.reject('G28 in a file is forbidden; M02 owns homing before the feeder')
            self.reject('unsupported/unsafe command %s; no arbitrary macros or ARM/restart commands' % command)
        self.command_count += 1
        if command == 'START_PRINT':
            if self.start or self.motion_seen:
                self.reject('START_PRINT must occur once, before motion')
            self.start = True
            for field in rest.split():
                pieces = field.split('=')
                if len(pieces) != 2 or pieces[0] not in ('BED_TEMP', 'EXTRUDER_TEMP'):
                    self.reject('START_PRINT accepts only BED_TEMP and EXTRUDER_TEMP')
                key = 'bed' if pieces[0] == 'BED_TEMP' else 'hotend'
                if key in self.header:
                    self.reject('duplicate START_PRINT temperature')
                self.header[key] = _number(pieces[1], pieces[0])
            return
        params, raw_params = {}, {}
        while rest:
            parameter = PARAMETER.match(rest)
            if parameter is None:
                self.reject('invalid parameter syntax; no exponent, expression, checksum or macro arguments')
            key, value = parameter.groups()
            if key in params:
                self.reject('duplicate parameter ' + key)
            raw_params[key] = value
            params[key] = _number(value, key)
            rest = rest[parameter.end():].strip()
        allowed = {
            'G0': set('XYZEF'), 'G1': set('XYZEF'), 'G92': set('XYZE'),
            'G4': {'P'}, 'M104': {'S', 'T'}, 'M140': {'S'},
            'M106': {'S', 'P'}, 'M107': {'P'}, 'M220': {'S'},
            'M221': {'S'}, 'M204': {'S', 'P', 'T'},
        }.get(command, set())
        if set(params) - allowed:
            self.reject('unsupported parameter for ' + command)
        if command in ('G0', 'G1', 'G92'):
            if any(abs(value) > MAX_PARAMETER for key, value in params.items() if key != 'F'):
                self.reject('coordinate/extrusion parameter exceeds bounded dialect')
            if 'F' in params and not 0. < params['F'] <= MAX_FEEDRATE:
                self.reject('F must be within 0..60000 mm/min (exclusive zero)')
            if command in ('G0', 'G1') and set(params) & set('XYZE'):
                self.motion_seen = True
        elif command == 'G4':
            if not 0. <= params.get('P', 0.) <= self.max_dwell_ms:
                self.reject('G4 P exceeds bounded dwell limit')
        elif command in ('M104', 'M140'):
            if 'S' not in params:
                self.reject(command + ' requires an explicit S temperature')
            if params.get('T', 0.) != 0.:
                self.reject('M300 has only extruder T0')
            if 'T' in raw_params and '.' in raw_params['T']:
                self.reject('M104 T must use an integer token, matching native Klipper')
            name = 'hotend' if command == 'M104' else 'bed'
            self._temperature(name, params['S'])
            self.temperature_requests.append((self.line, name, params['S']))
        elif command in ('M106', 'M107'):
            if params.get('P', 0.) != 0.:
                self.reject('only the native print fan P0 is available')
            if not 0. <= params.get('S', 255.) <= 255.:
                self.reject('fan S must be within 0..255')
        elif command in ('M220', 'M221'):
            if 'S' not in params or not 0. < params['S'] <= MAX_OVERRIDE:
                self.reject(command + ' requires 0 < S <= 200')
        elif command == 'M204':
            values = ([params['S']] if set(params) == {'S'} else
                      [params['P'], params['T']] if set(params) == {'P', 'T'} else [])
            if not values or any(not 0. < value <= self.max_accel for value in values):
                self.reject('M204 must use S or P/T within configured printer max_accel')
        elif command == 'END_PRINT':
            self.end = True
        elif command == 'M600':
            # Parameters have already been rejected by the empty allowed set.
            # This is a configuration requirement, never a request to run M03
            # while a file is being inspected.
            self.requires_filament = True

    def _temperature(self, name, value):
        lower, upper = self.limits[name]
        if value != 0. and not lower <= value <= upper:
            self.reject('%s temperature outside native heater limits' % name)
        if value < 0.:
            self.reject('negative heater target is forbidden')

    def finish(self):
        if not self.command_count:
            raise FileRejected('file contains no executable G-code')
        targets = {}
        for name in ('hotend', 'bed'):
            header, supplied = self.header.get(name), self.supplied.get(name)
            if header is not None and supplied is not None and header != supplied:
                raise FileRejected('START_PRINT and start-command temperatures disagree for ' + name)
            value = header if header is not None else supplied
            if value is None:
                raise FileRejected('explicit BED_TEMP and EXTRUDER_TEMP are required; no fallback temperatures')
            self._temperature(name, value)
            targets[name] = value
        return targets


def _open_source(root, filename):
    """Walk directory fds; no symlink can escape or substitute a path component."""
    # O_NONBLOCK prevents a FIFO/device with a .gcode suffix from hanging the
    # executor before fstat can reject it. Regular files are unaffected.
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    directory = os.open(root, flags | os.O_DIRECTORY)
    try:
        parts = filename.split('/')
        for part in parts[:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], flags, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise FileRejected('source must be a regular file')
        return os.fdopen(fd, 'rb', buffering=0), info
    except Exception:
        os.close(fd)
        raise


def _new_snapshot():
    fd, path = tempfile.mkstemp(prefix='m300_m02_', suffix='.gcode')
    os.fchmod(fd, 0o400)
    return os.fdopen(fd, 'w+b', buffering=0), path


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


def _preflight_snapshot_bytes(data, limits, supplied, max_line, max_dwell, max_accel):
    dialect = Dialect(limits, supplied, max_line, max_dwell, max_accel)
    for line in data.splitlines(keepends=True):
        if not line.endswith(b'\n'):
            raise FileRejected('non-LF line ending in compiled/text snapshot')
        dialect.feed(line)
    targets = dialect.finish()
    return dialect, targets


class JobSD:
    def __init__(self, job, config):
        self.job, self.config = job, config
        self.printer, self.gcode, self.reactor = job.printer, job.gcode, job.reactor
        self.v_sd = self.printer.load_object(config, 'virtual_sdcard')
        self.max_file_bytes = config.getint('max_file_bytes', 16 * 1024 * 1024,
                                            minval=1024, maxval=128 * 1024 * 1024)
        self.binary_zcode_qualified = getattr(job, 'binary_zcode_qualified', False)
        self.max_compiled_bytes = config.getint('max_compiled_bytes', 64 * 1024 * 1024,
                                                minval=1024, maxval=128 * 1024 * 1024)
        self.max_line_bytes = config.getint('max_line_bytes', 2048, minval=64, maxval=8192)
        self.max_dwell_ms = config.getfloat('max_dwell_ms', 1000., minval=0., maxval=1000.)
        self.max_accel = config.getsection('printer').getfloat('max_accel', above=0.)
        if not all(math.isfinite(v) for v in (self.max_dwell_ms, self.max_accel)):
            raise config.error('M300 file limits must be finite')
        self.root = os.path.realpath(self.v_sd.sdcard_dirname)
        self.installed = False
        self.is_preparing = False
        self._verifying = False
        self.selected = self.prepared = None
        self._feeder = None
        self._generation = 0
        self._session = self._started = self._paused = False
        self._pause_requested = self._eof_seen = False
        self._reported_error = False
        self._error_reason = None
        self._in_worker = self._closing = False
        self._worker_generation = None
        self._session_id = None
        self._halted = False
        self._last_context = None
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self._lifecycle_stop)

    def _error(self, message):
        return self.printer.command_error('M300 file: ' + str(message))

    def is_session_active(self):
        return self._session

    def _job_active(self):
        machine = getattr(self.job, 'machine', None)
        check = getattr(self.job, 'preparation_service_busy', None)
        service_busy = (check(self) if check is not None else
                        getattr(self.job, 'service_busy', lambda: False)())
        # FILE_ERROR may already be a terminal FSM label while root still has
        # a drain/error-clean operation pending. Do not overlap those sessions.
        return bool((machine is not None and (machine.active or machine.state == 'FAULT'))
                    or getattr(self.job, '_ops', ())
                    or getattr(self.job, '_waiting', False)
                    or getattr(self.job, '_executing', False)
                    or getattr(self.job, '_native_homing', False)
                    or service_busy
                    or getattr(self.job, '_cleanup_pending', False)
                    or getattr(self.job, '_resume_checking', False))

    def _ensure_idle(self):
        if self._halted or self.printer.is_shutdown():
            raise self._error('host restart/shutdown invalidated this adapter')
        if (self._session or self.is_preparing or self._verifying
                or self._in_worker or self._job_active()):
            raise self._error('another job or file operation is active')

    def _checkpoint(self, token, in_session=False):
        if token != self._generation or self._halted or self.printer.is_shutdown():
            raise PreparationCancelled('preparation/verification was cancelled or restarted')
        if in_session:
            if not self._session or self.prepared is None:
                raise PreparationCancelled('job session ended while verifying its snapshot')
        elif self._session or self._job_active():
            raise PreparationCancelled('job became active during file preparation')

    def _filename(self, filename):
        is_sd = isinstance(filename, str) and filename.startswith('sd:/')
        original = filename
        if is_sd:
            filename = filename[4:]
        if (not isinstance(filename, str) or not filename or len(filename.encode('utf-8')) > 1024
                or filename.startswith('/') or '\\' in filename or ':' in filename
                or any(part in ('', '.', '..') for part in filename.split('/'))
                or any(ord(char) < 32 or ord(char) == 127 for char in filename)):
            raise FileRejected('filename must be a relative path strictly inside the configured G-code root')
        suffix = os.path.splitext(filename)[1].lower()
        if suffix == '.zcode' and self.binary_zcode_qualified:
            return original
        if suffix in ('.zcode', '.zcodex', '.bin'):
            raise FileRejected('binary Z-code: binary_zcode_qualified=False or unsupported binary extension; '
                'the legacy Z-code inspector is read-only; M04 executes only the separately qualified M300 subset')
        if suffix not in EXTENSIONS:
            raise FileRejected('only .gcode, .g and .gco UTF-8 files are accepted')
        return original

    def _targets(self, gcmd):
        supplied = {}
        if gcmd is not None:
            for key, name in (('EXTRUDER_TEMP', 'hotend'), ('BED_TEMP', 'bed')):
                value = gcmd.get(key, None)
                if value is not None:
                    supplied[name] = _number(value, key)
        return supplied

    def _require_filament(self, required):
        if not required:
            return
        service = self.printer.lookup_object('m300_filament', None)
        if service is None:
            raise FileRejected('M600 requires configured m300_filament before file selection/start')
        if getattr(service, 'filament_qualified', False) is not True:
            raise FileRejected('M600 requires filament_qualified=True before file selection/start')

    def prepare(self, filename, gcmd=None):
        self._ensure_idle()
        filename = self._filename(filename)
        if filename.startswith('sd:/') or filename.lower().endswith('.zcode'):
            return self._prepare_m04(filename, gcmd)
        supplied = self._targets(gcmd)
        self._generation += 1
        token = self._generation
        self.is_preparing = True
        source = writer = raw_snapshot = textfile = result = None
        path = None
        executor = self.v_sd.executor
        try:
            heaters = self.printer.lookup_object('heaters')
            limits = {name: (heater.min_temp, heater.max_temp) for name, heater in
                      (('hotend', heaters.lookup_heater('extruder')),
                       ('bed', heaters.lookup_heater('heater_bed')))}
            dialect = Dialect(limits, supplied, self.max_line_bytes, self.max_dwell_ms, self.max_accel)
            source, before = executor.submit(_open_source, self.root, filename)
            self._checkpoint(token)
            if not 0 < before.st_size <= self.max_file_bytes:
                raise FileRejected('file size must be within 1..%d bytes' % self.max_file_bytes)
            writer, path = executor.submit(_new_snapshot)
            self._checkpoint(token)
            digest, size, partial = hashlib.sha256(), 0, b''
            while True:
                data = executor.submit(source.read, CHUNK)
                self._checkpoint(token)
                if not data:
                    break
                size += len(data)
                if size > self.max_file_bytes:
                    raise FileRejected('file grew beyond the bounded size')
                digest.update(data)
                if executor.submit(writer.write, data) != len(data):
                    raise FileRejected('incomplete snapshot write')
                self._checkpoint(token)
                lines = (partial + data).split(b'\n')
                partial = lines.pop()
                for line in lines:
                    dialect.feed(line + b'\n')
                if len(partial) > self.max_line_bytes:
                    raise FileRejected('line exceeds %d bytes' % self.max_line_bytes)
                self.reactor.pause(self.reactor.monotonic())
                self._checkpoint(token)
            if partial:
                raise FileRejected('final newline LF is required; bytes are never silently normalized')
            after = executor.submit(os.fstat, source.fileno())
            self._checkpoint(token)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if identity(before) != identity(after) or size != before.st_size:
                raise FileRejected('source changed during preparation; select it again')
            targets = dialect.finish()
            self._require_filament(dialect.requires_filament)
            raw_snapshot = executor.submit(_seal_snapshot, writer, path)
            writer, path = None, None
            self._checkpoint(token)
            wrapped = executor.wrap_obj(raw_snapshot)
            textfile = ReadOnlySnapshot(io.TextIOWrapper(io.BufferedReader(wrapped),
                                                         encoding='utf-8', newline=''),
                                        os.path.join(self.root, filename), self)
            raw_snapshot = None
            result = Prepared(self, filename, digest.hexdigest(), size, targets, textfile,
                              dialect.command_count, dialect.start, dialect.end,
                              requires_filament=dialect.requires_filament)
            textfile = None
            return result
        except (FileRejected, UnicodeError):
            raise
        except Exception as exc:
            raise FileRejected('unable to prepare file: ' + str(exc))
        finally:
            for stream in (source, writer, raw_snapshot, textfile):
                if stream is not None:
                    try:
                        if isinstance(stream, ReadOnlySnapshot):
                            stream.close()
                        else:
                            executor.submit(stream.close)
                    except Exception:
                        logging.exception('M300 snapshot cleanup')
            if path is not None:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
            self.is_preparing = False
            if result is not None:
                try:
                    self._checkpoint(token)
                    # Source close and snapshot sealing can yield. Publication
                    # must still reflect the current configured M03 capability.
                    self._require_filament(result.requires_filament)
                except Exception:
                    result.close()
                    raise

    def _require_binary(self, prepared):
        if not getattr(prepared, 'binary_source', False):
            return
        if not self.binary_zcode_qualified:
            raise FileRejected('binary_zcode_qualified=False; checked subset cannot execute')
        if getattr(prepared, 'requires_homing', False) and (
                self.job.homing_mode != 'native_contact' or not self.job.contact_homing_qualified):
            raise FileRejected('binary home prefix requires native_contact and contact_homing_qualified=True')
        move = self.job.gcode_move
        for name in ('base_position', 'homing_position'):
            values = getattr(move, name, None)
            if (values is None or len(values) < 3
                    or any(not math.isfinite(x) or abs(x) > 1.e-9 for x in values[:3])):
                raise FileRejected('binary stock coordinates require zero XYZ ' + name)
        if (not math.isclose(move.speed_factor, 1. / 60., rel_tol=0., abs_tol=1.e-12)
                or not math.isclose(move.extrude_factor, 1., rel_tol=0., abs_tol=1.e-12)):
            raise FileRejected('binary stock scales require M220 S100 and M221 S100')

    def _prepare_m04(self, filename, gcmd=None):
        """One immutable source, complete compile, independent M02 preflight.

        CPU and host file I/O run on the native executor; physical SD reads
        yield through its transport. Every such boundary checks cancellation.
        No unvalidated prefix can be passed to the live feeder.
        """
        supplied = self._targets(gcmd)
        self._generation += 1
        token = self._generation
        self.is_preparing = True
        source = writer = raw_snapshot = textfile = result = None
        path = None
        metadata = {}
        executor = self.v_sd.executor
        try:
            heaters = self.printer.lookup_object('heaters')
            limits = {name: (heater.min_temp, heater.max_temp) for name, heater in
                      (('hotend', heaters.lookup_heater('extruder')),
                       ('bed', heaters.lookup_heater('heater_bed')))}
            before = None
            if filename.startswith('sd:/'):
                card = self.printer.lookup_object('m300_sd', None)
                if card is None:
                    raise FileRejected('physical SD provider m300_sd is not configured')
                source, metadata = card.get_snapshot('/' + filename[4:], owner=self,
                    checkpoint=lambda: self._checkpoint(token))
                self._checkpoint(token)
            else:
                source, before = executor.submit(_open_source, self.root, filename)
                self._checkpoint(token)
                if not 0 < before.st_size <= self.max_file_bytes:
                    raise FileRejected('binary source exceeds bounded size')
            chunks, source_size, source_digest = [], 0, hashlib.sha256()
            while True:
                data = executor.submit(source.read, CHUNK)
                self._checkpoint(token)
                if not data:
                    break
                source_size += len(data)
                if source_size > self.max_file_bytes:
                    raise FileRejected('source exceeds bounded size')
                source_digest.update(data)
                chunks.append(data)
                self.reactor.pause(self.reactor.monotonic())
                self._checkpoint(token)
            if before is not None:
                after = executor.submit(os.fstat, source.fileno())
                self._checkpoint(token)
                identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                if identity(before) != identity(after) or source_size != before.st_size:
                    raise FileRejected('source changed during binary snapshot')
            if source_size == 0:
                raise FileRejected('empty source')
            if filename.startswith('sd:/') and (
                    metadata.get('size') != source_size
                    or metadata.get('sha256') != source_digest.hexdigest()
                    or metadata.get('readonly_snapshot') is not True):
                raise FileRejected('physical SD snapshot size/hash/read-only metadata mismatch')
            source_bytes = b''.join(chunks)
            del chunks
            binary = filename.lower().endswith('.zcode')
            requires_homing = False
            if binary:
                if not self.binary_zcode_qualified:
                    raise FileRejected('binary_zcode_qualified=False')
                from .m300_binary import compile_m300
                compiled = executor.submit(compile_m300, source_bytes,
                    heater_limits=limits, axis_limits=self.job._axis_bounds(),
                    max_bytes=self.max_file_bytes, max_output_bytes=self.max_compiled_bytes)
                self._checkpoint(token)
                data = compiled.gcode
                requires_homing = compiled.requires_homing
                metadata = dict(metadata, **compiled.metadata)
            else:
                data = source_bytes
            metadata.update(source_bytes=source_size, source_sha256=source_digest.hexdigest(),
                            source_kind='physical_sd' if filename.startswith('sd:/') else 'host')
            if not 0 < len(data) <= self.max_compiled_bytes or not data.endswith(b'\n'):
                raise FileRejected('compiled/text snapshot size or final LF invalid')
            dialect, targets = executor.submit(_preflight_snapshot_bytes, data, limits,
                supplied, self.max_line_bytes, self.max_dwell_ms, self.max_accel)
            self._checkpoint(token)
            self._require_filament(dialect.requires_filament)
            writer, path = executor.submit(_new_snapshot)
            self._checkpoint(token)
            for start in range(0, len(data), CHUNK):
                part = data[start:start+CHUNK]
                if executor.submit(writer.write, part) != len(part):
                    raise FileRejected('incomplete compiled snapshot write')
                self._checkpoint(token)
            raw_snapshot = executor.submit(_seal_snapshot, writer, path)
            writer, path = None, None
            self._checkpoint(token)
            wrapped = executor.wrap_obj(raw_snapshot)
            textfile = ReadOnlySnapshot(io.TextIOWrapper(io.BufferedReader(wrapped),
                encoding='utf-8', newline=''), filename, self)
            raw_snapshot = None
            result = Prepared(self, filename, hashlib.sha256(data).hexdigest(), len(data),
                targets, textfile, dialect.command_count, dialect.start, dialect.end,
                requires_filament=dialect.requires_filament)
            textfile = None
            result.binary_source = binary
            result.requires_homing = requires_homing
            result.source_metadata = metadata
            return result
        except (FileRejected, UnicodeError):
            raise
        except Exception as exc:
            raise FileRejected('M04 preflight failed: ' + str(exc))
        finally:
            for stream in (source, writer, raw_snapshot, textfile):
                if stream is not None:
                    try:
                        if isinstance(stream, ReadOnlySnapshot):
                            stream.close()
                        else:
                            executor.submit(stream.close)
                    except Exception:
                        logging.exception('M300 M04 snapshot cleanup')
            if path is not None:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
            self.is_preparing = False
            if result is not None:
                try:
                    self._checkpoint(token)
                    self._require_filament(result.requires_filament)
                    if result.binary_source and not self.binary_zcode_qualified:
                        raise PreparationCancelled('binary qualification changed while preparing')
                except Exception:
                    result.close()
                    raise

    def select(self, filename, gcmd=None):
        self._ensure_idle()
        old, self.selected = self.selected, None
        token = self._generation
        self._reported_error = False
        self._error_reason = None
        try:
            if old is not None:
                old.close()
            self._checkpoint(token)
            self.selected = self.prepare(filename, gcmd)
        except PreparationCancelled as exc:
            raise self._error(str(exc))
        except Exception as exc:
            self._dispatch_error('preflight: ' + str(exc))
            raise self._error(str(exc))
        if gcmd is not None:
            gcmd.respond_info('M300 file selected: %s sha256=%s bytes=%d; no heating or motion' %
                             (self.selected.filename, self.selected.sha256, self.selected.size))
        return self.selected

    def start_file(self, gcmd):
        filename = gcmd.get('FILENAME', None)
        if filename is not None:
            self.select(filename, gcmd)
        return self.start_selected(gcmd)

    def start_selected(self, gcmd=None):
        self._ensure_idle()
        prepared = self.selected
        if prepared is None or prepared.closed:
            raise self._error('select a fully checked file first (M23 or FILENAME=)')
        supplied = self._targets(gcmd)
        if any(prepared.targets[name] != value for name, value in supplied.items()):
            raise self._error('start-command targets disagree with the selected immutable snapshot')
        try:
            self._require_filament(prepared.requires_filament)
            self._require_binary(prepared)
        except FileRejected as exc:
            # Selection may predate a configuration/lifecycle change. Reject
            # before transferring ownership or invoking any heating callback.
            raise self._error(str(exc))
        self.selected = None
        self.prepared = prepared
        self._session = True
        self._started = self._paused = self._pause_requested = self._eof_seen = False
        self._error_reason = None
        self._reported_error = False
        self._session_id = uuid.uuid4().hex
        token = self._generation
        try:
            self.job.start_prepared(prepared, gcmd)
        except Exception:
            if token == self._generation and self._session and self.prepared is prepared:
                self.cancel()
            raise
        if (token != self._generation or not self._session
                or self.prepared is not prepared or prepared.closed):
            raise self._error('start was cancelled or restarted during authorization')
        self.v_sd.print_stats.set_current_file(prepared.filename)
        return prepared

    def begin(self, prepared):
        if (not self.installed or not self._session or self.prepared is not prepared
                or prepared._owner is not self or prepared.closed or self._started):
            raise self._error('begin requires the accepted, unopened M02 session snapshot')
        if self.v_sd.work_timer is not None or self.v_sd.current_file is not None:
            raise self._error('native virtual SD is not empty before begin')
        token = self._generation
        try:
            prepared.textfile.seek(0)
        except Exception:
            # seek is an executor operation and may return after CANCEL closed
            # the old reader. Preserve lifecycle cancellation as a distinct
            # result, so it cannot be escalated into a new hardware fault.
            self._checkpoint(token, in_session=True)
            raise
        self._checkpoint(token, in_session=True)
        if self.prepared is not prepared or prepared.closed:
            raise self._error('begin snapshot changed during seek')
        self._require_binary(prepared)
        self._feeder = FeederSnapshot(self, prepared.textfile)
        self.v_sd.current_file = self._feeder
        self.v_sd.file_position = self.v_sd.next_file_position = 0
        self.v_sd.file_size = prepared.size
        self.v_sd.print_stats.set_current_file(prepared.filename)
        self._started = True
        self._orig_resume()

    def pause(self):
        if not self._session or not self._started or self._eof_seen:
            raise self._error('pause requires a feeding snapshot')
        self._pause_requested = True
        self._orig_pause()
        self._paused = True

    def resume(self):
        if (not self._session or not self._paused or self._eof_seen
                or self.prepared is None or self.prepared.closed
                or self.v_sd.current_file is not self._feeder):
            raise self._error('resume requires the intact paused M02 snapshot')
        self._pause_requested = self._paused = False
        self._orig_resume()

    def get_context(self):
        if self.prepared is None or not self._session:
            return None
        position = (self.v_sd.next_file_position if self.v_sd.cmd_from_sd
                    else self.v_sd.file_position)
        return {'filename': self.prepared.filename, 'sha256': self.prepared.sha256,
                'size': self.prepared.size, 'position': position,
                'next_position': self.v_sd.next_file_position,
                'snapshot_id': self.prepared.identity, 'session_id': self._session_id}

    def verify_resume(self, context, full=True):
        if self._verifying:
            raise self._error('snapshot verification already in progress')
        if (not isinstance(context, dict) or not self._session or not self._paused
                or self._eof_seen or self.prepared is None or self.prepared.closed
                or self.v_sd.work_timer is not None
                or self.v_sd.current_file is not self._feeder):
            raise self._error('resume snapshot is not paused/intact')
        current = self.get_context()
        if context != current or not 0 <= current['position'] <= current['size']:
            raise self._error('resume identity/cursor belongs to another or modified job')
        if not full:
            return True
        prepared, token = self.prepared, self._generation
        stream, digest, count = prepared.textfile, hashlib.sha256(), 0
        self._verifying = True
        try:
            # tell may itself submit to the native I/O executor. Acquire the
            # verification lock before the first possible cooperative yield.
            saved = stream.tell()
            self._checkpoint(token, in_session=True)
            try:
                stream.seek(0)
                while True:
                    text = stream.read(CHUNK)
                    self._checkpoint(token, in_session=True)
                    if not text:
                        break
                    data = text.encode('utf-8')
                    digest.update(data)
                    count += len(data)
                    if count > prepared.size:
                        raise FileRejected('snapshot size changed')
                    self.reactor.pause(self.reactor.monotonic())
                    self._checkpoint(token, in_session=True)
                if count != prepared.size or digest.hexdigest() != prepared.sha256:
                    raise FileRejected('snapshot digest changed')
            finally:
                # Do not revive an invalidated file or touch a new session's
                # reader. The old read may have yielded while CANCEL closed it.
                if token == self._generation and not stream.closed:
                    stream.seek(saved)
            self._checkpoint(token, in_session=True)
            if context != self.get_context():
                raise FileRejected('resume cursor changed during snapshot verification')
        except PreparationCancelled:
            raise
        except Exception as exc:
            if token != self._generation or self._halted or self.printer.is_shutdown():
                raise PreparationCancelled('resume verification cancelled by lifecycle change') from exc
            raise self._error('resume verification failed: ' + str(exc))
        finally:
            self._verifying = False
        return True

    def _close_files(self):
        self._generation += 1
        self._closing = True
        try:
            self._last_context = self.get_context()
            # do_pause() can yield and is forbidden during Klippy shutdown.
            # Invalidate first; the native worker observes this stop flag at
            # its next boundary. Keep its cursor until it exits, otherwise a
            # cancellation inside G1 makes upstream seek a detached reader.
            self.v_sd.must_pause_work = True
            native = self.v_sd.current_file
            for stream in (native, self.prepared, self.selected):
                if stream is not None:
                    stream.close()
            self.prepared = self.selected = None
            self._feeder = None
            self._session = self._started = self._paused = False
            self._pause_requested = True
            if not self._in_worker:
                self._detach_native()
        finally:
            self._closing = False

    def _detach_native(self):
        timer = self.v_sd.work_timer
        if timer is not None:
            self.reactor.unregister_timer(timer)
        self.v_sd.work_timer = self.v_sd.current_file = None
        self.v_sd.file_position = self.v_sd.next_file_position = self.v_sd.file_size = 0
        self.v_sd.cmd_from_sd = False

    def cancel(self):
        had_session = self._session
        self._close_files()
        if self.installed and had_session and self._error_reason is None:
            self._orig_note_cancel()
            self.v_sd.print_stats.state = 'cancelled'
            self.v_sd.print_stats.error_message = ''

    def error(self, reason):
        self._error_reason = str(reason)
        self._close_files()
        if self.installed:
            self._orig_note_error(self._error_reason)
            # Native _note_finish returns early when printing never started or
            # already ended. M02 still records a preflight/file error honestly.
            self.v_sd.print_stats.state = 'error'
            self.v_sd.print_stats.error_message = self._error_reason

    def complete(self):
        if not self._session or not self._eof_seen or self._error_reason:
            raise self._error('completion requires checked EOF and no error')
        self._orig_note_complete()
        self._close_files()

    def _lifecycle_stop(self, *args):
        self._halted = True
        self._error_reason = 'host lifecycle invalidated file session'
        self._close_files()

    def _dispatch_error(self, reason):
        if self._reported_error:
            return
        self._reported_error = True
        self._error_reason = str(reason)
        try:
            self.job.file_error(str(reason))
        finally:
            if self._session or self.selected is not None or self.is_preparing:
                self.error(str(reason))

    def _active_worker(self):
        return self._in_worker and self._session and self._worker_generation == self._generation

    def _note_start(self):
        if self._active_worker():
            self._orig_note_start()

    def _note_pause(self):
        if self._active_worker():
            self._orig_note_pause()

    def _note_error(self, message):
        if self._active_worker():
            self._error_reason = str(message)
            self._orig_note_error(str(message))

    def _note_complete(self):
        # Native completion is only an EOF candidate. Old/stale workers can
        # never manufacture completion after cancellation or a new generation.
        if self._active_worker():
            self._native_complete = True

    def _work_handler(self, eventtime):
        if (not self._session or not self._started or self.prepared is None
                or self.v_sd.current_file is not self._feeder):
            self.v_sd.work_timer = None
            return self.reactor.NEVER
        token = self._generation
        self._in_worker, self._worker_generation = True, token
        self._native_complete = False
        failure = None
        try:
            result = self._orig_worker(eventtime)
        except Exception as exc:
            failure = 'native file worker exception: ' + str(exc)
            self.v_sd.work_timer = None
            self.v_sd.cmd_from_sd = False
            result = self.reactor.NEVER
        finally:
            self._in_worker = False
        if token != self._generation or not self._session:
            self._detach_native()
            return result
        if failure or self._error_reason:
            self._dispatch_error(failure or self._error_reason)
        elif (self._native_complete and self.v_sd.current_file is None
              and self.v_sd.file_position == self.prepared.size
              and not self.v_sd.cmd_from_sd and self.v_sd.work_timer is None):
            if self._pause_requested:
                # Pause has priority over the coincident EOF. No bytes remain,
                # but the intact reader is retained for normal RESUME checks.
                self.v_sd.current_file = self._feeder
                self.v_sd.next_file_position = self.v_sd.file_position
                self._paused = True
                self._orig_note_pause()
            elif not self._eof_seen:
                self._eof_seen = True
                try:
                    self.job.file_eof()
                except Exception as exc:
                    self._dispatch_error('job EOF callback failed: ' + str(exc))
        elif self._pause_requested and self.v_sd.current_file is self._feeder:
            self._paused = True
        else:
            self._dispatch_error('native feeder stopped without checked EOF or requested pause')
        return result

    def _blocked_resume(self):
        raise self._error('direct virtual_sdcard.do_resume bypass is forbidden; use the M02 lifecycle')

    def _native_pause(self):
        if self._closing:
            return self._orig_pause()
        return self.job.pause('native virtual_sdcard pause')

    def _native_cancel(self):
        return self.job.cancel('native virtual_sdcard cancel')

    def _blocked_seek(self, *args, **kwargs):
        raise self._error('M26/direct seek is forbidden; select a checked file from its beginning')

    def _blocked_load(self, *args, **kwargs):
        raise self._error('direct native file loading bypass is forbidden')

    def _reset(self):
        self._ensure_idle()
        if self.selected is not None:
            self.selected.close()
            self.selected = None
        self._generation += 1
        self._orig_reset()

    def cmd_M23(self, gcmd):
        self.select(gcmd.get_raw_command_parameters().strip(), gcmd)

    def cmd_M24(self, gcmd):
        if self._session:
            return self.job.resume()
        return self.start_selected(gcmd)

    def cmd_M25(self, gcmd):
        return self.job.pause('M25')

    def cmd_SDCARD_PRINT_FILE(self, gcmd):
        return self.start_file(gcmd)

    def cmd_SDCARD_RESET_FILE(self, gcmd):
        if self.v_sd.cmd_from_sd:
            raise self._error('SDCARD_RESET_FILE from a job is forbidden')
        self._reset()

    def install(self):
        if self.installed:
            return
        if self.v_sd.current_file is not None or self.v_sd.work_timer is not None:
            raise self.config.error('M300 job must install before any native file is opened')
        self._orig_resume, self._orig_pause = self.v_sd.do_resume, self.v_sd.do_pause
        self._orig_worker, self._orig_reset = self.v_sd.work_handler, self.v_sd._reset_file
        stats = self.v_sd.print_stats
        for name in ('start', 'pause', 'error', 'complete', 'cancel'):
            setattr(self, '_orig_note_' + name, getattr(stats, 'note_' + name))
        for name in ('start', 'pause', 'error', 'complete'):
            setattr(stats, 'note_' + name, getattr(self, '_note_' + name))
        self.v_sd.do_resume, self.v_sd.do_pause = self._blocked_resume, self._native_pause
        self.v_sd.do_cancel = self._native_cancel
        self.v_sd.work_handler, self.v_sd._load_file = self._work_handler, self._blocked_load
        self.v_sd._reset_file, self.v_sd.set_file_position = self._reset, self._blocked_seek
        handlers = {'M23': self.cmd_M23, 'M24': self.cmd_M24, 'M25': self.cmd_M25,
                    'M26': self._blocked_seek, 'SDCARD_PRINT_FILE': self.cmd_SDCARD_PRINT_FILE,
                    'SDCARD_RESET_FILE': self.cmd_SDCARD_RESET_FILE}
        for name, handler in handlers.items():
            if self.gcode.register_command(name, None) is None:
                raise self.config.error('M300 requires native virtual_sdcard command ' + name)
            self.gcode.register_command(name, handler)
            setattr(self.v_sd, 'cmd_' + name, handler)
        # A compiled binary job assumes one fixed coordinate/scaling frame.
        # Native SD holds the G-code mutex while cmd_from_sd is true. External
        # commands can still cancel/pause or turn heaters off, but cannot alter
        # this frame or inject a different trajectory during that session.
        for name in ('G0', 'G1', 'G28', 'G90', 'G91', 'G92', 'M82', 'M83',
                     'M220', 'M221', 'SET_GCODE_OFFSET', 'RESTORE_GCODE_STATE',
                     'SET_KINEMATIC_POSITION', 'FORCE_MOVE', 'MANUAL_STEPPER'):
            original = self.gcode.register_command(name, None)
            if original is not None:
                def guarded(gcmd, original=original, name=name):
                    native_home = False
                    if name == 'G28':
                        permit = getattr(self.job, '_home_command_permit', None)
                        if (permit is not None and getattr(self.job, '_native_homing', False)
                                and permit[0] == self.job.machine.token
                                and self.job.machine.state == 'HOMING'
                                and gcmd.get_command_parameters() == {'G': '28', permit[1]: ''}):
                            # Consume before original G28 can yield. A concurrent
                            # external G28 cannot borrow the same authorization.
                            self.job._home_command_permit = None
                            native_home = True
                    if (self._session and getattr(self.prepared, 'binary_source', False)
                            and not native_home
                            and not (self._active_worker() and self.v_sd.cmd_from_sd)):
                        raise self._error('binary job owns coordinate frame and trajectory')
                    return original(gcmd)
                self.gcode.register_command(name, guarded)
        self.installed = True
