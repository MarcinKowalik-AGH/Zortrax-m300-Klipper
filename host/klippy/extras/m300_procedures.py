# SPDX-License-Identifier: GPL-3.0-or-later
"""One operator view for M03/M07/M08; existing services own every operation.

No movement, thermal control, saved continuation or automatic resume lives
here. A Fluidd button carries the identity of the phase actually presented.
"""
import hashlib
import json
import math
import os

from .m300_material_ui_state import MESSAGES
from .m300_leveling_ui import format_view

OWNERS = ('m300_filament', 'm300_calibration', 'm300_thermal', 'm300_fans', 'm300_job')
TERMINAL = ('COMPLETE', 'CANCELLED', 'FAULT', 'ERROR')
VERBS = ('CONFIRM', 'PURGE', 'PAUSE', 'RESUME', 'CONFIRM_CLEAN', 'CANCEL')


def clean(value, limit=160):
    # Prompt protocol separators and newlines cannot originate in file names.
    return ' '.join(str(value or '').replace('|', '/').split())[:limit]


def number(value):
    return (float(value) if type(value) in (float, int)
            and math.isfinite(value) else None)


class M300Procedures:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.live = False
        self.epoch = os.urandom(16).hex()
        self.revision = 0
        self.identity = self.view_id = self.consumed = None
        self.changes = {}
        self.last_keys = {}
        self.started = {}
        self.last_prompt = None
        self.last_display = self.previous_display = None
        self.timer = self.reactor.register_timer(self._tick)
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self.invalidate)
        self.printer.register_event_handler('klippy:ready', self._ready)
        for name, callback in (
                ('ZORTRAX_PROCEDURE_STATUS', self.cmd_status),
                ('ZORTRAX_PROCEDURE_SHOW', self.cmd_show),
                ('ZORTRAX_PROCEDURE_ACTION', self.cmd_action),
                ('ZORTRAX_PROCEDURE_START', self.cmd_start)):
            self.gcode.register_command(name, callback,
                                        when_not_ready=name.endswith('STATUS'))

    def _ready(self):
        self.live = True
        self.reactor.update_timer(self.timer, self.reactor.NOW)

    def invalidate(self, *args):
        self.live = False
        self.epoch = os.urandom(16).hex()
        self.identity = self.view_id = self.consumed = self.last_prompt = None
        self.changes.clear()
        self.last_keys.clear()
        self.started.clear()
        self._release_display()
        self._emit('prompt_end')
        self.reactor.update_timer(self.timer, self.reactor.NEVER)

    def _emit(self, line):
        # Native respond_raw bypasses a second G-code parse. This is the
        # documented Fluidd prompt protocol, not executable owner commands.
        self.gcode.respond_raw('// action:' + line)

    def _release_display(self):
        display = self.printer.lookup_object('display_status', None)
        if display is not None and self.last_display is not None:
            if display.message == self.last_display:
                display.message = self.previous_display
        self.last_display = self.previous_display = None

    def _read(self, name, now):
        service = self.printer.lookup_object(name, None)
        if service is None:
            return {'state': 'UNAVAILABLE', 'busy': False, 'ready': False}
        try:
            status = service.get_status(now)
            if not isinstance(status, dict) or not isinstance(status.get('state'), str):
                raise ValueError('invalid owner status')
            return dict(status)
        except Exception as exc:
            return {'state': 'UNAVAILABLE', 'busy': False, 'ready': False,
                    'reason': clean(exc)}

    @staticmethod
    def _key(name, status):
        return (name, str(status.get('session_token')), status.get('phase_id'),
                status['state'], status.get('resume_phase'), status.get('operation'),
                tuple(status.get('can_' + v.lower()) is True for v in VERBS),
                status.get('can_confirm_resume_clean') is True,
                status.get('ready') is True)

    def view(self, now):
        snapshots = {name: self._read(name, now) for name in OWNERS}
        for name, status in snapshots.items():
            key = self._key(name, status)
            old = self.last_keys.get(name)
            if key != old:
                self.changes[name] = now
                self.last_keys[name] = key
            token = status.get('session_token')
            if old is None or str(token) != old[1]:
                self.started[name] = now
        # A filament change temporarily owns presentation above its paused
        # parent print. Completing it never resumes that parent.
        active = [n for n in OWNERS if snapshots[n].get('busy') is True
                  and snapshots[n]['state'] not in TERMINAL]
        terminal = [n for n in OWNERS if snapshots[n]['state'] in TERMINAL
                    and snapshots[n].get('session_token') not in (None, 0, '')]
        recent = max(terminal, key=lambda n: self.changes[n], default=None)
        if recent and now - self.changes[recent] < 8. and (
                not active or self.changes[recent] > max(self.changes[n] for n in active)):
            owner = recent
        else:
            owner = active[0] if active else recent
        status = snapshots[owner] if owner else {'state': 'IDLE', 'busy': False}
        identity = self._key(owner, status)
        if identity != self.identity:
            self.identity = identity
            self.revision += 1
            self.view_id = hashlib.sha256((self.epoch + ':' + str(self.revision)).encode()).hexdigest()[:24]
            self.consumed = None
        actions = []
        valid_token = (type(status.get('session_token')) in (int, str)
                       and status.get('session_token') not in (0, ''))
        ready = self.live and status.get('ready') is True and valid_token
        if ready and self.consumed != self.view_id:
            if owner == 'm300_job':
                actions = [a for a in ('PAUSE', 'RESUME', 'CANCEL')
                           if status.get('can_' + a.lower()) is True]
                if status.get('can_confirm_resume_clean') is True:
                    actions.insert(0, 'CONFIRM_CLEAN')
            elif owner and type(status.get('phase_id')) is int and status['phase_id'] >= 0:
                actions = [a for a in ('CONFIRM', 'PURGE', 'CANCEL')
                           if status.get('can_' + a.lower()) is True
                           and (a != 'PURGE' or owner == 'm300_filament')]
        state = status['state']
        title = ('Filament ' + str(status.get('operation') or '') if owner == 'm300_filament'
                 else 'Platform leveling' if owner == 'm300_calibration'
                 else 'Fan test ' + str(status.get('channel') or '') if owner == 'm300_fans'
                 else 'Thermal ' + str(status.get('heater') or '') if owner == 'm300_thermal'
                 else 'Print' if owner == 'm300_job' else 'ZORTRAX M300')
        message = (MESSAGES.get(state, state) if owner == 'm300_filament'
                   else state.replace('_', ' ').title())
        if owner == 'm300_job' and status.get('can_confirm_resume_clean') is True:
            message = 'Clean nozzle, then confirm'
        stats = self._read('print_stats', now)
        elapsed = (number(stats.get('print_duration')) if owner == 'm300_job' else
                   max(0., now - self.started.get(owner, now)))
        progress = number(status.get('progress')) if owner == 'm300_job' else None
        return {'owner': owner, 'state': state, 'title': clean(title),
                'message': clean(message), 'view_id': self.view_id,
                'token': status.get('session_token'), 'phase': status.get('phase_id'),
                'actions': actions, 'busy': status.get('busy') is True,
                'reason': clean(status.get('reason') or status.get('resume_block_reason')),
                'progress': None if progress is None else max(0., min(1., progress)),
                'elapsed': elapsed, 'phase_remaining': number(status.get('phase_remaining')),
                'filename': clean(status.get('filename')),
                'completed_mm': number(status.get('completed_mm')),
                'target_hotend': number(status.get('target_hotend', status.get('target'))),
                'target_bed': number(status.get('target_bed')),
                'snapshots': snapshots}

    def rows(self, now):
        view = self.view(now)
        rows = [('Back', ('page', 'main')), (view['title'] + ': ' + view['state'], None)]
        if view['owner'] == 'm300_calibration':
            # Present the screw and turns before navigation buttons/session
            # metadata, so the physical panel immediately shows the instruction.
            rows.extend((label, None) for label, action in format_view(
                view['snapshots'][view['owner']], (view['token'], view['phase']))
                if action is None)
        else:
            rows.append((view['message'], None))
        for action in view['actions']:
            rows.append((self._action_label(view, action),
                         ('procedure_action', view['view_id'], action)))
        rows.append(('Session: %s / Phase: %s' % (view['token'], view['phase']), None))
        for field, label, fmt in (('progress', 'Progress', lambda v: '%.1f%%' % (v * 100.)),
                                 ('elapsed', 'Elapsed', lambda v: '%d:%02d' % (v // 60, v % 60)),
                                 ('phase_remaining', 'Phase remaining', lambda v: '%.0f s' % v),
                                 ('completed_mm', 'Filament', lambda v: '%.1f mm' % v)):
            if view[field] is not None:
                rows.append((label + ': ' + fmt(view[field]), None))
        if view['filename']:
            rows.append((view['filename'], None))
        if view['reason']:
            rows.append((view['reason'], None))
        return 'Current procedure', rows

    @staticmethod
    def _action_label(view, action):
        if view['owner'] == 'm300_calibration' and action == 'CONFIRM':
            return {'WAIT_PREPARE': 'Start measurement', 'ADJUST': 'Adjustment done',
                    'WAIT_RETRY': 'Repeat this point', 'REVIEW': 'Save result'}.get(view['state'], 'Confirm')
        return action.replace('_', ' ').title()

    def action(self, view_id, action):
        view = self.view(self.reactor.monotonic())
        if view_id != view['view_id'] or action not in view['actions']:
            raise self.printer.command_error('M300: expired or unavailable procedure action; refresh current procedure')
        owner = self.printer.lookup_object(view['owner'])
        self.consumed = view_id  # Duplicate clicks cannot repeat this phase.
        token, phase = view['token'], view['phase']
        try:
            if view['owner'] == 'm300_filament':
                result = owner.request_ui(action, token, phase)
                if result.get('accepted') is not True:
                    raise self.printer.command_error(result.get('error') or 'Filament action refused')
            elif view['owner'] == 'm300_calibration':
                if action == 'CONFIRM':
                    owner.confirm(token, phase)
                else:
                    owner.cancel('shared operator view', token, phase)
            elif view['owner'] == 'm300_fans':
                owner.cancel(token)
            elif view['owner'] == 'm300_thermal':
                owner.cancel(token, phase)
            elif action == 'CONFIRM_CLEAN':
                owner.confirm_resume_clean(token)
            else:
                result = owner.request_ui(action, token)
                if result.get('accepted') is not True:
                    raise self.printer.command_error(result.get('error') or 'Print action refused')
        except Exception:
            # A refused action may be retried with a newly rendered identity;
            # the previous command is never replayed.
            self.identity = None
            raise
        finally:
            self.reactor.update_timer(self.timer, self.reactor.NOW)

    def _prompt(self, view):
        self._emit('prompt_end')
        self._emit('prompt_begin ' + ('Klipper - ' if view['owner'] == 'm300_thermal' else 'ZORTRAX M300 - ') + view['title'])
        for line in (view['state'] + ': ' + view['message'],
                     'Session %s / Phase %s' % (view['token'], view['phase']), view['reason']):
            if line:
                self._emit('prompt_text ' + clean(line))
        if view['owner'] == 'm300_calibration':
            for label, action in format_view(view['snapshots'][view['owner']],
                                            (view['token'], view['phase'])):
                if action is None:
                    self._emit('prompt_text ' + clean(label))
        for verb in view['actions']:
            color = 'error' if verb == 'CANCEL' else 'primary'
            self._emit('prompt_button %s|ZORTRAX_PROCEDURE_ACTION VIEW=%s ACTION=%s|%s' %
                       (self._action_label(view, verb), view['view_id'], verb, color))
        self._emit('prompt_footer_button Refresh|ZORTRAX_PROCEDURE_SHOW|info')
        self._emit('prompt_show')
        self.last_prompt = view['view_id']

    def _tick(self, now):
        if not self.live:
            return self.reactor.NEVER
        view = self.view(now)
        if view['owner']:
            if view['view_id'] != self.last_prompt:
                self._prompt(view)
                if view['owner'] == 'm300_calibration':
                    # External console, Fluidd and the encoder all follow the
                    # same current owner/phase, including screw pictograms.
                    menu = self.printer.lookup_object('m300_menu', None)
                    oled = self.printer.lookup_object('m300_oled', None)
                    if menu is not None and oled is not None:
                        menu._navigate('procedure')
                        oled.page, oled.selection, oled.render_at = 'm04', 0, 0.
            display = self.printer.lookup_object('display_status', None)
            visible = (view['busy'] or view['state'] not in TERMINAL
                       or now - self.changes[view['owner']] < 8.)
            if display is not None and visible:
                if self.last_display is None:
                    self.previous_display = display.message
                if view['owner'] == 'm300_job':
                    text = ('Clean nozzle' if 'CONFIRM_CLEAN' in view['actions'] else
                            view['state'].replace('_', ' ').title())
                else:
                    prefix = (str(view['snapshots'][view['owner']].get('operation') or 'Filament')
                              if view['owner'] == 'm300_filament' else
                              'Fan' if view['owner'] == 'm300_fans' else
                              'PID' if view['owner'] == 'm300_thermal' else 'Level')
                    short = {'WAIT_INSERT': 'Insert', 'WAIT_UNLOAD': 'Remove',
                             'WAIT_PURGE': 'Inspect', 'WAIT_PREPARE': 'Prepare',
                             'WAIT_RETRY': 'Retry', 'COMPLETE': 'Done'}.get(
                                 view['state'], view['state'].replace('_', ' ').title())
                    text = prefix + ': ' + short
                if view['progress'] is not None:
                    text += ' %.0f%%' % (100. * view['progress'])
                self.last_display = clean(text, 64)
                display.message = self.last_display
            elif not visible:
                self._release_display()
        else:
            self._release_display()
        return now + (.5 if view['busy'] else 2.)

    def get_status(self, now):
        view = self.view(now)
        # Owner snapshots already have their native Moonraker objects. Keep
        # the shared object small at normal subscription rates.
        view.pop('snapshots')
        return dict(view, installed=True, ready=self.live,
                    revision='0.13.16.3-PROCEDURES-M07', automatic_resume=False)

    def cmd_status(self, gcmd):
        gcmd.respond_info('ZORTRAX_PROCEDURE ' + json.dumps(
            self.get_status(self.reactor.monotonic()), sort_keys=True))

    def cmd_show(self, gcmd):
        self._prompt(self.view(self.reactor.monotonic()))
        self.cmd_status(gcmd)

    def cmd_action(self, gcmd):
        self.action(gcmd.get('VIEW'), gcmd.get('ACTION'))

    def cmd_start(self, gcmd):
        operation = gcmd.get('OP')
        if operation not in ('LOAD', 'UNLOAD', 'CHANGE', 'LEVEL'):
            raise self.printer.command_error('M300: unknown procedure')
        temp = gcmd.get_float('TEMP', None)
        if operation == 'LEVEL':
            self.printer.lookup_object('m300_calibration').start(temp)
        else:
            self.printer.lookup_object('m300_filament').start(operation, temperature=temp)
        self.reactor.update_timer(self.timer, self.reactor.NOW)


def load_config(config):
    return M300Procedures(config)
