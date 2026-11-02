# SPDX-License-Identifier: GPL-3.0-or-later
"""M08 22-state supervisory executor for classic M300.

The supervisor owns user-level phase/arbitration only. It delegates file/heat
and print motion to M02, material transport to M03, homing to M06 and platform
calibration to M07. It never adds a GPIO/ADC/stepper owner and never bypasses
those modules' gates or session tokens.
"""
from collections import deque
import json

from .m300_cycle_state import STATES, STATE_SET

PERIOD = .100

class M300Cycle:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.job = self.printer.load_object(config, 'm300_job')
        self.filament = self.printer.load_object(config, 'm300_filament')
        self.motion = self.printer.load_object(config, 'm300_motion')
        self.calibration = self.printer.load_object(config, 'm300_calibration')
        self.qualified = config.getboolean('qualified', False)
        self.ready = False
        self.installed = False
        self.state = 'IDLE'
        self.session_generation = 0
        self.last_reason = ''
        self.last_completed = None
        self._identity = None
        self._history = deque(maxlen=256)
        self._actions = deque(maxlen=256)
        self._timer = self.reactor.register_timer(self._tick)
        self.printer.register_event_handler('klippy:connect', self._connect)
        self.printer.register_event_handler('klippy:ready', self._ready)
        self.printer.register_event_handler('klippy:shutdown', self._shutdown)
        self.printer.register_event_handler('klippy:disconnect', self._shutdown)
        self.printer.register_event_handler('gcode:request_restart', self._restart)
        self.printer.register_event_handler('m300:job_completed', self._job_completed)
        self.gcode.register_command('ZORTRAX_CYCLE_STATUS', self.cmd_status, when_not_ready=True)
        self.gcode.register_command('ZORTRAX_CYCLE_ACTION', self.cmd_action)

    def _error(self, text):
        return self.printer.command_error('M300 M08 cycle: ' + str(text))

    def _connect(self):
        # A complete M08 profile must expose all four delegated owners.
        required = {'job': self.job, 'filament': self.filament,
                    'motion': self.motion, 'calibration': self.calibration}
        if any(value is None for value in required.values()):
            raise self.config.error('M08 requires M02/M03/M06/M07 owners')
        if not getattr(self.job, 'm08_cycle_enabled', False):
            raise self.config.error('M08 cycle requires m300_job m08_cycle_enabled=True')
        if len(STATES) != 22 or len(STATE_SET) != 22:
            raise self.config.error('M08 neutral cycle must contain exactly 22 states')
        self.installed = True

    def _ready(self):
        self.ready = True
        if getattr(self.job.board, 'native_control', False):
            return
        self.reactor.update_timer(self._timer, self.reactor.NOW)

    def _shutdown(self, *args):
        self.ready = False
        self._publish('FAULT', 'host lifecycle invalidated M08 session')
        self.reactor.update_timer(self._timer, self.reactor.NEVER)

    def _restart(self, *args):
        self.ready = False
        self._publish('FAULT', 'restart invalidated M08 session')

    def _job_completed(self, filename, seconds):
        self.last_completed = {'filename': filename, 'seconds': float(seconds),
                               'job_token': self.job.machine.token}

    def _material_state(self):
        fs = self.filament.machine.state
        mode = self.filament.machine.mode
        if not self.filament.machine.active and fs not in ('COMPLETE', 'CANCELLED', 'FAULT'):
            return None
        if mode == 'LOAD':
            if fs in ('HEATING', 'REHEATING'): return 'LOAD_HEAT'
            if fs in ('WAIT_INSERT', 'WAIT_PURGE'): return 'LOAD_READY'
            if fs in ('LOADING', 'PURGING', 'COMPLETING'): return 'LOAD_RUN'
        if mode == 'UNLOAD':
            if fs in ('HEATING', 'REHEATING'): return 'UNLOAD_HEAT'
            if fs == 'WAIT_UNLOAD': return 'UNLOAD_READY'
            if fs in ('UNLOADING', 'COMPLETING'): return 'UNLOAD_RUN'
        if mode == 'CHANGE':
            if fs in ('WAIT_PAUSE', 'HEATING', 'REHEATING', 'WAIT_UNLOAD', 'UNLOADING'):
                return 'CHANGE_UNLOAD'
            if fs == 'WAIT_INSERT': return 'CHANGE_INSERT'
            if fs in ('LOADING', 'WAIT_PURGE', 'PURGING', 'COMPLETING'):
                return 'CHANGE_LOAD'
        if fs == 'FAULT': return 'FAULT'
        return None

    def _derive(self, now):
        js = self.job.machine.state
        # Terminal job outcomes have priority over a completed/cancelled helper.
        if js == 'FAULT': return 'FAULT', self.job.machine.reason or ''
        if js == 'FILE_ERROR': return 'FILE_ERROR', self.job.machine.reason or ''
        if js == 'CANCELLED': return 'CANCELLED', self.job.machine.reason or ''
        material = self._material_state()
        if material == 'FAULT': return 'FAULT', self.filament.machine.reason or ''
        if material is not None and (self.filament.machine.active or js in ('IDLE','PAUSED','PRINTING','PAUSING')):
            return material, self.filament.machine.reason or ''
        if js in ('PREFLIGHT', 'HEATING', 'HOMING'):
            return 'PREPARING_PRINT', ''
        if js == 'PRINTING': return 'PRINTING', ''
        if js == 'PAUSING': return 'PAUSE_PARK', ''
        if js == 'PAUSED': return 'PAUSED', ''
        if js == 'RESUMING': return 'RESUME_HEAT', ''
        if js == 'RETURNING':
            phase = getattr(self.job, '_resume_subphase', None)
            return ({'PURGE':'RESUME_PURGE', 'CLEAN':'RESUME_CLEAN',
                     'RETURN':'RESUME_RETURN'}.get(phase, 'RESUME_RETURN'), '')
        if js in ('COMPLETING', 'COMPLETE'): return 'COMPLETE', ''
        if js == 'CANCELLING': return 'CANCELLED', self.job.machine.reason or ''
        return 'IDLE', ''

    def _identity_now(self):
        if self.job.machine.active or self.job.machine.state != 'IDLE':
            return ('job', self.job.machine.token)
        if self.filament.machine.active:
            return ('filament', self.filament.machine.token)
        return None

    def _publish(self, state, reason=''):
        if state not in STATE_SET:
            raise self._error('derived unknown state ' + str(state))
        identity = self._identity_now()
        if identity != self._identity:
            self._identity = identity
            self.session_generation += 1
        if state != self.state or reason != self.last_reason:
            self._history.append({'from': self.state, 'to': state,
                                  'at': self.reactor.monotonic(),
                                  'session_generation': self.session_generation,
                                  'identity': identity, 'reason': reason})
            self.state, self.last_reason = state, reason

    def _tick(self, now):
        if not self.ready or self.printer.is_shutdown():
            return self.reactor.NEVER
        state, reason = self._derive(now)
        self._publish(state, reason)
        return now + PERIOD

    def _record_action(self, action, **detail):
        row = {'action': action, 'at': self.reactor.monotonic(),
               'state_before': self.state, 'job_token': self.job.machine.token,
               'filament_token': self.filament.machine.token}
        row.update(detail)
        self._actions.append(row)
        return row

    def _motion_status(self):
        try:
            status = self.motion.get_status(self.reactor.monotonic())
        except Exception as exc:
            raise self._error('M06 motion status unavailable: ' + str(exc))
        if (not isinstance(status, dict) or not isinstance(status.get('busy'), bool)
                or not isinstance(status.get('position_valid'), bool)):
            raise self._error('M06 motion returned incomplete status')
        return status

    def _ensure_start_position(self):
        """Delegate fresh-session homing to M06 when XYZ trust was lost.

        M08 never fakes coordinates or bypasses the M06 qualification gates.
        This is intentionally before M02 creates a fresh job token: M02 itself
        refuses an untrusted position and M06 is the sole homing owner.
        """
        status = self._motion_status()
        if status['position_valid']:
            return False
        if status['busy']:
            raise self._error('M06 motion is busy before fresh job')
        home = getattr(self.motion, 'home', None)
        if not callable(home):
            raise self._error('M06 motion cannot establish a fresh position')
        self._publish('PREPARING_PRINT', 'M08 delegated fresh-session homing to M06')
        home(axes='xyz')
        status = self._motion_status()
        if status['busy'] or not status['position_valid']:
            raise self._error('M06 did not establish a valid XYZ position')
        return True

    def request(self, action, **params):
        if not self.ready or self.printer.is_shutdown():
            raise self._error('host is not ready')
        action = str(action).upper()
        self._publish(*self._derive(self.reactor.monotonic()))
        row = self._record_action(action, params=dict(params))
        if action == 'START_SELECTED':
            expected = params.get('identity')
            selected = self.job.sd.selected
            if selected is None or selected.closed:
                raise self._error('no checked file is selected')
            if expected is not None and selected.identity != expected:
                raise self._error('selected snapshot identity changed')
            self._ensure_start_position()
            before = self.job.machine.token
            self.job.sd.start_selected()
            if self.job.machine.token <= before:
                raise self._error('fresh start did not create a new job token')
        elif action == 'PAUSE':
            self.job.pause('M08 cycle request')
        elif action == 'RESUME':
            self.job.resume()
        elif action in ('STOP', 'CANCEL'):
            self.job.cancel('M08 ' + action.lower())
        elif action == 'CONFIRM_CLEAN':
            self.job.confirm_resume_clean(params.get('token', self.job.machine.token))
        elif action == 'CHANGE':
            self.filament.start('CHANGE', temperature=params.get('temperature'))
        elif action in ('LOAD', 'UNLOAD'):
            if 'temperature' not in params:
                raise self._error(action + ' requires explicit temperature')
            self.filament.start(action, temperature=float(params['temperature']))
        elif action in ('FILAMENT_CONFIRM', 'FILAMENT_PURGE'):
            token = params.get('token', self.filament.machine.token)
            phase = params.get('phase', self.filament.machine.phase_id)
            if action == 'FILAMENT_CONFIRM':
                self.filament.confirm(token, phase)
            else:
                self.filament.purge(token, phase)
        elif action == 'REPRINT':
            if self.last_completed is None or self.job.machine.state != 'COMPLETE':
                raise self._error('REPRINT requires a completed M08 job')
            filename = self.last_completed['filename']
            old = self.job.machine.token
            self.job.sd.select(filename)
            self._ensure_start_position()
            self.job.sd.start_selected()
            if self.job.machine.token <= old:
                raise self._error('REPRINT did not create a new session')
        else:
            raise self._error('unsupported M08 action: ' + action)
        self._publish(*self._derive(self.reactor.monotonic()))
        row['state_after'] = self.state
        return row

    def get_status(self, now):
        state, reason = self._derive(now)
        self._publish(state, reason)
        job = self.job.get_status(now)
        filament = self.filament.get_status(now)
        return {'version': '0.8.0-LAB_M01_M02_M03_M04_M05_M06_M07_M08',
                'model': 'M300_CLASSIC', 'state': self.state,
                'state_count': len(STATES), 'states': list(STATES),
                'session_generation': self.session_generation,
                'reason': self.last_reason, 'ready': self.ready and not self.printer.is_shutdown(),
                'installed': self.installed, 'qualified': self.qualified,
                'hardware_qualified': False, 'automatic_arm': False,
                'job_token': self.job.machine.token, 'job_state': self.job.machine.state,
                'filament_token': self.filament.machine.token,
                'filament_state': self.filament.machine.state,
                'resume_phase': job.get('resume_phase'),
                'can_pause': job.get('can_pause', False),
                'can_resume': job.get('can_resume', False),
                'can_confirm_resume_clean': job.get('can_confirm_resume_clean', False),
                'can_cancel': job.get('can_cancel', False),
                'last_completed': self.last_completed,
                'history': list(self._history), 'actions': list(self._actions)}

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_CYCLE ' + json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))

    def cmd_action(self, gcmd):
        action = gcmd.get('ACTION')
        params = {}
        for key in ('TOKEN','PHASE'):
            value = gcmd.get_int(key, None, minval=0)
            if value is not None: params[key.lower()] = value
        temp = gcmd.get_float('TEMP', None)
        if temp is not None: params['temperature'] = temp
        result = self.request(action, **params)
        gcmd.respond_info('M300_CYCLE_ACTION ' + json.dumps(result, sort_keys=True))

def load_config(config):
    return M300Cycle(config)
