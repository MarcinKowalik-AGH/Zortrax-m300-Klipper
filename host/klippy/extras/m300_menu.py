# SPDX-License-Identifier: GPL-3.0-or-later
"""M04 operator menu. Rows are data; file names never become G-code text.

Each confirmation holds the identity/token that was displayed. Rendering may
update observations, but cannot silently grant consent to a new job or phase.
"""
import json
import logging
import os
import stat
import textwrap


def sort_entries(entries, mode):
    def key(item):
        tail = (item['name'].casefold(), item['name'])
        value = ({'NAME': tail, 'NAME_CASE': (item['name'],),
                  'DATE': (-item['mtime'],) + tail,
                  'SIZE': (-item['size'],) + tail}.get(mode, tail))
        return (not item['is_dir'], value)
    return sorted(entries, key=key)


def card_entries(entries, mode):
    result = []
    for entry in entries:
        if entry['name'].startswith('.'):
            continue
        if not entry['directory'] and os.path.splitext(entry['name'])[1].lower() not in (
                '.gcode', '.gco', '.g', '.zcode'):
            continue
        result.append(dict(name=entry['name'], path=entry['path'],
                           is_dir=entry['directory'], size=entry['size'],
                           mtime=entry['modified'], fingerprint=entry.get('fingerprint')))
    return sort_entries(result, mode)


def host_entries(root, relative, sort_mode='NAME'):
    if (relative.startswith('/') or '\\' in relative or ':' in relative
            or any(p in ('.', '..', '') for p in relative.split('/') if relative)
            or len(relative.encode('utf-8')) >= 255 or relative.count('/') >= 31):
        raise ValueError('invalid browser directory')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(root, flags)
    try:
        for part in relative.split('/') if relative else ():
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        entries = []
        with os.scandir(fd) as iterator:
            for entry in iterator:
                if entry.name.startswith('.') or entry.is_symlink():
                    continue
                info = entry.stat(follow_symlinks=False)
                directory = stat.S_ISDIR(info.st_mode)
                if not directory and (not stat.S_ISREG(info.st_mode)
                        or os.path.splitext(entry.name)[1].lower() not in ('.gcode', '.gco', '.g', '.zcode')):
                    continue
                path = '/'.join(p for p in (relative, entry.name) if p)
                if len(path.encode('utf-8')) >= 255:
                    continue
                entries.append({'name': entry.name, 'path': path, 'is_dir': directory,
                                'size': info.st_size, 'mtime': info.st_mtime})
                if len(entries) > 50:
                    raise ValueError('directory exceeds the 50-entry browser limit')
        return sort_entries(entries, sort_mode)
    finally:
        os.close(fd)


class M300Menu:
    HOMING_UI_ABI = 1  # R15.5 motion startup contract retained.
    MENU_REVISION = "0.13.16.13-BRIGHTNESS-MESH-BOUNDS"
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.job = self.printer.load_object(config, 'm300_job')
        self.nvm = self.printer.load_object(config, 'm300_nvm')
        self.maintenance = self.printer.load_object(config, 'm300_maintenance')
        if getattr(self.job.board, 'native_control', False) and config.has_section('m300_settings'):
            self.printer.load_object(config, 'm300_settings')
        if getattr(self.job.board, 'native_control', False) and config.has_section('m300_models'):
            self.printer.load_object(config, 'm300_models')
        if getattr(self.job.board, 'native_control', False) and config.has_section('m300_print_ui'):
            self.printer.load_object(config, 'm300_print_ui')
        self.cycle = self.printer.lookup_object('m300_cycle', None)
        self.page, self.reason = 'main', ''
        self.generation = 0
        self._busy = False
        self._entries = []
        self._browser_generation = None
        self._directory, self._source = '', 'host'
        self._preview = None
        self._repeat_identity = None
        self._last_file = None
        self._confirm = None
        self._cal_view = (None, None)
        self._material_view = (None, None)
        self._atlas_address = None
        self._motion_jog_token = None
        self._temperature = {'HOTEND': None, 'BED': None}
        self._return_page = 'material'
        self._procedure_return = self._procedure_launch = self._procedure_dismissed = None
        self._labels = {}
        # Recovered stock labels are UI data; known extraction defects are
        # corrected explicitly in the resource provenance document.
        path = os.path.join(os.path.dirname(__file__), 'm300_menu_labels.json')
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as stream:
                self._labels = json.load(stream)
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self.invalidate)
        self.gcode.register_command('ZORTRAX_MENU_STATUS', self.cmd_status, when_not_ready=True)
        self.gcode.register_command('ZORTRAX_MENU', self.cmd_menu)
        self.printer.register_event_handler('m300:job_completed', self.job_completed)

    def _error(self, message):
        return self.printer.command_error('M300 menu: ' + str(message))

    def _ui(self):
        # Optional M11, looked up lazily because the configured section may
        # load after [m300_menu]. Never change action ownership.
        return self.printer.lookup_object('m300_menu_ui', None)

    def t(self, english):
        ui = self._ui()
        if ui is not None:
            return ui.translate(english)
        return self._labels.get(english, {}).get('en', english)

    @staticmethod
    def clean(text, maximum=160):
        return ' '.join(str(text).split())[:maximum]

    def _leave_motion_jog(self):
        token, self._motion_jog_token = self._motion_jog_token, None
        motion = self.printer.lookup_object('m300_motion', None)
        if (token is not None and motion is not None
                and motion.get_status(self.reactor.monotonic()).get('session_token') == token):
            motion.cancel('operator left the encoder jog view', token=token)

    def invalidate(self, *args):
        self._leave_motion_jog()
        ui = self._ui()
        if ui is not None:
            ui.invalidate()
        self.generation += 1
        self._confirm, self._preview = None, None
        self._repeat_identity = None
        self._cal_view = (None, None)
        self._material_view = (None, None)
        self._procedure_return = self._procedure_launch = self._procedure_dismissed = None
        self.page = 'main'

    def home(self):
        context = getattr(self, '_procedure_return', None)
        dismissed = context['session'] if context else getattr(self, '_procedure_dismissed', None)
        if self.page == 'fan_test':
            fans = self.printer.lookup_object('m300_fans', None)
            if fans is not None and fans.test is not None:
                fans.end_oem()
        self.invalidate()
        self._procedure_dismissed = dismissed
        self.reason = ''

    def _navigate(self, page, remember=True, *, refresh_information=True):
        if self.page == 'fan_test' and page != 'fan_test':
            fans = self.printer.lookup_object('m300_fans', None)
            if fans is not None and fans.test is not None:
                fans.end_oem()
        if self.page == 'motion_jog' and page != 'motion_jog':
            self._leave_motion_jog()
        ui = self._ui()
        if ui is not None:
            ui.entered(self.page, page, remember)
        self.generation += 1
        self.page, self.reason, self._confirm = page, '', None
        if refresh_information and page in ('information', 'info_printer'):
            settings = self.printer.lookup_object('m300_settings', None)
            if settings is not None:
                settings.request_refresh()
        self._material_view = (None, None)
        if page == 'material_status':
            service = self.printer.lookup_object('m300_material_ui', None)
            if service is not None:
                try:
                    view = service.view()
                    self._material_view = (view['token'], view['phase'])
                except Exception:
                    # Rendering will show unavailability. Page entry never
                    # recovers, acknowledges or changes a procedure owner.
                    pass

    def present_information_page(self, page, now):
        """Show a remote menu selection without taking over a modal panel."""
        oled = self.printer.lookup_object('m300_oled', None)
        if (oled is None or not oled.connected or self._busy
                or self.page in ('motion_jog', 'fan_test')
                or self.maintenance.get_status(now).get('platform_held')):
            return
        print_ui = self.printer.lookup_object('m300_print_ui', None)
        if print_ui is not None and print_ui.view(now) is not None:
            return
        at_requested_page = (oled.page == 'status' if page == 'status'
                             else oled.page == 'm04' and self.page == page)
        if at_requested_page and oled.message is None:
            return
        if page == 'status':
            oled._show_status()
        else:
            self._navigate(page, remember=False, refresh_information=False)
            oled.page, oled.selection, oled.message = 'm04', 0, None
            select = getattr(self._ui(), 'brightness_selection', None)
            if select is not None:
                oled.selection = select() or 0
            oled.render_at = 0.
        oled._user_refresh_pending = True
        self.reactor.update_timer(oled.timer, self.reactor.NOW)

    def _panel_route(self):
        oled = self.printer.lookup_object('m300_oled', None)
        return (self.page, oled.page, self.generation) if oled is not None else None

    def _panel_origin(self):
        oled = self.printer.lookup_object('m300_oled', None)
        if oled is None:
            return None
        ui = self._ui()
        history = getattr(ui, 'history', None)
        # Only navigation is saved. Never save an action token, confirmation,
        # heater/motor state, file handle or a resumable print state here.
        panel = {'job_cancel':'job', 'filament_cancel':'filament'}.get(oled.page, oled.page)
        page = 'models' if self.page in ('confirm', 'confirm_print') else self.page
        stack = tuple(history.stack) if history is not None else ()
        if page in ('procedure', 'fan_test'):
            page, stack = (stack[-1], stack[:-1]) if stack else ('maintenance', ())
        return dict(panel=panel, page=page, selection=oled.selection,
                    history=stack)

    def _launch_origin(self, view):
        hint = getattr(self, '_procedure_launch', None)
        if hint is None:
            return None
        status = view['snapshots'][view['owner']]
        if (hint['generation'] != self.generation or hint['owner'] != view['owner']
                or hint['operation'] != status.get('operation')
                or hint['previous_token'] == view['token']):
            return None
        self._procedure_launch = None
        return hint['origin']

    def present_procedure(self, view, page, selection=0):
        """Temporarily show this owner/session, retaining its invoking screen."""
        oled = self.printer.lookup_object('m300_oled', None)
        if oled is None:
            return False
        session = view['owner'], view['token']
        if session == getattr(self, '_procedure_dismissed', None):
            return False
        context = getattr(self, '_procedure_return', None)
        route = self._panel_route()
        if context is None or context['session'] != session:
            origin = self._launch_origin(view)
            if origin is None:
                origin = (context['origin'] if context and context['shown']==route
                          else self._panel_origin())
            context = dict(session=session, origin=origin, shown=None)
            self._procedure_return = context
        elif context['shown'] != route:
            # Settings or another manually selected screen is not a modal
            # owner. Phase updates must not steal it from the operator.
            if not (self.page == page and oled.page == 'm04'):
                return False
        if self.page != page or oled.page != 'm04':
            self._navigate(page, remember=False)
            oled.page, oled.selection = 'm04', selection
        context['shown'] = self._panel_route()
        oled.message = None
        self._refresh_panel(oled)
        return True

    def _refresh_panel(self, oled):
        oled._input_epoch = getattr(oled, '_input_epoch', 0)+1
        oled._presented_context = oled._presented_actions = None
        oled.render_at = 0.
        oled._user_refresh_pending = True

    def return_from_procedure(self, owner, operation, token=None, *, explicit=False):
        context = getattr(self, '_procedure_return', None)
        oled = self.printer.lookup_object('m300_oled', None)
        if context is not None:
            if context['session'][0] != owner or token is not None and context['session'][1] != token:
                return False
            if not explicit and context['shown'] != self._panel_route():
                return False  # Preserve a screen the operator deliberately opened.
            origin = context['origin']
            self._procedure_return = self._procedure_launch = None
            self._procedure_dismissed = context['session']
            if oled is not None and origin is not None:
                if origin['panel'] == 'status':
                    oled._show_status()
                else:
                    self._navigate(origin['page'], remember=False, refresh_information=False)
                    oled.page, oled.selection, oled.message = origin['panel'], origin['selection'], None
                    ui = self._ui()
                    if getattr(ui, 'history', None) is not None:
                        ui.history.stack[:] = origin['history']
                        ui.history.scroll_anchor = None
                    select = getattr(ui, 'brightness_selection', None)
                    if select is not None and origin['selection'] > 0:
                        level = select()
                        if level is not None:
                            oled.selection = level  # A concurrent setting change is not undone.
                self._refresh_panel(oled)
                return True
        if oled is not None and (oled.page != 'm04' or self.page not in ('procedure', 'fan_test')):
            return False
        page = ('native_job' if operation == 'CHANGE' else
                'material' if owner == 'm300_filament' else
                'maintenance')
        self._navigate(page, remember=False)
        if oled is not None:
            oled.page, oled.selection = 'm04', 0
            self._refresh_panel(oled)
        return True

    def _service(self, name):
        obj = self.printer.lookup_object(name, None)
        if obj is None:
            raise self._error(name + ' is not configured')
        return obj

    def present_motion_jog(self, motion, token):
        """Bind an already-created M06 lease to the current physical panel."""
        if motion is not self._service('m300_motion'):
            raise self._error('foreign motion owner')
        status = motion.get_status(self.reactor.monotonic())
        if (type(token) is not int or status.get('session_token') != token
                or status.get('busy') is not True
                or status.get('state') not in ('JOG_WAIT_RELEASE', 'JOG_WAIT_PRESS', 'JOGGING')):
            raise self._error('current encoder jog session required')
        oled = self._service('m300_oled')
        self._navigate('motion_jog')
        self._motion_jog_token = token
        oled.page, oled.selection, oled.render_at = 'm04', 0, 0.

    def _temperature_label(self, kind):
        value = self._temperature[kind]
        return '---' if value is None else '%d°C' % value

    def _notice(self, rows):
        if self.reason:
            rows.extend((line, None) for line in textwrap.wrap(
                self.clean(self.reason), width=36, max_lines=5, placeholder='...'))
        return rows

    def rows(self, now):
        ui = self._ui()
        native = getattr(getattr(getattr(self, 'job', None), 'board', None), 'native_control', False)
        back = [(self.t('Back'), ('ui_back', self.generation)
                 if ui is not None else ('page', 'main'))]
        if not native and self.maintenance.get_status(now)['sleep']:
            return self.t('Sleep'), [(self.t('Wake up'), ('wake',)),
                    ('Targets 0; position not restored', None)]
        if native and self.page == 'main':
            return 'M300', self._notice([
                ('Klipper', ('page', 'klipper')),
                ('Zortrax M300', ('page', 'zortrax')),
                ('Service / Tests', ('page', 'tests'))])
        if native and self.page == 'zortrax':
            return 'Zortrax M300', self._notice([(self.t('Back'), ('page', 'main')),
                (self.t('Models'), ('page', 'models')),
                (self.t('Maintenance'), ('page', 'maintenance')),
                (self.t('Material'), ('page', 'material')),
                (self.t('Settings'), ('page', 'settings')),
                (self.t('Information'), ('page', 'information'))])
        if native and self.page == 'maintenance':
            return self.t('Maintenance'), self._notice([(self.t('Back'), ('page', 'zortrax')),
                (self.t('Autocalibration'), ('native_gcode','ZORTRAX_LEVEL')),
                ('Homing XY', ('native_gcode', 'ZORTRAX_HOME_XY')),
                ('Homing Z', ('native_gcode', 'ZORTRAX_HOME_Z')),
                ('Homing ALL', ('native_gcode', 'ZORTRAX_HOME_ALL')),
                (self.t('Heat the extruder'), ('native_gcode','ZORTRAX_HEAT')),
                (self.t('Move the platform up'), ('platform_hold',-1)),
                (self.t('Move the platform down'), ('platform_hold',1)),
                (self.t('Fan test'), ('native_gcode','ZORTRAX_FAN_TEST_START'))])
        if native and self.page == 'fan_test':
            return self._service('m300_procedures').rows(now)
        if native:
            from .m300_settings import PAGES
            if self.page in PAGES:
                settings = self.printer.lookup_object('m300_settings', None)
                if settings is None:
                    return 'Settings / Information', back+[('Settings service unavailable', None)]
                title, rows = settings.rows(self.page, now)
                if self.page == 'settings' and getattr(self._ui(), 'leveling_settings', False):
                    view = self._service('m300_procedures').view(now)
                    target = 'maintenance' if view['state'] in ('COMPLETE', 'CANCELLED', 'IDLE') else 'procedure'
                    context = getattr(self, '_procedure_return', None)
                    if (target == 'maintenance' and context is not None
                            and context['session'] == (view['owner'], view['token'])):
                        rows[0] = ('Back', ('procedure_return', view['owner'], view['token']))
                    else:
                        rows[0] = ('Back', ('page', target))
                return title, self._notice(rows)
        if native and self.page == 'material':
            return self.t('Material'), self._notice([(self.t('Back'), ('page', 'zortrax')),
                (self.t('Unload the material'), ('native_gcode','ZORTRAX_UNLOAD')),
                (self.t('Load the material'), ('native_gcode','ZORTRAX_LOAD'))])
        if native and self.page == 'tests':
            return 'Service / Tests', self._notice(back + [
                ('Diagnostics', ('page', 'diagnostics')),
                ('TEST: material procedures', ('page', 'material')),
                ('TEST: platform calibration', ('cal_start',)),
                ('TEST: calibration status', ('cal_refresh',)),
                ('TEST: OEM print / SD', ('page', 'models')),
                ('Current test procedure', ('page', 'procedure')),
                ('Read test status', ('native_gcode', 'TEST_ZORTRAX_STATUS')),
                ('TEST XY 50 mm/s', ('native_gcode', 'TEST_ZORTRAX_XY SPEED=50')),
                ('TEST XY 60 mm/s', ('native_gcode', 'TEST_ZORTRAX_XY SPEED=60'))])
        if native and self.page == 'native_pid':
            stats = self.printer.lookup_object('print_stats', None)
            busy = stats is not None and stats.get_status(now).get('state') in ('printing', 'paused')
            def command(script):
                return None if busy else ('native_gcode', script)
            return 'PID calibration', back + [
                ('Hotend PID 200C', command('PID_CALIBRATE HEATER=extruder TARGET=200')),
                ('Bed PID 60C', command('PID_CALIBRATE HEATER=heater_bed TARGET=60')),
                ('Save calibration', command('SAVE_CONFIG'))]
        if native and self.page == 'native_job':
            stats = self.printer.lookup_object('print_stats', None)
            view = stats.get_status(now) if stats is not None else {}
            state = view.get('state', 'standby')
            rows = back + [('State: ' + self.clean(state), None),
                           ('File: ' + self.clean(view.get('filename', '')), None),
                           ('Print time: %.0f s' % view.get('print_duration', 0.), None)]
            if self.printer.lookup_object('m300_print_ui', None) is not None:
                return 'Print status', rows
            if state == 'printing':
                rows.append(('Pause', ('native_gcode', 'PAUSE')))
            if state == 'paused':
                rows.append(('Change the material', ('native_gcode', 'ZORTRAX_CHANGE')))
                rows.append(('Resume', ('native_gcode', 'RESUME')))
            if state in ('printing', 'paused'):
                rows.append(('Cancel', ('native_gcode', 'CANCEL_PRINT')))
            return 'Print status', rows
        if self.page == 'main':
            rows = [
                (self.t('Models'), ('page', 'models')),
                (self.t('Material'), ('page', 'material')),
                (self.t('Maintenance'), ('page', 'maintenance')),
                (self.t('Settings'), ('page', 'settings')),
                (self.t('Information'), ('page', 'information')),
                ('Job', ('oled', 'job')),
                ('Diagnostics', ('page', 'diagnostics')),
                (self.t('Sleep'), ('confirm_sleep',))]
            if native:
                rows = [row for row in rows if row[1] != ('confirm_sleep',)]
                rows = [(('Job' if row[0] == 'Job' else
                          'Diagnostics' if row[0] == 'Diagnostics' else row[0]), row[1])
                        for row in rows]
            if not native and self.printer.lookup_object('m300_procedures', None) is not None:
                rows.insert(0, ('Current procedure', ('page', 'procedure')))
            cycle = self.cycle.get_status(now) if self.cycle is not None else {}
            if cycle.get('can_confirm_resume_clean'):
                rows.insert(1, ('Nozzle clean: confirm', ('cycle_clean', cycle.get('job_token'))))
            return ('M300' if native else 'M300 / M08 LAB'), self._notice(rows)
        if self.page == 'procedure':
            service = self.printer.lookup_object('m300_procedures', None)
            if service is None:
                return 'Current procedure', back + [('Procedure view unavailable', None)]
            title, rows = service.rows(now)
            if rows and rows[0][0] == 'Back':
                rows = back + rows[1:]
            return title, self._notice(rows)
        if self.page == 'fans':
            service = self.printer.lookup_object('m300_fans', None)
            if service is None:
                return 'Fans', back + [('Fan service unavailable', None)]
            title, rows = service.rows(now)
            return title, self._notice(back + rows[1:])
        models = self.printer.lookup_object('m300_models', None) if native else None
        if models is not None and self.page == 'models':
            card = self.printer.lookup_object('m300_sd', None)
            sd_row = (('SD card', ('browse', 'sd', '')) if getattr(card, 'qualified', False)
                      else ('SD card access is disabled', None))
            return 'Models', self._notice(back + [sd_row, ('Host files', ('browse', 'host', ''))])
        if models is not None and self.page == 'model_file':
            view = models.get_status(now)
            token = view['token']
            rows = [('Back', ('model_cancel', token))]
            if view['state'] == 'READY':
                rows.append(('Start printing', ('model_start', token)))
            rows.extend((line, None) for line in textwrap.wrap(self.clean(view['filename'] or '', 240), 34))
            if view['state'] == 'IMPORTING':
                rows += [('Reading model', None), ('Copied: %d bytes' % view['bytes_copied'], None)]
            elif view['state'] == 'READY':
                rows.append((view['format'], None))
                for name, target in view['targets'].items():
                    rows.append(('%s: %g C' % (name.title(), target), None))
            elif view['error']:
                rows.extend((line, None) for line in textwrap.wrap(self.clean(view['error'], 240), 34))
            else:
                rows.append(('Model selection unavailable', None))
            return 'Model information', self._notice(rows)
        if self.page == 'models':
            rows = back + [('Host', ('browse', 'host', '')),
                           ('SD / SPI1', ('browse', 'sd', ''))]
            if self._last_file:
                rows.append((self.t('Print again'), ('repeat',)))
            return self.t('Models'), self._notice(rows)
        if self.page == 'browser':
            parent = self._directory.rsplit('/', 1)[0] if '/' in self._directory else ''
            if self._directory:
                action = ('browse', self._source, parent)
            elif models is not None:
                action = ('page', 'zortrax')
            else:
                action = ('page', 'models')
            rows = [(self.t('Up') if self._directory else self.t('Back'), action)]
            rows.extend((('> ' if x['is_dir'] else '') + self.clean(x['name'], 240),
                ('directory' if x['is_dir'] else 'file', self._source, x['path'], self.generation))
                for x in self._entries)
            if not self._entries:
                rows.append((self.t('No models'), None))
            if models is not None and self._source == 'sd' and not self._directory:
                rows.append(('Host files', ('browse', 'host', '')))
            return ('SD:/' if self._source == 'sd' else 'Host:/') + self._directory, self._notice(rows)
        if self.page in ('preview', 'confirm_print'):
            p = self._preview
            rows = [(self.t('Back'), ('page', 'models'))]
            if p is None:
                rows.append(('No current checked snapshot', None))
            else:
                if getattr(self.job, 'workflow_qualified', False):
                    rows.append((self.t('Print'), ('confirm_print', p.identity)))
                else:
                    rows.append(('OEM print workflow is disabled', None))
                rows.extend((line, None) for line in textwrap.wrap(self.clean(p.filename, 240), 36))
                rows.extend([('Bytes: %d' % p.size, None),
                             ('SHA256: ' + p.sha256[:16], None),
                             ('Hotend: %.1f°C' % p.targets['hotend'], None),
                             ('Bed: %.1f°C' % p.targets['bed'], None)])
                metadata = getattr(p, 'source_metadata', {})
                for key in ('material', 'estimated_seconds', 'source_bytes', 'profile'):
                    if key in metadata:
                        rows.append((key + ': ' + self.clean(metadata[key]), None))
            return self.t('Model information'), self._notice(rows)
        if self.page == 'confirm':
            repeat = (self._confirm is not None and self._confirm[1][0] == 'print'
                      and self._confirm[1][1] == self._repeat_identity)
            return self.t('Are you sure?'), self._notice([
                back[0],
                ('Model removed: confirm print' if repeat else self.t('Confirm'),
                 ('confirmed', self.generation))] + [
                (line, None) for line in textwrap.wrap(self.clean(
                    self._confirm[0] if self._confirm else 'Expired confirmation'), 36)])
        if self.page == 'material':
            filament = self.printer.lookup_object('m300_filament', None)
            target = getattr(filament, 'procedure_temperature', 240.)
            return self.t('Material'), self._notice(back + [
                ('Load / Unload: %gC' % target, None),
                (self.t('Load the material'), ('material', 'LOAD')),
                (self.t('Unload the material'), ('material', 'UNLOAD')),
                (self.t('Change the material'), ('material', 'CHANGE')),
                ('Current operation', ('oled', 'filament'))] +
                ([('M09: material controls', ('page', 'material_status'))]
                 if self.printer.lookup_object('m300_material_ui', None) is not None else []))
        if self.page == 'material_status':
            facade = self.printer.lookup_object('m300_material_ui', None)
            if facade is None:
                return self.t('Material'), back + [('Material module unavailable', None)]
            try:
                view = facade.view()
            except Exception as exc:
                return self.t('Material'), back + [
                    ('Material status unavailable', None),
                    (self.clean(str(exc), 120), None),
                    ('Refresh', ('page', 'material_status'))]
            current = (view['token'], view['phase']) == self._material_view
            rows = [('Back', ('page', 'material')),
                    (self.clean(view['message'], 80) if current else 'Phase changed: Refresh first', None),
                    ('Phase: ' + str(view['phase']), None)]
            for verb, label in [('CONFIRM','Confirm'),
                                ('PURGE','Purge'),('CANCEL','Cancel')]:
                allowed = current and verb in view['actions']
                rows.append((label + ('' if allowed else ' [unavailable]'),
                    ('material_action', verb, *self._material_view) if allowed else None))
            rows.append(('Refresh', ('page', 'material_status')))
            if not current:
                rows.append(('Phase changed: select Refresh', None))
            return self.t('Material'), self._notice(rows)
        if self.page in ('maintenance', 'klipper'):
            if native:
                rows = back + [
                    ('Hotend TEMP: ' + self._temperature_label('HOTEND'), ('temperatures', 'HOTEND', 'klipper')),
                    ('Bed TEMP: ' + self._temperature_label('BED'), ('temperatures', 'BED', 'klipper')),
                    ('Heat hotend', ('service', 'HOTEND')),
                    ('Heat bed', ('service', 'BED')),
                    ('Turn off heaters', ('native_gcode', 'TURN_OFF_HEATERS')),
                    ('Home Y', ('motion_home_y',)),
                    ('Home X', ('motion_home_x',)),
                    ('Home XY', ('motion_home_xy',)),
                    ('Home Z (180C)', ('motion_home_z',)),
                    ('Home XYZ', ('motion_home_xyz',)),
                    ('Move axes', ('page', 'native_moves')),
                    ('Fans', ('page', 'fans')),
                    ('PID calibration', ('page', 'native_pid')),
                    ('Print status', ('page', 'native_job'))]
                if self.printer.lookup_object('m300_pad_mesh', None) is not None:
                    rows.insert(11, ('Bed mesh (25 points)', ('page', 'bed_mesh')))
                return 'Klipper', self._notice(rows)
            motion = self.printer.lookup_object('m300_motion', None)
            motion_rows = ([('XY gap >=5mm: CONFIRM', ('motion_xy_arm',)),
                            ('Home Y', ('motion_home_y',)),
                            ('Home X', ('motion_home_x',)),
                            ('Home XY', ('motion_home_xy',)),
                            ('Before Z: heat / clean nozzle', None),
                            ('Home Z', ('motion_home_z',)),
                            ('Home XYZ: SPLIT ONLY', None),
                            ('Move Z with encoder', ('motion_jog',)),
                            ('Motion status', ('page', 'motion_status'))]
                           if motion is not None else [
                            ('Platform Z -1 mm', ('service', 'JOG_Z', -1.)),
                            ('Platform Z +1 mm', ('service', 'JOG_Z', 1.))])
            return self.t('Maintenance'), self._notice(back + [
                ('Hotend TEMP: ' + self._temperature_label('HOTEND'), ('temperatures', 'HOTEND', 'maintenance')),
                ('Bed TEMP: ' + self._temperature_label('BED'), ('temperatures', 'BED', 'maintenance')),
                (self.t('Autocalibration'), ('cal_start',)),
                ('Calibration status', ('cal_refresh',)),
                (self.t('Heat the extruder'), ('service', 'HOTEND')),
                (self.t('Heat the platform'), ('service', 'BED')),
            ] + motion_rows + [
                ('Fans / cooling status', ('page', 'fans')),
                ('Test print fan (5 s)', ('service', 'FAN_PRINT')),
                ('Test hotend fan (5 s)', ('service', 'FAN_HOTEND')),
                ('Stop service / heat off', ('service_stop',))])
        if self.page == 'bed_mesh' and native:
            mesh = self.printer.lookup_object('m300_pad_mesh', None)
            if mesh is None:
                return 'Bed mesh', back+[('Native pad mesh is not configured', None)]
            status = mesh.get_status(now)
            rows = back+[('State: '+self.clean(status.get('state', 'IDLE')), None)]
            if not status.get('busy'):
                rows.append(('Measure 25 pad points', ('native_gcode', 'ZORTRAX_BED_MESH')))
            result = status.get('result') or {}
            if result:
                rows.append(('Profile: '+self.clean(result.get('profile', '')), None))
            rows.append(('Five pads / 25 contacts', None))
            return 'Bed mesh', self._notice(rows)
        if self.page == 'native_moves' and native:
            return 'Move axes', back + [
                ('Move ' + axis, ('page', 'native_move_' + axis.lower()))
                for axis in 'XYZ']
        if self.page.startswith('native_move_') and native:
            axis = self.page[-1].upper()
            if axis not in 'XYZ':
                return 'Move axes', back
            rows = back[:]
            for step in (-10., -1., -.1, .1, 1., 10.):
                script = ('SAVE_GCODE_STATE NAME=M300_UI_NATIVE\nG91\nG1 %s%g F%d') % (
                              axis, step, 300 if axis == 'Z' else 3000)
                rows.append(('%s %+.1f mm' % (axis, step), ('native_gcode', script)))
            return 'Move ' + axis, rows
        if self.page in ('motion_jog', 'motion_status'):
            status = self._service('m300_motion').get_status(now)
            rows = [(self.t('Back'), ('page', 'maintenance')),
                    ('State: ' + self.clean(status.get('state')), None),
                    ('Axes: ' + self.clean(status.get('homed_axes', '')), None),
                    ('Position valid: ' + str(status.get('position_valid', False)), None)]
            if self.page == 'motion_status':
                rows.extend([('Phase: ' + self.clean(status.get('phase','')), None),
                    ('PC7 contact: query via Fluidd', None),
                    ('Z %s steps/mm' % status.get('z_steps_per_mm', '?'), None),
                    ('Z0 heat: %sC' % status.get('z_home_hotend_target_c','?'),None),
                    ('Heating: ' + str(status.get('z_home_preheat_active',False)),None),
                    ('Z gap proof: ' + str(status.get('xy_clearance_mm')),None)])
            if self.page == 'motion_jog':
                rows.extend([('Release, then hold + rotate', None),
                             ('Release stops and ends jog', None),
                             ('Puszczenie: stop i koniec ruchu', None)])
            rows.append(('Cancel', ('motion_stop',)))
            if status.get('reason'):
                rows.extend((line, None) for line in textwrap.wrap(
                    self.clean(status['reason'], 240), 36))
            return 'M300 Z / M06', self._notice(rows)
        if self.page.startswith('temperature_'):
            kind = self.page[12:]
            heater = self.job.hotend if kind == 'HOTEND' else self.job.bed
            candidates = range(170, 301, 10) if kind == 'HOTEND' else range(40, 121, 10)
            return 'Select ' + kind + ' TEMP', [(self.t('Back'), ('page', self._return_page))] + [
                ('%d°C' % value, ('temp', kind, value, self._return_page))
                for value in candidates if heater.min_temp <= value <= heater.max_temp]
        if self.page == 'calibration':
            status = self._service('m300_calibration').get_status(now)
            token, phase = self._cal_view
            if status.get('workflow') == 'M07_STOCK':
                from .m300_leveling_ui import format_view
                rows = list(back)
                for label, action in format_view(status, self._cal_view,
                                                 self.nvm.get_setting('language', 'EN')):
                    if action is None:
                        rows.extend((line, None) for line in textwrap.wrap(self.clean(label, 240), 36))
                    else:
                        rows.append((self.clean(label, 120), action))
                return 'Platform leveling', self._notice(rows)
            rows = back + [(self.clean(status.get('state')), None)]
            if (status.get('session_token'), status.get('phase_id')) != self._cal_view:
                rows.append(('Phase changed: refresh required', None))
            for key in ('prompt', 'instruction', 'reason', 'review'):
                if status.get(key):
                    text = status[key] if isinstance(status[key], str) else json.dumps(status[key], ensure_ascii=False)
                    rows.extend((line, None) for line in textwrap.wrap(self.clean(text, 480), 36))
            rows.extend([('Refresh phase', ('cal_refresh',)),
                         (self.t('Confirm'), ('cal_confirm', token, phase)),
                         (self.t('Cancel'), ('cal_cancel', token, phase))])
            return self.t('Autocalibration'), self._notice(rows)
        if self.page == 'settings':
            labels = {'language': 'Language', 'light_mode': 'Light', 'sound': 'Buzzer',
                      'sleep_mode': 'Sleep Mode', 'sleep_light': 'Sleep light',
                      'sort_mode': 'Models sorting', 'full_platform_preheat': 'Full platform preheating'}
            if native:
                labels.pop('language', None)
                labels.pop('sleep_mode', None)
                labels.pop('sleep_light', None)
            return self.t('Settings'), self._notice(back + [
                (self.t(label) + ': ' + str(self.nvm.get_setting(key, '?')), ('setting', key))
                for key, label in labels.items()])
        if self.page.startswith('setting_'):
            key = self.page[8:]
            choices = self.nvm.get_status(now).get('setting_choices', {}).get(key, [])
            rows = [(self.t('Back'), ('page', 'settings'))]
            for choice in choices:
                if isinstance(choice, dict):
                    value, label = choice.get('value'), choice.get('label', str(choice.get('value')))
                elif isinstance(choice, (list, tuple)) and len(choice) == 2:
                    value, label = choice
                else:
                    value, label = choice, str(choice)
                rows.append((self.t(str(label)), ('set', key, value)))
            return key, self._notice(rows)
        if self.page == 'stock_atlas' and ui is not None:
            return 'M300 stock / M11', back + ui.list_atlas()
        if self.page == 'stock_detail' and ui is not None:
            entry = ui.item(self._atlas_address)
            if entry is None:
                return 'M300 stock / M11', back + [('Unknown source record', None)]
            locale = ui.language().lower()
            rows = back + [
                (entry['translations'].get(locale, entry['source_en']), None),
                ('Stock RAM ' + entry['ram_address'], None),
                ('Parity: ' + entry['historical_parity'], None),
                ('Source callback: ' + str(entry['source_callback']), None),
            ]
            if entry['safe_navigation_page']:
                rows.append(('Open adapted page', ('atlas_open',entry['ram_address'])))
            else:
                rows.append(('No independent action / documented', None))
            return 'Stock record / M11', rows
        if self.page == 'information':
            status = self.nvm.get_status(now)
            hardware = getattr(getattr(self.job, 'board', None), 'hardware', None)
            hw = hardware.get_status() if hardware is not None else {}
            return self.t('Information'), self._notice(back + [
                ('M300_CLASSIC / M11' if ui is not None else 'M300_CLASSIC / M07', None),
                (self.MENU_REVISION, None),
                ('Hardware: ' + str(hw.get('hardware_label') or 'unavailable'), None),
                ('Z %s steps/mm' % hw.get('effective_z_steps_per_mm', '?'), None),
                ('Z profile: ' + str(hw.get('z_profile', 'config')), None),
                ('Serial: not inferred', None),
                ('NVM: ' + str(status.get('source', 'host JSON')), None),
                (self.clean(status.get('identity', {})), None),
                (self.clean(status.get('counters', {})), None),
                (self.t('Help'), ('page', 'help'))] +
                ([('Stock menu atlas / M11', ('page','stock_atlas'))] if ui is not None else []))
        if self.page == 'help':
            return self.t('Help'), back + [
                ('Rotate: select / Click: open', None),
                ('Long press: return to menu', None),
                ('Models: select, check, confirm', None),
                ('Pause preserves one job session', None),
                ('Wake does not reheat or home', None),
                ('Fault: inspect before restart', None),
                ('LAB: hardware still unqualified', None)]
        if self.page == 'diagnostics':
            return 'Diagnostics', back + [('Board', ('oled', 'board')),
                ('Temperatures', ('oled', 'temps')), ('Inputs', ('oled', 'inputs')),
                ('SD status', ('page', 'sd_status')), ('Service status', ('page', 'service_status'))] + ([('OLED link / M10', ('oled', 'oled_link'))] if self.printer.lookup_object('m300_oled_link', None) is not None else [])
        if self.page in ('sd_status', 'service_status'):
            obj = self._service('m300_sd') if self.page == 'sd_status' else self.maintenance
            return self.page, back + [(self.clean(k + ': ' + str(v), 240), None)
                for k, v in obj.get_status(now).items() if k not in ('cid', 'csd')]
        return 'M300', back

    def _browse(self, source, directory):
        generation = self.generation
        def checkpoint():
            if generation != self.generation or self.printer.is_shutdown():
                raise self._error('browser request expired')
        self._busy = True
        try:
            browser = self.printer.lookup_object('m300_browser', None)
            if browser is not None:
                listing = browser.list_files(source, directory, checkpoint=checkpoint)
                self._browser_generation = listing['generation']
                entries = [dict(name=e.name, path=e.path, is_dir=e.is_dir,
                                size=e.size, mtime=e.mtime) for e in browser.catalog.entries]
            elif source == 'host':
                entries = self.job.sd.v_sd.executor.submit(host_entries, self.job.sd.root,
                    directory, self.nvm.get_setting('sort_mode', 'NAME'))
            elif source == 'sd':
                entries = card_entries(self._service('m300_sd').list_files(
                    '/' + directory, checkpoint=checkpoint),
                                       self.nvm.get_setting('sort_mode', 'NAME'))
            else:
                raise self._error('unknown file source')
            checkpoint()
            self._navigate('browser')
            self._source, self._directory, self._entries = source, directory, list(entries)
        finally:
            self._busy = False

    def _select_file(self, source, path):
        models = self.printer.lookup_object('m300_models', None)
        if models is not None:
            browser = self._service('m300_browser')
            if (source != browser.catalog.source
                    or self._browser_generation != browser.catalog.generation):
                raise self._error('browser listing expired; reopen the directory')
            index = next((i for i, entry in enumerate(browser.catalog.entries)
                          if entry.path == path and not entry.is_dir), None)
            if index is None:
                raise self._error('file no longer belongs to the displayed listing')
            browser.native_preview(self._browser_generation, index)
            self._navigate('model_file')
            return
        generation = self.generation
        self._repeat_identity = None
        self._busy = True
        try:
            browser = self.printer.lookup_object('m300_browser', None)
            if browser is None:
                p = self.job.sd.select(('sd:/' if source == 'sd' else '') + path)
            else:
                # Repeat performs a new listing; normal selection retains its lease.
                if self.page != 'browser':
                    directory = path.rsplit('/', 1)[0] if '/' in path else ''
                    listing = browser.list_files(source, directory)
                    self._browser_generation = listing['generation']
                if (browser.catalog.source != source
                        or browser.catalog.generation != self._browser_generation):
                    raise self._error('browser listing expired; list the directory again')
                matches = [i for i, e in enumerate(browser.catalog.entries)
                           if e.path == path and not e.is_dir]
                if len(matches) != 1:
                    raise self._error('file no longer belongs to the displayed listing')
                browser.preview_file(self._browser_generation, matches[0])
                p = self.job.sd.selected
            if generation != self.generation or self.printer.is_shutdown():
                if self.job.sd.selected is p:
                    self.job.sd.cancel()
                raise self._error('selection expired while preparing the file')
            self._preview = p
            self._navigate('preview')
        finally:
            self._busy = False

    def _confirmation(self, label, action):
        self._navigate('confirm')
        self._confirm = (label, action)

    def _required_temp(self, kind):
        value = self._temperature[kind]
        if value is None:
            raise self._error('select an explicit ' + kind + ' temperature first')
        return value

    @staticmethod
    def _script_procedure(script):
        words = script.strip().upper().split()
        if not words:
            return None
        command = words[0]
        if command == 'G28':
            axes = ''.join(axis for axis in 'XYZ' if len(words)==1 or axis in words[1:])
            operation = {'X':'HOME_X','Y':'HOME_Y','Z':'HOME_Z',
                         'XY':'HOME_XY','XYZ':'HOME_ALL'}.get(axes)
            return ('m300_motion',operation) if operation else None
        return {'ZORTRAX_HOME_XY':('m300_motion','HOME_XY'),
                'ZORTRAX_HOME_Z':('m300_motion','HOME_Z'),
                'ZORTRAX_HOME_ALL':('m300_motion','HOME_ALL'),
                'ZORTRAX_LEVEL':('m300_calibration',None),
                'ZORTRAX_HEAT':('m300_maintenance','HOTEND'),
                'ZORTRAX_LOAD':('m300_filament','LOAD'),
                'ZORTRAX_UNLOAD':('m300_filament','UNLOAD'),
                'ZORTRAX_CHANGE':('m300_filament','CHANGE'),
                'ZORTRAX_FAN_TEST_START':('m300_fans','FAN_TEST'),
                'ZORTRAX_FAN_UPPER':('m300_fans','FAN_TEST'),
                'ZORTRAX_FAN_LOWER':('m300_fans','FAN_TEST')}.get(command)

    @staticmethod
    def _procedure_snapshot(service, now):
        try:
            status = service.get_status(now) if service is not None else {}
            return status if isinstance(status, dict) else {}
        except Exception:
            return {}  # Optional UI bookkeeping must not interrupt a command.

    def _native_script(self, script, origin=None):
        # Run through the ordinary native G-code mutex. Revalidate the view
        # AFTER acquiring it, so a delayed click cannot outlive navigation or
        # restart. The OLED serial/ACK callback never waits for this command.
        generation = self.generation
        origin = self._panel_origin() if origin is None else origin
        procedure = self._script_procedure(script)
        def execute(now):
            with self.gcode.get_mutex():
                if generation != self.generation or self.printer.is_shutdown():
                    return
                saved = False
                hint = None
                if procedure is not None:
                    owner, operation = procedure
                    service = self.printer.lookup_object(owner, None)
                    before = self._procedure_snapshot(service, now)
                    hint = dict(origin=origin, owner=owner, operation=operation,
                                generation=generation, previous_token=before.get('session_token'))
                    self._procedure_launch = hint
                try:
                    prefix = 'SAVE_GCODE_STATE NAME=M300_UI_NATIVE\n'
                    if script.startswith(prefix):
                        self.gcode.run_script_from_command(prefix.strip())
                        saved = True
                        self.gcode.run_script_from_command(script[len(prefix):])
                    else:
                        self.gcode.run_script_from_command(script)
                except self.printer.command_error as exc:
                    self.reason = str(exc)
                    if getattr(self, '_procedure_launch', None) is hint:
                        self._procedure_launch = None
                finally:
                    if hint is not None and getattr(self, '_procedure_launch', None) is hint:
                        status = self._procedure_snapshot(service, self.reactor.monotonic())
                        if not status.get('busy'):
                            self._procedure_launch = None
                    if saved and not self.printer.is_shutdown():
                        self.gcode.run_script_from_command(
                            'RESTORE_GCODE_STATE NAME=M300_UI_NATIVE MOVE=0')
        self.reactor.register_callback(execute)

    def select(self, action, now):
        if action is None:
            return None
        if not isinstance(action, tuple) or not action:
            raise self._error('invalid menu action')
        if self._busy:
            self.reason = 'Menu I/O is in progress; wait before choosing another action.'
            return None
        self.maintenance.activity()
        self.reason = ''
        try:
            kind = action[0]
            if kind == 'native_gcode':
                if not getattr(getattr(getattr(self, 'job', None), 'board', None), 'native_control', False):
                    raise self._error('native controls are not active')
                self._native_script(action[1])
            elif kind == 'procedure_return':
                view = self._service('m300_procedures').view(now)
                if (view['owner'], view['token']) != tuple(action[1:3]) or view['busy']:
                    raise self._error('procedure changed; review the current screen')
                operation = view['snapshots'][view['owner']].get('operation')
                if self.return_from_procedure(view['owner'], operation, view['token'], explicit=True):
                    return '_procedure_view_restored'
            elif kind == 'platform_hold':
                # The raw acknowledged physical press owns this gesture.
                # The short/long event delivered on release never jogs twice.
                return None
            elif kind == 'page':
                target = action[1]
                card = self.printer.lookup_object('m300_sd', None)
                if (target == 'models' and self.printer.lookup_object('m300_models', None) is not None
                        and getattr(card, 'qualified', False)):
                    self._navigate('models')
                    self._browse('sd', '')
                else:
                    self._navigate(target)
            elif kind == 'model_cancel':
                if action[1] is not None:
                    self._service('m300_models').cancel(action[1])
                self._navigate('browser', remember=False)
            elif kind == 'model_start':
                generation = self.generation
                self._busy = True
                try:
                    with self.gcode.get_mutex():
                        if self.generation != generation or self.printer.is_shutdown():
                            raise self._error('model start expired')
                        self._service('m300_models').start(action[1])
                    self._navigate('native_job')
                finally:
                    self._busy = False
            elif kind == 'procedure_action':
                self._service('m300_procedures').action(action[1], action[2])
            elif kind == 'fan_test':
                self._service('m300_fans').start_test(action[1])
                self._navigate('fans')
            elif kind == 'fan_cancel':
                self._service('m300_fans').cancel(action[1])
            elif kind == 'fan_set':
                if getattr(getattr(getattr(self, 'job', None), 'board', None), 'native_control', False):
                    self._native_script('M106 S%d' % round(255. * action[1] / 100.))
                else:
                    self._service('m300_fans').set_print(action[1])
            elif kind == 'ui_back':
                ui = self._ui()
                if ui is None or action[1] != self.generation:
                    raise self._error('M11 expired or unavailable back navigation')
                self._navigate(ui.parent(self.page), remember=False)
            elif kind == 'atlas_item':
                ui = self._ui()
                if ui is None or ui.item(action[1]) is None:
                    raise self._error('unknown or unavailable source menu record')
                self._atlas_address = action[1]
                self._navigate('stock_detail')
            elif kind == 'atlas_open':
                ui = self._ui()
                entry = None if ui is None else ui.item(action[1])
                if entry is None or not entry['safe_navigation_page']:
                    raise self._error('M11 stock entry has no adapted action')
                self._navigate(entry['safe_navigation_page'])
            elif kind == 'oled':
                return action[1]
            elif kind == 'wake':
                self.maintenance.wake()
                self.home()
            elif kind == 'browse':
                self._browse(action[1], action[2])
            elif kind in ('directory', 'file'):
                if action[3] != self.generation:
                    raise self._error('file list changed; choose the entry again')
                if kind == 'directory':
                    self._browse(action[1], action[2])
                else:
                    self._select_file(action[1], action[2])
            elif kind == 'confirm_print':
                p = self._preview
                if p is None or p.identity != action[1] or self.job.sd.selected is not p or p.closed:
                    raise self._error('checked file selection changed')
                label = ('Remove finished model, then start: ' if p.identity == self._repeat_identity
                         else 'Start: ') + self.clean(p.filename)
                self._confirmation(label, ('print', p.identity))
            elif kind == 'confirm_sleep':
                self._confirmation('Sleep: heat off, motors released', ('sleep',))
            elif kind == 'confirmed':
                if action[1] != self.generation or self._confirm is None:
                    raise self._error('confirmation expired')
                _, request = self._confirm
                self._confirm = None
                if request[0] == 'print':
                    p = self._preview
                    if p is None or p.identity != request[1] or self.job.sd.selected is not p or p.closed:
                        raise self._error('checked snapshot no longer matches confirmation')
                    generation = self.generation
                    self._busy = True
                    try:
                        browser = self.printer.lookup_object('m300_browser', None)
                        if browser is not None:
                            browser.validate_preview(p)
                        if generation != self.generation or self.printer.is_shutdown():
                            raise self._error('print confirmation expired during source check')
                        cycle = self.printer.lookup_object('m300_cycle', self.cycle)
                        if cycle is not None:
                            cycle.request('START_SELECTED', identity=p.identity)
                        else:
                            self.job.sd.start_selected()
                    finally:
                        self._busy = False
                    self._preview = None
                    self._navigate('main')
                    return 'job'
                self.maintenance.sleep()
                self.home()
            elif kind == 'cycle_clean':
                if self.cycle is None:
                    raise self._error('M08 cycle is unavailable')
                self.cycle.request('CONFIRM_CLEAN', token=action[1])
                self.reason = 'Resume clean confirmed; bounded return may continue.'
                return 'job'
            elif kind == 'repeat':
                if not self._last_file or self.job.machine.state != 'COMPLETE':
                    raise self._error('repeat requires a successfully completed previous job')
                source, path = self._last_file
                self._select_file(source, path)
                self._repeat_identity = self._preview.identity
                self.reason = 'Remove the finished model; confirm the new checked snapshot.'
            elif kind == 'temperatures':
                self._return_page = action[2]
                self._navigate('temperature_' + action[1])
            elif kind == 'temp':
                self._temperature[action[1]] = action[2]
                self._navigate(action[3])
            elif kind == 'material':
                # M09 is optional: legacy M08 retains the original M03 route.
                service = self.printer.lookup_object('m300_material_ui', None)
                if service is None:
                    service = self._service('m300_filament')
                filament = self._service('m300_filament')
                temp = None if action[1] == 'CHANGE' else filament.procedure_temperature
                service.start(action[1], temperature=temp)
                return 'filament'
            elif kind == 'material_action':
                if tuple(action[2:4]) != self._material_view:
                    raise self._error('material view changed; refresh before confirming')
                facade = self._service('m300_material_ui')
                facade.act(action[1], action[2], action[3])
                self._navigate('material_status')
            elif kind == 'motion_xy_arm':
                # Deliberate physical operator affirmation, NEVER a sensor measurement.
                outcome=self._service('m300_motion').arm_xy_clearance(5.)
                self.reason = 'Confirmed operator >=5mm XY gap (60s), MCU ARM requested. No movement.'
            elif kind in ('motion_home_x','motion_home_y','motion_home_xy','motion_home_z','motion_home_xyz'):
                origin = self._panel_origin()
                axes={'motion_home_x':'x','motion_home_y':'y',
                      'motion_home_xy':'xy','motion_home_z':'z','motion_home_xyz':'xyz'}[kind]
                self._navigate('motion_status')
                oled = self.printer.lookup_object('m300_oled', None)
                if oled is not None:
                    oled.page, oled.selection, oled.render_at = 'm04', 0, 0.
                motion = self._service('m300_motion')
                if getattr(motion, 'normal_control', False):
                    self._native_script('G28 ' + ' '.join(axes.upper()), origin=origin)
                    self.reason = 'Homing %s requested.' % axes.upper()
                else:
                    motion.home(axes=axes)
                    self.reason = 'Homing %s ended. Check PC7, axis reference and status.' % axes.upper()
            elif kind == 'motion_home':
                # Old M11 action cached on screen before the upgrade is not allowed.
                raise self._error('Full G28 XYZ disabled for unqualified Z400. Use XY then Z.')
            elif kind == 'motion_jog':
                motion = self._service('m300_motion')
                token = motion.start_jog()
                try:
                    self.present_motion_jog(motion, token)
                except Exception:
                    motion.cancel('encoder jog view could not be presented', token=token)
                    raise
            elif kind == 'motion_stop':
                self._service('m300_motion').cancel('operator menu cancel')
                self._motion_jog_token = None
                self._navigate('motion_status')
                self.reason = 'Motion cancelled; check position validity.'
            elif kind == 'service':
                op = action[1]
                if getattr(getattr(getattr(self, 'job', None), 'board', None), 'native_control', False):
                    if op not in ('HOTEND', 'BED'):
                        raise self._error('use native controls for this operation')
                    value = action[2] if len(action) > 2 else self._required_temp(op)
                    self._native_script('SET_HEATER_TEMPERATURE HEATER=%s TARGET=%g' % (
                        'extruder' if op == 'HOTEND' else 'heater_bed', value))
                    return None
                fans = self.printer.lookup_object('m300_fans', None)
                if fans is not None and op in ('FAN_PRINT', 'FAN_HOTEND'):
                    fans.start_test(op[4:])
                    self._navigate('fans')
                    return None
                value = (action[2] if len(action) > 2 else self._required_temp(op)
                         if op in ('HOTEND', 'BED') else None)
                self.maintenance.start(op, value)
                self.reason = 'Accepted: ' + op
            elif kind == 'service_stop':
                self.maintenance.stop()
                self.reason = 'Service stopped; thermal targets are zero.'
            elif kind == 'cal_start':
                calibration = self._service('m300_calibration')
                calibration.start(None)
                self._cal_refresh(now)
            elif kind == 'cal_refresh':
                self._cal_refresh(now)
            elif kind == 'cal_confirm':
                self._service('m300_calibration').confirm(action[1], action[2])
                self.reason = 'Phase accepted; refresh to confirm a later phase.'
            elif kind == 'cal_cancel':
                self._service('m300_calibration').cancel('operator', token=action[1], phase=action[2])
                self.reason = 'Calibration cancelled.'
            elif kind == 'setting':
                self._navigate('setting_' + action[1])
            elif kind == 'set':
                generation = self.generation
                settings = self.printer.lookup_object('m300_settings', None)
                shared = settings is not None and getattr(self.job.board, 'native_control', False)
                self._busy = True
                try:
                    if shared:
                        settings.set_option(action[1], action[2])
                    else:
                        self.nvm.set_setting(action[1], action[2])
                finally:
                    self._busy = False
                if not shared and generation == self.generation:
                    self._navigate('settings')
            else:
                raise self._error('unsupported menu action')
        except Exception as exc:
            self.reason = self.clean(str(exc), 240)
            logging.info('M300 menu refused action: %s', self.reason)
        return None

    def _cal_refresh(self, now):
        status = self._service('m300_calibration').get_status(now)
        self._cal_view = (status.get('session_token'), status.get('phase_id'))
        self._navigate('calibration')

    def job_completed(self, filename, seconds):
        if filename.startswith('sd:/'):
            self._last_file = ('sd', filename[4:])
        else:
            self._last_file = ('host', filename)

    def get_status(self, now):
        return {'page': self.page, 'generation': self.generation, 'busy': self._busy,
                'reason': self.reason, 'file_source': self._source,
                'directory': self._directory, 'entries': len(self._entries),
                'preview_identity': None if self._preview is None else self._preview.identity,
                'calibration_view': self._cal_view, 'motion_jog_token': self._motion_jog_token,
                'material_view': self._material_view,
                'homing_ui_abi': self.HOMING_UI_ABI,
                'menu_revision': self.MENU_REVISION,
                'm11_installed': self._ui() is not None,
                'hardware_qualified': False}

    def cmd_status(self, gcmd):
        gcmd.respond_info('ZORTRAX_MENU ' + json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))

    def cmd_menu(self, gcmd):
        self.home()
        oled = self._service('m300_oled')
        oled.page, oled.selection, oled.render_at = 'm04', 0, 0.


def load_config(config):
    return M300Menu(config)
