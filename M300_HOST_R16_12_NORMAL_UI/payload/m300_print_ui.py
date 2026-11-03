# SPDX-License-Identifier: GPL-3.0-or-later
"""Contextual OLED views of the native print and pause_resume owners."""
from collections import deque
from functools import lru_cache
import logging

from .m300_leveling_oem import draw_text, width
from .m300_print_hold import PrintHold
from .m300_ui_m11_state import clean_label

COMMANDS = {'pause': 'PAUSE', 'resume': 'RESUME', 'change': 'ZORTRAX_CHANGE',
            'stop': 'CANCEL_PRINT'}
PAUSE_ROWS = (('Resume the print', 'resume'), ('Change the material', 'change'),
              ('Stop the print', 'ask_stop'))
STOP_ROWS = (('No', 'keep'), ('Yes, stop the print', 'stop'))


@lru_cache(maxsize=48)
def frame_for(frame_type, title, lines, selected):
    frame = frame_type()
    draw_text(frame, (256 - width(title)) // 2, 1, title)
    for index, line in enumerate(lines):
        # The stock font has variable-width glyphs. Reserve room for the cursor.
        while width(line) > 230:
            line = line[:-1]
        y = 17 + 12 * index
        if index == selected:
            for dy in range(-2, 3):
                frame.pixel(6 + 3 - abs(dy), y + 7 + dy)
        draw_text(frame, 16, y, line)
    return frame.wire_bytes()


class M300PrintUI:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.sd = self.printer.load_object(config, 'virtual_sdcard')
        self.hold = PrintHold()
        self.frames = deque(maxlen=12)
        self.epoch = 0
        self.ready = False
        self.selected = 0
        self.last_key = self.dismissed = self.pending = self.error = self.confirm_stop = None
        self.printer.register_event_handler('klippy:ready', self._ready)
        self.printer.register_event_handler('virtual_sdcard:reset_file', self._new_file)
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self._stop)
        self.gcode.register_command('ZORTRAX_REPRINT_SHOW', self.cmd_show)
        self.gcode.register_command('ZORTRAX_REPRINT_CONFIRM', self.cmd_reprint)

    def _ready(self):
        self.ready = True

    def _new_file(self, *args):
        self.epoch += 1
        self.frames.clear()
        self.confirm_stop = None

    def _stop(self, *args):
        self.ready = False
        self._new_file()
        self.hold.reset()

    def _drained(self, now):
        toolhead = self.printer.lookup_object('toolhead', None)
        if toolhead is None:
            return False
        print_time, estimated, empty = toolhead.check_busy(now)
        return empty and print_time <= estimated

    def view(self, now, *, include_dismissed=False):
        if not self.ready or self.printer.is_shutdown():
            return None
        stats = self.sd.print_stats
        state = stats.state
        filename = stats.filename
        if not filename:
            return None
        if state in ('printing', 'paused') and self.sd.current_file is not None:
            filament = self.printer.lookup_object('m300_filament', None)
            if filament is not None and filament.machine.active:
                return None  # The existing procedure presenter owns Change.
            pause = self.printer.lookup_object('pause_resume', None)
            if state == 'paused':
                phase = ('PAUSED' if pause is not None and pause.is_paused
                         and pause.sd_paused and self.sd.work_timer is None else 'SD_PAUSED')
            else:
                phase = 'PRINTING'
            name = getattr(self.sd.current_file, 'name', filename)
            file_key = (id(self.sd.current_file), getattr(stats, 'last_pause_time', None)
                        if state == 'paused' else None)
            identity = self.epoch, name, file_key
            if phase == 'PAUSED' and self.confirm_stop == identity:
                phase = 'STOP_CONFIRM'
            elif phase != 'PAUSED':
                self.confirm_stop = None
            return ((self.epoch, phase, name, identity[-1]), None)
        if state == 'complete' and self.sd.current_file is None and self.sd.work_timer is None:
            phase = 'DONE' if self._drained(now) else 'DRAINING'
            models = self.printer.lookup_object('m300_models', None)
            replay = models.reprint_status(now) if phase == 'DONE' and models else {}
            token = replay.get('token') if replay.get('available') else None
            key = (self.epoch, phase, replay.get('filename') or filename, token)
            if include_dismissed or self.dismissed != self.epoch:
                return (key, token)
        return None

    def render(self, now, panel_context, frame_type, *, show_status):
        view = self.view(now)
        if view is None:
            self.frames.clear()
            return None
        key, token = view
        if self.last_key != key:
            self.frames.clear()
            self.selected = 0
            self.error = None
            self.last_key = key
            if key[1] == 'PRINTING':
                show_status()
        _, phase, filename, _ = key
        if phase == 'PRINTING':
            return None
        filename = clean_label(filename, 96)
        rows = ()
        selected = -1
        if phase == 'PAUSED':
            title = 'PAUSE MENU'
            rows = PAUSE_ROWS
            selected = self.selected
            lines = tuple(label for label, _ in rows)
        elif phase == 'STOP_CONFIRM':
            title = 'STOP THE PRINT?'
            rows = STOP_ROWS
            selected = self.selected
            lines = tuple(label for label, _ in rows)
        elif phase == 'SD_PAUSED':
            title = 'PRINT PAUSED'
            lines = (filename, 'Waiting for native pause' if self.pending else 'Native SD pause: M24 to resume')
        elif phase == 'DRAINING':
            title = 'PRINTING'
            lines = (filename, 'Finishing queued moves')
        else:
            title = 'PRINTING DONE'
            lines = ('Remove the model',
                     'Hold knob 10 s to reprint' if token else 'Reprint unavailable',
                     'Press to close')
        if self.error:
            lines = (*lines[:3], clean_label(self.error, 80))
        wire = frame_for(frame_type, title, lines, selected)
        self._remember_frame((wire, panel_context, key, rows, selected))
        return wire

    def present_status(self, wire, panel_context):
        key = self.last_key
        if key is not None and key[1] == 'PRINTING':
            self._remember_frame((wire, panel_context, key, (), -1))

    def _remember_frame(self, receipt):
        if not self.frames or self.frames[-1] != receipt:
            self.frames.append(receipt)

    def receipt(self, stream, panel_context):
        if not stream.ready or not stream.enabled:
            return None
        previous = getattr(stream, 'previous', None)
        return next((item for item in reversed(self.frames)
                     if item[0] == previous and item[1] == panel_context), None)

    def panel(self, events, received_at, now, receipt, guard, *, reverse=False,
              printing_status=False):
        view = self.view(now)
        key, token = view if view else (None, None)
        verified = (receipt is not None and receipt[2] == key and guard())
        phase = key[1] if key else None
        status_hold = phase == 'PRINTING' and printing_status
        wants_hold = status_hold or phase == 'DONE' and token is not None
        consumed, fired = self.hold.update(events, received_at, now,
                                          receipt[1:3] if verified else None,
                                          active=wants_hold, allow_short=status_hold)
        if fired:
            self._schedule('pause' if phase == 'PRINTING' else 'reprint', key, guard)
        if phase is None or phase == 'PRINTING':
            return consumed
        if verified and events is not None:
            if (phase == 'DONE' and not events['pressed'] and events['shorts'] == 1
                    and events['releases'] == 1 and not events['delta']):
                self.dismissed = self.epoch
            if phase in ('PAUSED', 'STOP_CONFIRM') and not consumed:
                rows = receipt[3]
                if events['delta']:
                    delta = -events['delta'] if reverse else events['delta']
                    self.selected = max(0, min(len(rows) - 1, self.selected + delta))
                elif events['shorts'] and receipt[4] == self.selected:
                    action = rows[self.selected][1]
                    if action == 'ask_stop':
                        self.confirm_stop = key[0], key[2], key[3]
                    elif action == 'keep':
                        self.confirm_stop = None
                    else:
                        self._schedule(action, key, guard)
        return True

    def _schedule(self, action, key, guard):
        if self.pending is not None:
            return
        self.pending = key
        def run(eventtime):
            try:
                with self.gcode.get_mutex():
                    view = self.view(self.reactor.monotonic())
                    if not guard() or view is None or view[0] != key:
                        return
                    if action == 'reprint':
                        self.printer.lookup_object('m300_models').reprint(view[1])
                    else:
                        self.gcode.run_script_from_command(COMMANDS[action])
            except Exception as exc:
                self.error = str(exc)
                logging.info('M300 contextual print action refused: %s', exc)
            finally:
                self.pending = None
        self.reactor.register_callback(run)

    def cmd_show(self, gcmd):
        view = self.view(self.reactor.monotonic(), include_dismissed=True)
        if view is None or view[0][1] != 'DONE' or not view[1]:
            raise gcmd.error('No drained completed print is available for exact reprint')
        title = clean_label(view[0][2], 96).replace('|', '/')
        token = view[1]
        gcmd.respond_raw('// action:prompt_end')
        gcmd.respond_raw('// action:prompt_begin Printing done')
        gcmd.respond_raw('// action:prompt_text Remove the model')
        gcmd.respond_raw('// action:prompt_text ' + title)
        gcmd.respond_raw('// action:prompt_button Reprint|ZORTRAX_REPRINT_CONFIRM TOKEN=' + token + '|primary')
        gcmd.respond_raw('// action:prompt_footer_button Back|RESPOND TYPE=command MSG=action:prompt_end')
        gcmd.respond_raw('// action:prompt_show')

    def cmd_reprint(self, gcmd):
        models = self.printer.lookup_object('m300_models', None)
        if models is None or not self._drained(self.reactor.monotonic()):
            raise gcmd.error('No drained completed model is available')
        try:
            models.reprint(gcmd.get('TOKEN'))
        except ValueError as exc:
            raise gcmd.error(str(exc))
        gcmd.respond_raw('// action:prompt_end')


def load_config(config):
    return M300PrintUI(config)
