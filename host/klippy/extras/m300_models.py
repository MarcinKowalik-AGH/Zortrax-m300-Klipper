# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare Models files once, then give the read-only stream to native Klippy."""
from dataclasses import dataclass
import hashlib
import io
import json
import logging
import math
import os
import re
import secrets
import stat
from typing import Optional

from .m300_binary import compile_m300, DEFAULT_MAX_BYTES
from .m300_job_sd import ReadOnlySnapshot, _open_source, _new_snapshot, _seal_snapshot
from .m300_maintenance import other_service
from .m300_native_service import lock_command, require_idle_print
from .m300_runtime import deposited

MAX_LINE = 64 * 1024
ORCA_HEADER_BYTES = 256 * 1024
ORCA_PROFILE_START = re.compile(
    rb'^; M300 Classic / native Klipper\r?\nG90\r?\nM83\r?\n'
    rb'M140 S(?P<bed>[0-9]{1,3})\r?\n'
    rb'(?P<wait>M190 S(?P=bed)\r?\n|'
    rb'TEMPERATURE_WAIT SENSOR=heater_bed MINIMUM=(?P<minimum>[0-9]{1,3})\r?\n)'
    rb'(?P<nozzle>M104 S180\r?\n)G28\r?\n'
    rb'M109 S[0-9]{1,3}\r?\nG90\r?\nM83\r?\nG92 E0\r?\n',
    re.MULTILINE)
PEERS = ('m300_job', 'm300_filament', 'm300_calibration', 'm300_maintenance',
         'm300_motion', 'm300_fans', 'm300_thermal', 'm300_nvm')


class ModelError(ValueError):
    pass


@dataclass(frozen=True)
class Preview:
    source: str
    filename: str
    source_sha256: str
    size: int
    stream: ReadOnlySnapshot
    targets: dict
    binary: bool
    virtual_name: Optional[str] = None

    @property
    def native_filename(self):
        return self.virtual_name or self.filename


def _file_identity(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _copy_text(stream, target, max_bytes):
    """Validate native text framing without restricting the user's slicer macros."""
    digest = hashlib.sha256()
    size = 0
    has_command = False
    while line := stream.readline(MAX_LINE + 1):
        size += len(line)
        if size > max_bytes or len(line) > MAX_LINE:
            raise ModelError('G-code file or line exceeds the configured limit')
        # Keep CRLF byte offsets, matching the native worker's text wrapper.
        payload = line.removesuffix(b'\n').removesuffix(b'\r')
        if (b'\r' in payload or b'\x00' in payload
                or any(ch < 32 and ch != 9 or ch == 127 for ch in payload)):
            raise ModelError('invalid control byte in G-code')
        decoded = payload.decode('utf-8')
        if size == len(line) and decoded.startswith('\ufeff'):
            raise ModelError('save G-code as UTF-8 without a byte order mark')
        has_command |= bool(payload.split(b';', 1)[0].strip())
        digest.update(line)
        # Klippy's worker dispatches LF-terminated lines. Preserve a last
        # command even if the source was saved without the final newline.
        output = line if line.endswith(b'\n') else line + b'\n'
        if target.write(output) != len(output):
            raise ModelError('incomplete local G-code snapshot write')
    if not has_command:
        raise ModelError('G-code file contains no commands')
    return digest.hexdigest(), size


def _parallel_orca_preheat(snapshot):
    """Move the supplied Orca M300 profile's 180 C command before its bed wait."""
    snapshot.seek(0)
    header = snapshot.read(ORCA_HEADER_BYTES)
    match = ORCA_PROFILE_START.search(header)
    if match is None:
        return
    # Only slicer metadata can precede this startup block. Unknown macros
    # may have their own thermal sequencing.
    for line in header[:match.start()].splitlines():
        command = line.split(b';', 1)[0].split(None, 1)
        if command and command[0] not in (b'M73', b'SET_PRINT_STATS_INFO', b'EXCLUDE_OBJECT_DEFINE'):
            return
    bed = int(match['bed'])
    minimum = match['minimum']
    if (minimum is None and bed <= 35
            or minimum is not None and not (0 < bed <= 35 and int(minimum) == bed - 1)):
        return
    # The source file, digest and total byte count stay intact. Replay uses
    # the same immutable execution snapshot as the first print.
    reordered = match['nozzle'] + match['wait']
    snapshot.seek(match.start('wait'))
    if snapshot.write(reordered) != len(reordered):
        raise ModelError('incomplete parallel preheat snapshot write')


def _build_snapshot(root, entry, physical, metadata, max_bytes, limits):
    """Disk I/O and conversion only. Runs in the virtual SD executor."""
    opened, before = (physical, None) if physical is not None else _open_source(root, entry.path)
    writer = temporary = None
    try:
        with io.BufferedReader(opened) as source_file:
            if before is not None and (before.st_size != entry.size or before.st_mtime != entry.mtime):
                raise ModelError('host file changed; reopen the directory')
            if not 0 < entry.size <= max_bytes:
                raise ModelError('model file is empty or exceeds the configured size limit')
            binary = limits is not None
            targets = {}
            writer, temporary = _new_snapshot()
            if binary:
                source = source_file.read(max_bytes + 1)
                if len(source) > max_bytes:
                    raise ModelError('Z-code exceeds the configured size limit')
                source_digest, source_size = hashlib.sha256(source).hexdigest(), len(source)
                heaters, axes = limits
                result = compile_m300(source, heater_limits=heaters, axis_limits=axes,
                                      max_bytes=max_bytes, max_records=250_000,
                                      max_output_bytes=16 * 1024 * 1024, native=True)
                targets = result.targets
                if writer.write(result.gcode) != len(result.gcode):
                    raise ModelError('incomplete converted G-code snapshot write')
            else:
                source_digest, source_size = _copy_text(source_file, writer, max_bytes)
            if before is not None and _file_identity(before) != _file_identity(os.fstat(opened.fileno())):
                raise ModelError('host file changed during import')
            if source_size != entry.size or (metadata is not None and
                    (metadata.get('readonly_snapshot') is not True
                     or metadata.get('size') != source_size
                     or metadata.get('sha256') != source_digest)):
                raise ModelError('source size or SD snapshot identity changed')
            size = writer.tell()
            if not binary:
                _parallel_orca_preheat(writer)
        raw = _seal_snapshot(writer, temporary)
        writer = temporary = None
        return raw, size, source_digest, targets
    finally:
        if writer is not None:
            writer.close()
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _copy_open_native_file(fd, size):
    """Keep the bytes Klippy opened, without moving its source file offset."""
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_size != size:
        raise ModelError('native source size changed')
    writer, temporary = _new_snapshot()
    try:
        digest = hashlib.sha256()
        position = 0
        while position < size:
            data = os.pread(fd, min(65536, size - position), position)
            if not data or writer.write(data) != len(data):
                raise ModelError('incomplete native source snapshot')
            digest.update(data)
            position += len(data)
        if _file_identity(os.fstat(fd)) != _file_identity(before):
            raise ModelError('native source changed while making the snapshot')
        _parallel_orca_preheat(writer)
        raw = _seal_snapshot(writer, temporary)
        writer = temporary = None
        return raw, digest.hexdigest()
    finally:
        if writer is not None:
            writer.close()
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


class NativeModelStream(ReadOnlySnapshot):
    """Hold a verified EOF stream for replay until the job is cleared."""
    def __init__(self, stream, name, owner):
        super().__init__(stream, name, owner)
        self.begin()

    def begin(self):
        self.eligible = True
        self.expected_seek = 0
        self.eof = self.retained = False

    def fileno(self):
        # Protected native pauses verify this same read-only execution file,
        # including imports/reprint snapshots, without reopening its pathname.
        return self._io('fileno')

    def read(self, size=-1):
        result = super().read(size)
        if size > 0 and not result:
            self.eof = True
        return result

    def seek(self, offset, whence=0):
        if whence != 0 or offset != self.expected_seek:
            self.eligible = False
        self.expected_seek = None
        self.eof = False
        return super().seek(offset, whence)

    def close(self):
        owner = self._owner
        active = owner.active
        sd = owner.v_sd
        if (active is not None and active.stream is self and self.eligible
                and self.eof and sd.file_position == active.size
                and not sd.must_pause_work and owner.ready
                and not owner.printer.is_shutdown()):
            # Native EOF closes the active file immediately before publishing
            # print_stats.complete. Keep the descriptor for that transition.
            self.retained = True
            return
        if active is not None and active.stream is self:
            owner.active = None
        super().close()

    def release(self):
        self.retained = self.eligible = False
        super().close()

    def _io(self, operation, *args):
        try:
            return super()._io(operation, *args)
        except (OSError, UnicodeError) as exc:
            from .m300_error_codes import report
            report(self._owner.printer, exc, source='native_model_read', code=4, fatal=True)
            if not self._owner.printer.is_shutdown():
                self._owner.printer.invoke_async_shutdown('M300 local model snapshot read failed')
            raise


class M300Models:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.job = self.printer.load_object(config, 'm300_job')
        self.v_sd = self.printer.load_object(config, 'virtual_sdcard')
        self.executor = self.v_sd.executor
        self.max_gcode_bytes = config.getint('max_gcode_bytes', 16 * 1024 * 1024,
                                             minval=1024, maxval=128 * 1024 * 1024)
        self.max_zcode_bytes = config.getint('max_zcode_bytes', 8 * 1024 * 1024,
                                             minval=1024, maxval=DEFAULT_MAX_BYTES)
        self.ready = False
        self.operation = self.token = self.preview = None
        self.filename = self.source = self.error = None
        self.runtime = None
        self.runtime_started = self.runtime_deposited = self.runtime_ended = False
        self.active = self.completed = self.completed_token = None
        self.native_load = self.native_print = None
        self.printer.register_event_handler('klippy:ready', self._ready)
        self.printer.register_event_handler('virtual_sdcard:reset_file', self._reset_print)
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self.invalidate)
        self.gcode.register_command('ZORTRAX_MODELS_STATUS', self.cmd_status, when_not_ready=True)
        self.gcode.register_command('ZORTRAX_MODELS_START', self.cmd_start)
        self.gcode.register_command('ZORTRAX_MODELS_CANCEL_IMPORT', self.cmd_cancel)

    def _ready(self):
        self.ready = True
        if (not self.job.board.native_control or self.native_load is not None
                or not hasattr(self.v_sd, '_load_file')):
            return
        self.native_load = self.v_sd._load_file
        self.v_sd._load_file = self._load_native_model
        stats = self.v_sd.print_stats
        self.runtime = self.printer.lookup_object('m300_nvm', None)
        native_start = stats.note_start
        native_complete, native_pause = stats.note_complete, stats.note_pause
        native_error = getattr(stats, 'note_error', None)
        native_cancel = stats.note_cancel

        def start():
            native_start()
            self.runtime_started = True
            if self.runtime_deposited and not self.runtime_ended:
                self.runtime.runtime_start(self.reactor.monotonic())

        def complete():
            was_printing = stats.state == 'printing'
            native_complete()
            self._record_complete()
            if self.runtime is None:
                return
            self.runtime.runtime_pause(self.reactor.monotonic())
            sd = self.v_sd
            if (self.runtime_started and was_printing and stats.state == 'complete'
                    and sd.current_file is None and sd.work_timer is None
                    and not sd.must_pause_work and sd.file_position == sd.file_size):
                self.runtime.runtime_complete()
            self.runtime_started = False

        def pause():
            native_pause()
            if self.runtime is not None:
                self.runtime.runtime_pause(self.reactor.monotonic())
            active = self.active
            if active is not None and self.v_sd.current_file is active.stream:
                active.stream.expected_seek = self.v_sd.file_position

        stats.note_complete, stats.note_pause = complete, pause
        if self.runtime is not None:
            stats.note_start = start
            self._watch_deposition()
            self._watch_heater_waits(stats)

            def cancelled():
                self.runtime.runtime_pause(self.reactor.monotonic())
                self.runtime_started = False
                native_cancel()
            stats.note_cancel = cancelled
        if native_error is not None:
            def failed(message):
                native_error(message)
                if self.runtime is not None:
                    self.runtime.runtime_pause(self.reactor.monotonic())
                    self.runtime_started = False
                if stats.state == 'error':
                    from .m300_error_codes import report
                    report(self.printer, message, source='native_print',
                           fatal=self.printer.is_shutdown())
            stats.note_error = failed
        record = lock_command(self.gcode, 'SDCARD_PRINT_FILE', self._dispatch_print)
        if record is not None:
            self.native_print = record[1]

    def _watch_deposition(self):
        move = self.printer.lookup_object('gcode_move', None)
        if move is None:
            return
        # Observe native dispatch rather than interpreting a slicer's E mode,
        # extrusion factor or arcs independently of Klipper's parser.
        for name in ('G0', 'G1', 'G2', 'G3'):
            previous = self.gcode.ready_gcode_handlers.get(name)
            if previous is None:
                continue

            def watch(gcmd, previous=previous):
                if (not self.ready or not self.runtime_started or self.runtime_deposited
                        or self.runtime_ended or not self.v_sd.cmd_from_sd):
                    return previous(gcmd)
                before = tuple(move.last_position[:4])
                now = self.reactor.monotonic()
                result = previous(gcmd)
                if (self.ready and not self.printer.is_shutdown()
                        and self.runtime_started and not self.runtime_ended
                        and deposited(before, move.last_position[:4])):
                    self.runtime_deposited = True
                    self.runtime.runtime_start(now)
                return result

            lock_command(self.gcode, name, watch)

    def _watch_heater_waits(self, stats):
        for name in ('M109', 'M190', 'TEMPERATURE_WAIT'):
            previous = self.gcode.ready_gcode_handlers.get(name)
            if previous is None:
                continue

            def wait(gcmd, previous=previous):
                if (not self.runtime_started or not self.runtime_deposited
                        or self.runtime_ended or not self.v_sd.cmd_from_sd):
                    return previous(gcmd)
                self.runtime.runtime_pause(self.reactor.monotonic())
                result = previous(gcmd)
                if (self.ready and not self.printer.is_shutdown()
                        and stats.state == 'printing' and not self.v_sd.must_pause_work):
                    self.runtime.runtime_start(self.reactor.monotonic())
                return result

            lock_command(self.gcode, name, wait)

    def runtime_end(self):
        if self.runtime_started:
            self.runtime_ended = True
            now = self.reactor.monotonic()
            self.runtime.runtime_pause(now)
            self.runtime.runtime_drained(now)

    def _load_native_model(self, gcmd, filename, check_subdirs=False):
        # The native loader resolves the exact file, retains standard filename
        # reporting and initializes print statistics. Take a bounded immutable
        # copy of that descriptor before native do_resume can start the worker.
        self.native_load(gcmd, filename, check_subdirs=check_subdirs)
        sd = self.v_sd
        source, size = sd.current_file, sd.file_size
        if source is None or not 0 < size <= self.max_gcode_bytes:
            return
        raw = None
        try:
            fd = source.fileno()
            if sd.current_file is not source:
                raise gcmd.error('native file selection changed before snapshot')
            raw, digest = self.executor.submit(_copy_open_native_file, fd, size)
            if sd.current_file is not source:
                raise gcmd.error('native file selection changed during snapshot')
            self._live()
            stream = self._snapshot_stream(raw, source.name)
            raw = None
        except (ModelError, OSError, UnicodeError) as exc:
            if not self.ready or self.printer.is_shutdown() or sd.current_file is not source:
                raise gcmd.error('native file selection expired') from exc
            logging.info('M300 cannot retain this native job for reprint: %s', exc)
            return
        finally:
            if raw is not None:
                self.executor.submit(raw.close)
        self.active = Preview('host', sd.print_stats.filename, digest, size, stream, {}, False)
        sd.current_file = stream
        try:
            source.close()
        except OSError:
            logging.exception('M300 native source close')
        if not self.ready or self.printer.is_shutdown() or sd.current_file is not stream:
            raise gcmd.error('native file selection expired')

    def _dispatch_print(self, gcmd):
        filename = gcmd.get('FILENAME')
        physical = filename.removeprefix('/')
        if not physical.startswith('sd:/'):
            return self.native_print(gcmd)
        # This name is reserved for a physical SD job recorded by Models.
        # Stock Fluidd's Reprint passes the name, not an M300 token.
        completed = self.completed
        if (self.v_sd.cmd_from_sd or completed is None
                or completed.source != 'sd' or completed.virtual_name != physical):
            raise gcmd.error('No matching completed SD snapshot. Select the model again.')
        try:
            self.reprint(self.completed_token)
        except ModelError as exc:
            raise gcmd.error(str(exc)) from exc

    def _reset_print(self, *args):
        if self.runtime is not None:
            self.runtime.runtime_pause(self.reactor.monotonic())
        self.runtime_started = self.runtime_deposited = self.runtime_ended = False
        active, completed = self.active, self.completed
        self.active = self.completed = self.completed_token = None
        for model in (active, completed):
            if model is not None:
                model.stream.release()

    def _record_complete(self):
        model, self.active = self.active, None
        if model is None:
            return
        sd = self.v_sd
        if (self.ready and not self.printer.is_shutdown()
                and sd.print_stats.state == 'complete' and sd.print_stats.filename == model.native_filename
                and sd.current_file is None and sd.work_timer is None
                and sd.file_position == model.size and model.stream.retained):
            self.completed = model
            self.completed_token = secrets.token_hex(16)
        else:
            model.stream.release()

    def _reprint_available(self, now):
        model = self.completed
        sd = self.v_sd
        if (model is None or self.operation is not None or self.preview is not None
                or model.stream.closed or not self.ready or self.printer.is_shutdown()
                or sd.current_file is not None or sd.work_timer is not None
                or sd.print_stats.state != 'complete' or sd.print_stats.filename != model.native_filename):
            return False
        toolhead = self.printer.lookup_object('toolhead')
        queued, estimated, empty = toolhead.check_busy(now)
        return empty and queued <= estimated

    def reprint_status(self, now):
        available = self._reprint_available(now)
        return dict(available=available, token=self.completed_token if available else None,
                    filename=self.completed.filename if self.completed else None)

    def reprint(self, token):
        self._idle()
        sd = self.v_sd
        if (getattr(sd, 'cmd_from_sd', False) or token is None
                or token != self.completed_token or not self._reprint_available(self.reactor.monotonic())):
            raise ModelError('No completed model is ready to reprint')
        model = self.completed
        self._check_frame(model)
        # The native reset invalidates any prior selection. Detach the one
        # consumed token first, and close its stream if attaching fails.
        self.completed = self.completed_token = None
        try:
            sd._reset_file()
            self._idle()
            self._attach(model)
        except Exception:
            model.stream.release()
            raise
        return model.filename

    def _discard(self):
        self.token = None
        preview, self.preview = self.preview, None
        if preview is not None:
            preview.stream.close()

    def invalidate(self, *args):
        self.ready = False
        self._discard()
        self._reset_print()

    def _live(self):
        if (not self.ready or self.printer.is_shutdown()
                or not self.job.board.native_control):
            raise ModelError('Models requires a ready native M300 host')

    def _idle(self):
        self._live()
        require_idle_print(self.printer, self.reactor.monotonic())
        pause = self.printer.lookup_object('pause_resume', None)
        if (self.v_sd.current_file is not None or self.v_sd.work_timer is not None
                or (pause is not None and pause.is_paused)):
            raise ModelError('native print or selected file already owns virtual SD')
        blocker = other_service(self.printer, PEERS + ('m300_sd',), self.reactor.monotonic())
        if blocker is not None:
            raise ModelError('Models blocked by ' + blocker)

    def _limits(self):
        heaters = self.printer.lookup_object('heaters')
        hotend = heaters.lookup_heater('extruder')
        bed = heaters.lookup_heater('heater_bed')
        return ({'hotend': (max(hotend.min_temp, hotend.min_extrude_temp),
                            min(hotend.max_temp, 300.)),
                 'bed': (bed.min_temp, min(bed.max_temp, 130.))}, self.job._axis_bounds())

    def _snapshot_stream(self, raw, name):
        wrapped = self.executor.wrap_obj(raw)
        reader = io.TextIOWrapper(io.BufferedReader(wrapped), encoding='utf-8', newline='')
        return NativeModelStream(reader, name, self)

    def prepare(self, source, entry, cid, checkpoint):
        self._idle()
        if self.operation is not None:
            raise ModelError('another model import is in progress')
        if source not in ('host', 'sd') or entry.is_dir:
            raise ModelError('choose a G-code or Z-code file')
        binary = entry.path.lower().endswith('.zcode')
        max_bytes = self.max_zcode_bytes if binary else self.max_gcode_bytes
        if not 0 < entry.size <= max_bytes:
            raise ModelError('model file is empty or exceeds the configured size limit')
        card = self.printer.lookup_object('m300_sd', None) if source == 'sd' else None
        if source == 'sd' and (card is None or not cid or not entry.fingerprint):
            raise ModelError('SD listing expired; reopen the SD directory')
        old, self.preview = self.preview, None
        self.error = None
        token = self.token = self.operation = secrets.token_hex(16)
        self.filename, self.source = entry.path, source

        def check():
            self._live()
            if token != self.token:
                raise ModelError('model import cancelled')
            checkpoint()

        def run(eventtime):
            physical = raw = stream = None
            try:
                if old is not None:
                    old.stream.close()
                check()
                self._idle()
                limits = self._limits() if binary else None
                metadata = None
                if card is not None:
                    expected = dict(cid=cid, fingerprint=entry.fingerprint, size=entry.size)
                    physical, metadata = card.get_snapshot('/' + entry.path,
                                                           checkpoint=check, expected=expected)
                check()
                raw, size, digest, targets = self.executor.submit(
                    _build_snapshot, self.v_sd.sdcard_dirname, entry, physical,
                    metadata, max_bytes, limits)
                physical = None  # Worker closed the source.
                check()
                self._idle()
                display_name = ('sd:/' if source == 'sd' else '') + entry.path
                stream = self._snapshot_stream(raw, display_name)
                raw = None
                # Stable for this snapshot and its repeats. A stale Fluidd
                # history item for the same card pathname cannot select new bytes.
                virtual_name = 'sd:/%s/%s' % (token, entry.path) if source == 'sd' else None
                self.preview = Preview(source, display_name, digest, size, stream, targets, binary,
                                       virtual_name)
                stream = None
            except Exception as exc:
                if token == self.token:
                    self.error = str(exc)
                    logging.info('M300 model import refused: %s', self.error)
                    from .m300_error_codes import report
                    report(self.printer, exc, source='m300_models')
            finally:
                for leftover in (stream, raw, physical):
                    if leftover is not None and not leftover.closed:
                        try:
                            self.executor.submit(leftover.close)
                        except Exception:
                            logging.exception('M300 model snapshot cleanup')
                self.operation = None
        self.reactor.register_callback(run)
        return self.get_status(self.reactor.monotonic())

    def cancel(self, token):
        if not self.token or token != self.token:
            raise ModelError('model selection expired')
        self.error = None
        self._discard()

    def start(self, token):
        # Called under the native G-code mutex. The transfer and timer setup
        # do not yield; no file paths or user strings are parsed as commands.
        self._idle()
        preview = self.preview
        if (not self.token or token != self.token or self.operation is not None
                or preview is None or preview.stream.closed):
            raise ModelError('choose a fully prepared model first')
        self._check_frame(preview)
        self.v_sd._reset_file()
        self._idle()
        if self.preview is not preview or self.token != token:
            raise ModelError('model selection changed before start')
        self.preview = self.token = None
        self._attach(preview)
        return preview.filename

    def _check_frame(self, preview):
        if preview.binary:
            move = self.printer.lookup_object('gcode_move')
            for values in (move.base_position, move.homing_position):
                if any(not math.isfinite(x) or abs(x) > 1.e-9 for x in values[:3]):
                    raise ModelError('M300 Z-code requires zero XYZ G-code offsets')

    def _attach(self, model):
        sd = self.v_sd
        model.stream.begin()
        self.active = model
        sd.current_file = model.stream
        sd.file_position = sd.next_file_position = 0
        sd.file_size = model.size
        try:
            sd.print_stats.set_current_file(model.native_filename)
            sd.do_resume()
        except Exception:
            sd._reset_file()
            raise

    def get_status(self, now):
        preview = self.preview
        card = self.printer.lookup_object('m300_sd', None) if self.source == 'sd' else None
        if self.operation:
            state = 'IMPORTING' if self.token else 'CANCELLING'
        elif preview:
            state = 'READY'
        else:
            state = 'ERROR' if self.error else 'IDLE'
        return dict(ready=self.ready, state=state, busy=self.operation is not None,
                    token=self.token, filename=self.filename, source=self.source, error=self.error,
                    counter_error=self.runtime.runtime_error if self.runtime is not None else None,
                    bytes_copied=getattr(card, 'bytes_copied', 0) if self.operation else 0,
                    format=('Z-code' if preview.binary else 'G-code') if preview else None,
                    source_sha256=preview.source_sha256 if preview else None,
                    gcode_bytes=preview.size if preview else None,
                    targets=dict(preview.targets) if preview else {})

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_MODELS ' + json.dumps(self.get_status(self.reactor.monotonic()),
                                                    sort_keys=True))

    def cmd_start(self, gcmd):
        try:
            filename = self.start(gcmd.get('TOKEN'))
        except ModelError as exc:
            raise gcmd.error(str(exc))
        gcmd.respond_info('Started model through native Klipper: ' + filename)

    def cmd_cancel(self, gcmd):
        try:
            self.cancel(gcmd.get('TOKEN'))
        except ModelError as exc:
            raise gcmd.error(str(exc))
        self.cmd_status(gcmd)


def load_config(config):
    return M300Models(config)
