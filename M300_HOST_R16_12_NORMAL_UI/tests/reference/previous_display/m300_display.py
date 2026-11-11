# SPDX-License-Identifier: GPL-3.0-or-later
"""Display-only inactivity. Native thermal, motion and printer sleep untouched."""
import json
import logging
import math

from .m300_display_stream import AWAKE, DIM, OFF, DisplayStream

REVISION = '0.1.0-M300-DISPLAY-IDLE'


class M300Display:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.oled = self.printer.load_object(config, 'm300_oled')
        self.timeout = config.getfloat('timeout', 300., minval=5., maxval=86400.)
        if not math.isfinite(self.timeout):
            raise config.error('Display timeout must be finite')
        self.normal = config.getint('normal_contrast', 159, minval=1, maxval=159)
        self.dim = config.getint('dim_contrast', 32, minval=1, maxval=self.normal)
        self.stream = None
        self.connected = False
        self.error = None
        self.last_activity = self.reactor.monotonic()
        self.last_source = 'startup'
        self.busy = False
        self._consume_gesture = False
        self._hooks_installed = False
        self.timer = self.reactor.register_timer(self._tick)
        for event, cb in (('klippy:ready', self._ready),
                          ('klippy:shutdown', self._stop),
                          ('klippy:disconnect', self._stop),
                          ('gcode:command_error', self._command_error)):
            self.printer.register_event_handler(event, cb)
        self.gcode.register_command('ZORTRAX_DISPLAY_STATUS', self.cmd_status,
                                   when_not_ready=True)
        self.gcode.register_command('ZORTRAX_DISPLAY_WAKE', self.cmd_wake)

    def _ready(self):
        # Optional UI failure must not block native printer startup.
        try:
            base = self.oled.stream
            for name in ('step', 'ack', 'start', 'stop', 'request'):
                if not callable(getattr(base, name, None)):
                    raise ValueError('Unsupported OLED stream: ' + name)
            if not hasattr(self.oled, 'encoder') or not hasattr(self.oled, 'timer'):
                raise ValueError('Unsupported M300 OLED adapter')
            hooks = self.printer.lookup_object('webhooks')._endpoints
            if not callable(hooks.get('gcode/script')):
                raise ValueError('Unsupported Klipper G-code API')
            if not isinstance(base, DisplayStream):
                self.stream = DisplayStream(base, self.normal, self.dim)
                self.oled.stream = self.stream
            else:
                self.stream = base
            if not self._hooks_installed:
                for endpoint in ('gcode/script', 'gcode/restart',
                                 'gcode/firmware_restart'):
                    original = hooks.get(endpoint)
                    if original is None:
                        continue
                    def observed(request, original=original, endpoint=endpoint):
                        # This is the external API boundary. G-code from
                        # virtual_sdcard/macros never traverses this hook.
                        if endpoint != 'gcode/script' or any(
                                line.split(';', 1)[0].strip()
                                for line in request.get_str('script').splitlines()):
                            self.activity('operator_command')
                        return original(request)
                    hooks[endpoint] = observed
                original = self.oled.encoder.update
                def encoder_update(params, received_at):
                    events = original(params, received_at)
                    now = self.reactor.monotonic()
                    if (events is None or not isinstance(received_at, (int, float))
                            or not math.isfinite(received_at)
                            or not 0. <= now - received_at <= 1.):
                        return events
                    active = any(events.get(k, 0)
                                 for k in ('delta', 'presses', 'releases',
                                           'shorts', 'longs'))
                    dark = (self.stream.display_mode == OFF
                            or self.stream.requested_mode == OFF)
                    if active:
                        self.activity('encoder')
                        if dark:
                            self._consume_gesture = True
                    if self._consume_gesture:
                        # Consume the complete wake gesture, including long
                        # and release, so it cannot accept an unseen action.
                        result = dict(events)
                        for key in ('delta', 'presses', 'releases', 'shorts', 'longs'):
                            result[key] = 0
                        if not events.get('pressed'):
                            self._consume_gesture = False
                        return result
                    return events
                self.oled.encoder.update = encoder_update
                motion = self.printer.lookup_object('m300_motion', None)
                if motion is not None and callable(getattr(motion, 'panel_update', None)):
                    original_panel = motion.panel_update
                    def panel_update(snapshot, eventtime, token, view_current=False):
                        # Keep delivery of release/STOP; an invisible view
                        # must never grant a new hold-to-jog permission.
                        if (self._consume_gesture
                                or self.stream.display_mode == OFF
                                or self.stream.requested_mode == OFF):
                            view_current = False
                        return original_panel(snapshot, eventtime, token,
                                              view_current=view_current)
                    motion.panel_update = panel_update
                self._hooks_installed = True
            self.connected, self.error = True, None
            self._consume_gesture = False
            self.activity('ready')
            self.reactor.update_timer(self.timer, self.reactor.NOW)
        except Exception as exc:
            self.connected = False
            self.error = str(exc)
            logging.exception('Optional M300 display idle unavailable')

    def _stop(self, *args):
        self.connected = False
        self._consume_gesture = False
        self.reactor.update_timer(self.timer, self.reactor.NEVER)
        # Existing OLED/MCU lifecycle retains ownership of the local waiting
        # and error screen. No host command is sent after disconnect/shutdown.

    def _command_error(self, *args):
        self.activity('command_error')

    def activity(self, source):
        if not self.connected:
            return
        now = self.reactor.monotonic()
        self.last_activity, self.last_source = now, source
        self.stream.set_mode(AWAKE)
        self.oled.render_at = 0.
        self.reactor.update_timer(self.oled.timer, self.reactor.NOW)

    def _working(self, now):
        names = ('print_stats', 'm300_job', 'm300_filament',
                 'm300_calibration', 'm300_motion', 'm300_thermal', 'm300_fans')
        for name in names:
            obj = self.printer.lookup_object(name, None)
            if obj is None:
                continue
            try:
                status = obj.get_status(now)
                if (status.get('busy') or status.get('active')
                        or str(status.get('state', '')).lower()
                        in ('printing', 'paused')):
                    return True
            except Exception:
                # An unknown operation should remain visible, at dim level.
                return True
        toolhead = self.printer.lookup_object('toolhead', None)
        if toolhead is not None:
            try:
                print_time, estimated_time, empty = toolhead.check_busy(now)
                if not empty or print_time > estimated_time:
                    return True
            except Exception:
                return True
        for name in ('extruder', 'heater_bed'):
            heater = self.printer.lookup_object(name, None)
            if heater is not None:
                try:
                    if heater.get_status(now).get('target', 0.) > 0.:
                        return True
                except Exception:
                    return True
        return False

    def _tick(self, now):
        if not self.connected:
            return self.reactor.NEVER
        self.busy = self._working(now)
        desired = AWAKE
        if now - self.last_activity >= self.timeout:
            desired = DIM if self.busy else OFF
        if desired != self.stream.requested_mode:
            self.stream.set_mode(desired)
            self.reactor.update_timer(self.oled.timer, self.reactor.NOW)
        return now + 1.

    def get_status(self, now):
        return {'revision': REVISION, 'connected': self.connected,
                'error': self.error, 'timeout': self.timeout,
                'mode': self.stream.display_mode if self.stream else 'UNAVAILABLE',
                'requested_mode': self.stream.requested_mode if self.stream else None,
                'normal_contrast': self.normal, 'dim_contrast': self.dim,
                'inactive_seconds': max(0., now - self.last_activity),
                'last_activity': self.last_source, 'working': self.busy,
                'screen_only': True, 'hardware_verified': False,
                'wake_command_sources': ['Fluidd/Moonraker G-code API', 'encoder'],
                'changes': self.stream.display_changes if self.stream else 0}

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_DISPLAY ' + json.dumps(
            self.get_status(self.reactor.monotonic()), sort_keys=True))

    def cmd_wake(self, gcmd):
        self.activity('explicit_wake')


def load_config(config):
    return M300Display(config)
