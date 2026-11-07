# SPDX-License-Identifier: GPL-3.0-or-later
"""One error identity for native Klipper, Fluidd, OLED and MCU metadata.

This observer never changes a heater, motor, ARM state or shutdown latch.
HF_IN_SHUTDOWN commands only annotate the MCU's independently safe screen.
"""
from collections import deque
import json
import logging
import os

from .m300_error_codes import (CATALOG, CODES, KINDS, NONE, SHUTDOWN, GUARD,
                               classify, clean, descriptor, identity)

REVISION = '0.13.16.27-SD-NOTICE'
STATE_FORMAT = ('m300_error_state code=%hu kind=%c fatal=%c source=%c'
                ' native_id=%hu revision=%u')


class M300Errors:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.mcu = self.printer.lookup_object(config.get('mcu', 'mcu'))
        self.current = None
        self.history = deque(maxlen=32)
        self.epoch = os.urandom(8).hex()
        self.sequence = 0
        self.mcu_state = {}
        self.abi = 0
        self.connected = self.live = False
        self._set_cmd = self._query_cmd = None
        self._publishing = False
        self._publish_pending = False
        self._presented_id = None
        self._last_wire = None
        self._oled_notice = self._oled_meta = None
        self.mcu.register_config_callback(self._build_config)
        self.gcode.register_output_handler(self._output)
        self.printer.register_event_handler('klippy:ready', self._ready)
        self.printer.register_event_handler('klippy:analyze_shutdown', self._shutdown)
        self.printer.register_event_handler('klippy:disconnect', self._disconnect)
        self.printer.register_event_handler('gcode:request_restart', self._restart)
        for name, callback in (('ZORTRAX_ERROR_STATUS', self.cmd_status),
                               ('ZORTRAX_ERROR_SHOW', self.cmd_show),
                               ('ZORTRAX_ERROR_ACK', self.cmd_ack)):
            self.gcode.register_command(name, callback, when_not_ready=True)

    def _build_config(self):
        self.abi = int(self.mcu.get_constants().get('M300_ERROR_ABI', 0))
        if self.abi != 1:
            return  # Older firmware retains host diagnostics, without MCU detail.
        self._set_cmd = self.mcu.lookup_command('m300_error_set code=%hu kind=%c fatal=%c')
        self._query_cmd = self.mcu.lookup_command('m300_error_query')
        self.mcu.register_serial_response(self._mcu_response, STATE_FORMAT)
        self.connected = True

    def _ready(self):
        self.connected = self.live = True
        if self._query_cmd is not None:
            self._query_cmd.send([])

    def _restart(self, *args):
        self.live = False

    def _disconnect(self, *args):
        self.connected = self.live = False
        self._last_wire = None

    def _output(self, line):
        if not self._publishing and line.startswith('!! '):
            if self.current and clean(line[3:]) == self.current['reason']:
                return  # Typed owner diagnosis wins over text classification.
            self.record(line[3:], source='gcode')

    def _shutdown(self, message, details):
        # Klippy calls this after native shutdown handlers, with the original
        # MCU/verify_heater cause. Do not replace it with guard consequence 255.
        self.live = False
        reason = details.get('reason') or message
        self.record(reason, source='klipper_shutdown', fatal=True)
        if self._query_cmd is not None and self.connected:
            self._query_cmd.send([])

    def _mcu_response(self, params):
        data = {k: int(v) for k, v in params.items() if not k.startswith('#')}
        def deliver(now):
            self.mcu_state = data
            if not data.get('fatal'):
                return
            code, kind = data.get('code', 0), data.get('kind', SHUTDOWN)
            if code not in CODES and code != 0 or kind not in KINDS:
                return
            # Generic native shutdown is only a consequence when the host
            # already knows the exact verify_heater failure.
            if self.current and self.current['fatal'] and not code and kind in (SHUTDOWN, GUARD):
                return
            if (self.current and self.current['fatal'] and code == self.current['code']
                    and (code or kind == self.current['kind'])):
                return  # Retain the original native reason, not just its title.
            self.record(descriptor(code, kind)['title'], code=code, kind=kind,
                        source='mcu_local', fatal=True, sync=False)
        self.reactor.register_async_callback(deliver)

    def record(self, reason, *, source, code=None, kind=NONE, fatal=False, sync=True):
        reason = clean(reason)
        if code is None:
            found = classify(reason, source, fatal)
            if found is None:
                return None
            code, kind = found
        if type(code) is not int or code not in CODES and code != 0 or kind not in KINDS:
            raise ValueError('Unknown M300 error identity')
        informational = code == 101 and not fatal
        old = self.current
        if informational and old and old.get('severity', 'error') != 'info':
            return old  # An empty catalogue must never replace an actual fault.
        if old and old['fatal']:
            if not fatal:
                return old
            old_specific = bool(old['code'] or old['kind'] not in (SHUTDOWN, GUARD))
            new_specific = bool(code or kind not in (SHUTDOWN, GUARD))
            if not new_specific:
                return old  # A lifecycle consequence cannot replace the root.
            if old_specific and (source != 'mcu_local' or not new_specific):
                return old
        pad = self.printer.lookup_object('m300_pad_mesh', None)
        context = {}
        if (not fatal and pad is not None and getattr(pad, 'run_id', None)
                and (pad.busy or source == 'm300_pad_mesh')):
            context = dict(surface='pad_mesh', run_id=pad.run_id)
        if old and (old['code'], old['kind'], old['reason'], old['fatal']) == (
                code, kind, reason, bool(fatal)) and all(old.get(k) == context.get(k) for k in ('surface','run_id')):
            return old
        self.sequence += 1
        meta = descriptor(code, kind, fatal=fatal)
        self.current = dict(code=code, kind=kind, fatal=bool(fatal), source=source,
                            reason=reason, id='%s-%d' % (self.epoch, self.sequence),
                            timestamp=self.reactor.monotonic(), state='NOTICE' if informational else 'FAULT',
                            severity='info' if informational else 'error',
                            title=meta['title'], action=meta['action'],
                            icon='activity:' + meta['icon'])
        self.current['label'] = identity(self.current)
        if context:
            # Keep the typed root cause and error identity. Fluidd owns one
            # result panel for the whole mesh run, including nested homing.
            self.current.update(context)
        self.history.append(dict(self.current))
        log = logging.info if informational else logging.error
        log('M300_%s %s', 'NOTICE' if informational else 'ERROR', json.dumps(self.current, sort_keys=True))
        if sync:
            self._sync(code, kind, fatal)
        if not self._publish_pending:
            self._publish_pending = True
            self.reactor.register_callback(self._publish)
        return self.current

    def _sync(self, code, kind, fatal):
        wire = (code, kind, int(bool(fatal)))
        if self._set_cmd is None or not self.connected or wire == self._last_wire:
            return
        try:
            self._set_cmd.send(list(wire))  # Metadata only; valid after shutdown.
            self._last_wire = wire
        except Exception:
            logging.exception('M300 error detail could not reach MCU; local diagnosis retained')

    def _publish(self, now):
        self._publish_pending = False
        if self.current is not None:
            self.show(automatic=True)

    def show(self, code=None, *, automatic=False):
        record = self.current if code is None else dict(code=code, kind=NONE, fatal=False)
        if record is None:
            if not automatic:
                self.gcode.respond_info('M300: no active error')
            return
        if automatic and code is None and record['id'] == self._presented_id:
            return  # Owner changes and the queued observer publish one notice.
        meta = descriptor(record['code'], record['kind'], fatal=record['fatal'])
        label = identity(record)
        if code is None and record.get('surface') == 'pad_mesh':
            record['view_revision'] = record.get('view_revision', 0) + 1
        logging.info('M300_ERROR_VIEW %s', json.dumps(dict(code=record['code'],
            kind=record['kind'], label=label, title=meta['title'], action=meta['action'],
            catalogue=code is not None), sort_keys=True))
        self._publishing = True
        try:
            emit = lambda text: self.gcode.respond_raw('// action:' + text)
            emit('prompt_end')
            if code is not None or record.get('surface') != 'pad_mesh':
                emit('prompt_begin ZORTRAX M300 - ' + label)
                emit('prompt_text ' + meta['title'])
                if record.get('reason'):
                    emit('prompt_text Cause: ' + clean(record['reason']))
                emit('prompt_text ' + meta['action'])
                if code is not None:
                    emit('prompt_text Catalogue entry; no fault has been triggered.')
                    emit('prompt_text Detection: ' + meta['detection'])
                elif record['fatal']:
                    emit('prompt_text Safety latch remains active. Fix the cause before FIRMWARE_RESTART.')
                else:
                    emit('prompt_footer_button Acknowledge|ZORTRAX_ERROR_ACK ID=%s|primary' % record['id'])
                if (self.live and not record['fatal']
                        and self.printer.lookup_object('m300_settings', None) is not None):
                    target = 'error_catalog' if code is not None else 'errors'
                    emit('prompt_footer_button Back|ZORTRAX_UI_SHOW PAGE=%s|info' % target)
                emit('prompt_show')
            if code is None:
                self._presented_id = record['id']
            oled = self.printer.lookup_object('m300_oled', None)
            if self.live and oled is not None and oled.connected:
                # Existing notice navigation preserves the previous page;
                # dismissing it cannot clear a safety latch or resume a job.
                oled.message = (label, meta['oled'] + '. ' + '. '.join(filter(None, meta['hint'])))
                self._oled_notice, self._oled_meta = oled.message, meta
                oled.render_at = 0.
                oled._user_refresh_pending = True
                self.reactor.update_timer(oled.timer, self.reactor.NOW)
        finally:
            self._publishing = False

    def render_notice(self, title, message, frame_type, sprite):
        if (title, message) != self._oled_notice:
            return None
        from .m300_settings_ui import menu_frame
        meta = self._oled_meta
        return menu_frame(('Back', title, meta['oled'], *meta['hint']), (), 0, frame_type, sprite)

    def acknowledge(self, token):
        if self.current is None or token != self.current['id']:
            raise self.printer.command_error('Expired error notice; refresh before acknowledging')
        if self.current['fatal'] or self.printer.is_shutdown():
            raise self.printer.command_error('Safety latch remains active; fix the cause, then FIRMWARE_RESTART')
        self.current = None
        self._oled_notice = self._oled_meta = None
        self._sync(0, NONE, False)
        self.gcode.respond_raw('// action:prompt_end')
        oled = self.printer.lookup_object('m300_oled', None)
        if oled is not None and oled.connected:
            oled.message = None
            oled.render_at = 0.

    def rows(self, page):
        back = [('Back', ('page', 'help' if page == 'errors' else 'errors'))]
        if page == 'error_catalog':
            return 'OEM error codes', back + [('#%03d %s' % (code, item['oled']),
                ('native_gcode', 'ZORTRAX_ERROR_SHOW CODE=%d' % code)) for code, item in CODES.items()]
        rows = back + [('Code catalogue', ('page', 'error_catalog'))]
        if self.current is None:
            rows.append(('No active error', None))
        else:
            rows.append((self.current['label'], ('native_gcode', 'ZORTRAX_ERROR_SHOW')))
            if not self.current['fatal']:
                rows.append(('Acknowledge notice', ('native_gcode',
                             'ZORTRAX_ERROR_ACK ID=' + self.current['id'])))
            rows.append((self.current['title'], None))
        return 'Errors', rows

    def get_status(self, now):
        return dict(revision=REVISION, state=self.current.get('state', 'FAULT') if self.current else 'IDLE', busy=False,
                    current=dict(self.current) if self.current else None,
                    history=list(self.history), mcu=dict(self.mcu_state), mcu_abi=self.abi,
                    mcu_upgrade_required=self.abi != 1, catalogue_size=len(CODES),
                    automatic_fault_clear=False, automatic_resume=False)

    def cmd_status(self, gcmd):
        if self._query_cmd is not None and self.connected:
            self._query_cmd.send([])
        gcmd.respond_info('M300_ERRORS ' + json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))

    def cmd_show(self, gcmd):
        code = gcmd.get_int('CODE', None)
        if code is not None and code not in CODES:
            raise gcmd.error('Unknown OEM error code')
        self.show(code)

    def cmd_ack(self, gcmd):
        self.acknowledge(gcmd.get('ID'))


def load_config(config):
    return M300Errors(config)
