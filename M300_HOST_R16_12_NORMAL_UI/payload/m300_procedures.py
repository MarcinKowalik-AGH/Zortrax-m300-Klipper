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
from .m300_leveling_oem import describe, format_deviation
from .m300_oem_procedure_ui import describe as describe_service
from .m300_maintenance_ui import describe as describe_maintenance
from .m300_native_service import require_idle_print

OWNERS = ('m300_filament', 'm300_calibration', 'm300_maintenance',
          'm300_thermal', 'm300_fans', 'm300_job', 'm300_motion')
HOMING_TITLES = {'HOME_XY': 'Homing XY', 'HOME_Z': 'Homing Z', 'HOME_ALL': 'Homing ALL'}
HOMING_COMMANDS = {'HOME_XY': 'G28 X Y', 'HOME_Z': 'G28 Z', 'HOME_ALL': 'G28'}
HOMING_PHASES = {
    'HOME_Y': 'Homing Y', 'HOME_X': 'Homing X', 'Z_PREHEAT': 'Heating nozzle for Z',
    'Z_CHECK_CONTACT': 'Checking Z contact', 'Z_CONTACT_POSITION': 'Moving to Z contact',
    'HOME_Z_NATIVE_PROBE': 'Homing Z', 'Z_FIVE_CONTACT_REFERENCES': 'Refining Z reference',
    'Z_FINAL_CLEARANCE': 'Moving to Z clearance',
}
TERMINAL = ('COMPLETE', 'CANCELLED', 'FAULT', 'ERROR')
VERBS = ('CONFIRM', 'PURGE', 'PAUSE', 'RESUME', 'CONFIRM_CLEAN', 'CANCEL',
         'BACK', 'TOGGLE_UPPER', 'TOGGLE_LOWER')


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
        self.printer.register_event_handler('m300:homing_view_changed', self._homing_changed)
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

    def _homing_changed(self):
        if self.live:
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
        calibration = self._read('m300_calibration', self.reactor.monotonic())
        if calibration.get('state') == 'FAULT':
            # A host-requested shutdown must retain the actual pad failure
            # explanation in Fluidd. All actions are revoked by live=False.
            self._prompt(self.view(self.reactor.monotonic(), owner_override='m300_calibration'))
        else:
            for name in ('m300_fans','m300_maintenance'):
                status=self._read(name,self.reactor.monotonic())
                if (status.get('state') == 'FAULT'
                        and status.get('reason') != 'host lifecycle invalidated the service'
                        and not status.get('platform_panel_local')):
                    self._prompt(self.view(self.reactor.monotonic(),owner_override=name))
                    break

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
        if service is None or (name == 'm300_motion' and
                               getattr(service, 'operator_homing', None) not in HOMING_TITLES):
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
                status.get('ready') is True, status.get('upper_enabled'),
                status.get('lower_enabled'), status.get('upper_cooling'))

    def view(self, now, owner_override=None):
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
                  and snapshots[n]['state'] not in TERMINAL
                  and (n!='m300_maintenance' or snapshots[n].get('operation')=='HOTEND'
                       or snapshots[n].get('native_control'))]
        terminal = [n for n in OWNERS if snapshots[n]['state'] in TERMINAL
                    and snapshots[n].get('session_token') not in (None, 0, '')
                    and (n!='m300_maintenance' or snapshots[n].get('operation')=='HOTEND'
                         or snapshots[n].get('native_control'))]
        recent = max(terminal, key=lambda n: self.changes[n], default=None)
        if recent and now - self.changes[recent] < 8. and (
                not active or self.changes[recent] > max(self.changes[n] for n in active)):
            owner = recent
        else:
            owner = active[0] if active else recent
        if owner_override in snapshots and snapshots[owner_override]['state'] != 'UNAVAILABLE':
            owner = owner_override
        status = snapshots[owner] if owner else {'state': 'IDLE', 'busy': False}
        language = 'EN'
        identity = self._key(owner, status) + (language,)
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
            elif owner == 'm300_fans' and status.get('native_control'):
                actions = [a for a in ('BACK', 'TOGGLE_UPPER', 'TOGGLE_LOWER')
                           if status.get('can_'+a.lower()) is True]
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
        if owner == 'm300_motion':
            title = HOMING_TITLES[status['operation']]
            message = HOMING_PHASES.get(status.get('phase'), message)
        stats = self._read('print_stats', now)
        elapsed = (number(stats.get('print_duration')) if owner == 'm300_job' else
                   max(0., now - self.started.get(owner, now)))
        progress = number(status.get('progress')) if owner == 'm300_job' else None
        screen = (describe(status, language) if owner == 'm300_calibration'
                  else describe_service(owner,status,language))
        if screen:
            titles={'m300_calibration':'Platform leveling',
                    'm300_maintenance':'Heat the extruder','LOAD':'Load the material',
                    'UNLOAD':'Unload the material','CHANGE':'Change the material'}
            title = titles.get(owner,titles.get(status.get('operation'),'Zortrax M300'))
            message = screen['text']
        maintenance_screen = describe_maintenance(owner, status)
        if maintenance_screen:
            title, message = maintenance_screen['title'], maintenance_screen['text']
        return {'owner': owner, 'state': state, 'title': clean(title),
                'leveling_screen': screen,
                'maintenance_screen': maintenance_screen,
                'message': message if screen or maintenance_screen else clean(message), 'view_id': self.view_id,
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
        if view['owner'] == 'm300_motion':
            rows = [(view['title'], None), (view['message'], None)]
            if view['busy']:
                rows.append(('Please wait', None))
            else:
                rows.insert(0, ('Back', ('page', 'maintenance')))
                if view['reason']:
                    rows.append((view['reason'], None))
            return view['title'], rows
        if (view.get('maintenance_screen') or {}).get('kind') == 'fan_menu':
            return view['title'], [(self._action_label(view, action),
                    ('procedure_action', view['view_id'], action)) for action in view['actions']]
        if view.get('leveling_screen') or view['owner']=='m300_calibration':
            screen = view.get('leveling_screen') or describe(view['snapshots'][view['owner']])
            rows = [(line, None) for line in screen['text'].split('\n')]
            if screen['diagram'] is not None:
                rows.extend(('%s: %s mm' % (p, format_deviation(v)), None)
                            for p, v in enumerate(screen['diagram']))
            rows.extend((self._action_label(view, action),
                         ('procedure_action', view['view_id'], action))
                        for action in view['actions'])
            return view['title'], rows
        rows = [('Back', ('page', 'main')), (view['title'] + ': ' + view['state'], None)]
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
        screen = view.get('maintenance_screen') or {}
        if screen.get('kind') == 'fan_menu':
            return screen['labels'][('BACK', 'TOGGLE_UPPER', 'TOGGLE_LOWER').index(action)]
        if view.get('leveling_screen') or view['owner']=='m300_calibration':
            return 'Cancel' if action=='CANCEL' else 'Continue'
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
            elif view['owner'] in ('m300_calibration','m300_maintenance'):
                if action == 'CONFIRM':
                    owner.confirm(token, phase)
                else:
                    owner.cancel('shared operator view', token, phase)
            elif view['owner'] == 'm300_fans':
                if action == 'BACK':
                    owner.end_oem()
                elif action in ('TOGGLE_UPPER', 'TOGGLE_LOWER'):
                    owner.toggle(action[7:], token, phase)
                else:
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
        if view['snapshots'].get(view['owner'], {}).get('platform_panel_local'):
            return
        self._emit('prompt_end')
        self._emit('prompt_begin ' + ('Klipper - ' if view['owner'] == 'm300_thermal' else 'ZORTRAX M300 - ') + view['title'])
        if view['owner'] == 'm300_motion':
            if view['busy']:
                self._emit('prompt_text M300_HOMING_ACTIVE')
            self._emit('prompt_text ' + view['message'])
            if view['reason']:
                self._emit('prompt_text ' + view['reason'])
        elif view.get('leveling_screen'):
            screen = view.get('leveling_screen') or describe(view['snapshots'][view['owner']])
            for line in screen['text'].split('\n'):
                self._emit('prompt_text ' + line.replace('|', '/'))
            if screen['diagram'] is not None:
                # Same rounded numbers as the physical five-point diagram.
                for p in (4, 3, 2, 1, 0):
                    self._emit('prompt_text %s: %s mm' % (p, format_deviation(screen['diagram'][p])))
        elif view.get('maintenance_screen'):
            for line in view['maintenance_screen']['text'].split('\n'):
                self._emit('prompt_text '+line)
        else:
            for line in (view['state'] + ': ' + view['message'],
                         'Session %s / Phase %s' % (view['token'], view['phase']), view['reason']):
                if line:
                    self._emit('prompt_text ' + clean(line))
        for verb in view['actions']:
            color = 'error' if verb == 'CANCEL' else 'primary'
            self._emit('prompt_button %s|ZORTRAX_PROCEDURE_ACTION VIEW=%s ACTION=%s|%s' %
                       (self._action_label(view, verb), view['view_id'], verb, color))
        if self.live and not (view.get('leveling_screen') or view.get('maintenance_screen')):
            self._emit('prompt_footer_button Refresh|ZORTRAX_PROCEDURE_SHOW|info')
        self._emit('prompt_show')
        self.last_prompt = view['view_id']

    def _tick(self, now):
        if not self.live:
            return self.reactor.NEVER
        view = self.view(now)
        if view['owner'] and not view['snapshots'][view['owner']].get('platform_panel_local'):
            if view['view_id'] != self.last_prompt:
                homing = view['owner'] == 'm300_motion'
                finished_service = (view['state'] in ('COMPLETE', 'CANCELLED') and
                    (homing or ((view.get('maintenance_screen') or view.get('leveling_screen'))
                     and view['owner'] in ('m300_maintenance','m300_filament',
                                           'm300_calibration','m300_fans'))))
                if finished_service:
                    self._emit('prompt_end')
                    self.last_prompt=view['view_id']
                else:
                    self._prompt(view)
                maintenance_screen = view.get('maintenance_screen')
                if maintenance_screen and view['busy']:
                    menu=self.printer.lookup_object('m300_menu',None)
                    oled=self.printer.lookup_object('m300_oled',None)
                    # A held platform must keep its acknowledged row; changing
                    # that view would revoke the physical hold lease.
                    if menu is not None and oled is not None and view['state']!='PLATFORM_HOLD':
                        page='fan_test' if maintenance_screen['kind']=='fan_menu' else 'maintenance'
                        if menu.page!=page or oled.page!='m04':
                            menu._navigate(page)
                            oled.page,oled.selection,oled.render_at='m04',0,0.
                            if page=='maintenance':
                                labels=[label for label,_ in menu.rows(now)[1]]
                                if maintenance_screen['text'] in labels:
                                    oled.selection=labels.index(maintenance_screen['text'])
                elif not finished_service and (
                        (homing and view['busy']) or
                        (view.get('leveling_screen') and
                         (view['owner'] == 'm300_calibration' or view['busy']))):
                    # External console, Fluidd and the encoder all follow the
                    # same current owner/phase, including screw pictograms.
                    menu = self.printer.lookup_object('m300_menu', None)
                    oled = self.printer.lookup_object('m300_oled', None)
                    ui = self.printer.lookup_object('m300_menu_ui', None)
                    if (menu is not None and oled is not None
                            and (homing or not getattr(ui, 'leveling_settings', False))
                            and (menu.page != 'procedure' or oled.page != 'm04')):
                        menu._navigate('procedure')
                        oled.page, oled.selection, oled.render_at = 'm04', 0, 0.
                        if homing:
                            oled.message = None
                            oled._user_refresh_pending = True
                elif finished_service:
                    # OEM Heat/Load/Unload return to the invoking submenu.
                    menu=self.printer.lookup_object('m300_menu',None)
                    oled=self.printer.lookup_object('m300_oled',None)
                    if menu is not None and oled is not None and menu.page in ('procedure','fan_test'):
                        operation=view['snapshots'][view['owner']].get('operation')
                        menu.return_from_procedure(view['owner'], operation)
                        oled.page,oled.selection,oled.render_at='m04',0,0.
            display = self.printer.lookup_object('display_status', None)
            visible = (view['busy'] or view['state'] not in TERMINAL
                       or now - self.changes[view['owner']] < 8.)
            if display is not None and visible:
                if self.last_display is None:
                    self.previous_display = display.message
                if view['owner'] == 'm300_job':
                    text = ('Clean nozzle' if 'CONFIRM_CLEAN' in view['actions'] else
                            view['state'].replace('_', ' ').title())
                elif view.get('maintenance_screen'):
                    text = view['maintenance_screen']['text']
                elif view.get('leveling_screen'):
                    text = view['leveling_screen']['text']
                elif view['owner'] == 'm300_motion':
                    text = view['title'] + ' ' + view['message']
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
                    revision='0.13.16.7-OEM-PROCEDURES', automatic_resume=False)

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
        if operation not in ('LOAD', 'UNLOAD', 'CHANGE', 'LEVEL','HEAT',
                             'FANS','FAN_UPPER','FAN_LOWER','FAN_BACK', *HOMING_TITLES):
            raise self.printer.command_error('M300: unknown procedure')
        temp = gcmd.get_float('TEMP', None)
        try:
            if operation in HOMING_TITLES:
                motion = self.printer.lookup_object('m300_motion', None)
                if not getattr(motion, 'normal_control', False):
                    raise self.printer.command_error('Native M300 homing is unavailable')
                require_idle_print(self.printer, self.reactor.monotonic())
                self.gcode.run_script_from_command(HOMING_COMMANDS[operation])
            elif operation.startswith('FAN'):
                owner=self.printer.lookup_object('m300_fans')
                if operation=='FAN_BACK':
                    owner.end_oem()
                else:
                    if owner.test is None:
                        owner.start_oem()
                    if operation == 'FANS':
                        self.last_prompt = None  # Reopen the current session without resetting its switches.
                    else:
                        owner.toggle(operation[4:],owner.token,owner.phase)
            elif operation == 'LEVEL':
                self.printer.lookup_object('m300_calibration').start(temp)
            elif operation=='HEAT':
                self.printer.lookup_object('m300_maintenance').start('HOTEND',temp)
            else:
                self.printer.lookup_object('m300_filament').start(operation, temperature=temp)
        except self.printer.command_error as exc:
            # Closing the web dialog is not a procedure confirmation. Reopen
            # the service that still owns the machine so it can be finished.
            for name in OWNERS:
                if str(exc).endswith(name + ' owns resources'):
                    now = self.reactor.monotonic()
                    if self._read(name, now).get('busy') is True:
                        self._prompt(self.view(now, owner_override=name))
                    break
            raise
        self.reactor.update_timer(self.timer, self.reactor.NOW)


def load_config(config):
    return M300Procedures(config)
