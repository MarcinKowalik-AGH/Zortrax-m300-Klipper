# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare Models files once, then give the read-only stream to native Klippy."""
from dataclasses import dataclass
import hashlib
import io
import json
import logging
import math
import os
import secrets

from .m300_binary import compile_m300, DEFAULT_MAX_BYTES
from .m300_job_sd import ReadOnlySnapshot, _open_source, _new_snapshot, _seal_snapshot
from .m300_maintenance import other_service
from .m300_native_service import require_idle_print

MAX_LINE = 64 * 1024
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


class NativeModelStream(ReadOnlySnapshot):
    """The native worker catches read errors internally. Escalate storage loss."""
    def _io(self, operation, *args):
        try:
            return super()._io(operation, *args)
        except (OSError, UnicodeError):
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
        self.printer.register_event_handler('klippy:ready', self._ready)
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self.invalidate)
        self.gcode.register_command('ZORTRAX_MODELS_STATUS', self.cmd_status, when_not_ready=True)
        self.gcode.register_command('ZORTRAX_MODELS_START', self.cmd_start)
        self.gcode.register_command('ZORTRAX_MODELS_CANCEL_IMPORT', self.cmd_cancel)

    def _ready(self):
        self.ready = True

    def _discard(self):
        self.token = None
        preview, self.preview = self.preview, None
        if preview is not None:
            preview.stream.close()

    def invalidate(self, *args):
        self.ready = False
        self._discard()

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
                wrapped = self.executor.wrap_obj(raw)
                reader = io.TextIOWrapper(io.BufferedReader(wrapped), encoding='utf-8', newline='')
                stream = NativeModelStream(reader, display_name, self)
                raw = None
                self.preview = Preview(source, display_name, digest, size, stream, targets, binary)
                stream = None
            except Exception as exc:
                if token == self.token:
                    self.error = str(exc)
                    logging.info('M300 model import refused: %s', self.error)
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
        if preview.binary:
            move = self.printer.lookup_object('gcode_move')
            for values in (move.base_position, move.homing_position):
                if any(not math.isfinite(x) or abs(x) > 1.e-9 for x in values[:3]):
                    raise ModelError('M300 Z-code requires zero XYZ G-code offsets')
        sd = self.v_sd
        sd._reset_file()
        self._idle()
        if self.preview is not preview or self.token != token:
            raise ModelError('model selection changed before start')
        sd.current_file = preview.stream
        sd.file_position = sd.next_file_position = 0
        sd.file_size = preview.size
        self.preview = self.token = None
        try:
            sd.print_stats.set_current_file(preview.filename)
            sd.do_resume()
        except Exception:
            sd._reset_file()
            raise
        return preview.filename

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
