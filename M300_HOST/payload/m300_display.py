# SPDX-License-Identifier: GPL-3.0-or-later
"""Display-only inactivity. Native thermal, motion and printer sleep untouched."""
import json
import logging
import math

from .m300_display_stream import AWAKE, DIM, OFF, DisplayStream
from .m300_display_oem import ENTERING_TEXT, load_moon, sleep_wire
from .m300_nvm import MAX_BRIGHTNESS

REVISION = '0.4.0-M300-BRIGHTNESS'


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
        self.brightness = MAX_BRIGHTNESS
        self.notice_seconds = config.getfloat('notice_seconds', 10.,
                                             minval=1., maxval=60.)
        if not math.isfinite(self.notice_seconds):
            raise config.error('Display notice duration must be finite')
        self.stream = None
        self.connected = False
        self.error = None
        self.last_activity = self.reactor.monotonic()
        self.last_source = 'startup'
        self.busy = False
        self.sleep_enabled = True
        self.phase = AWAKE
        self.notice_wire = None
        self._notice_shown_at = None
        self._notice_start_contrast = None
        self._presentation_wait = False
        self._maintenance_asleep = False
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
        self.printer.register_event_handler('m300:setting_changed', self._setting_changed)

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
            # Asset validation is optional-UI initialization, not a reason to
            # prevent native printer Ready if a local file is unavailable.
            from .m300_oled_render import Frame
            self.notice_wire = sleep_wire(Frame, load_moon())
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
                        if endpoint != 'gcode/script':
                            self.activity('operator_command')
                        else:
                            script = request.get_str('script')
                            if any(line.split(';', 1)[0].strip() for line in script.splitlines()):
                                self.activity('operator_command')
                            settings = self.printer.lookup_object('m300_settings', None)
                            handle = getattr(settings, 'try_web_script', None)
                            if handle is not None and handle(script):
                                return
                        return original(request)
                    hooks[endpoint] = observed
                original = self.oled.encoder.update
                original_render = self.oled._render
                def render(now):
                    if self.phase == 'ENTERING_SLEEP':
                        self.oled._presented_context = None
                        self.oled._presented_actions = None
                        self.stream.request(self.notice_wire, urgent=True)
                        return
                    return original_render(now)
                self.oled._render = render
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
                    self._sync_presentation()
                    guarded = (dark or self.phase == 'ENTERING_SLEEP'
                               or self._presentation_wait)
                    if active:
                        self.activity('encoder')
                        if guarded:
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
                                or self.phase == 'ENTERING_SLEEP'
                                or self._presentation_wait
                                or self.stream.display_mode == OFF
                                or self.stream.requested_mode == OFF):
                            view_current = False
                        return original_panel(snapshot, eventtime, token,
                                              view_current=view_current)
                    motion.panel_update = panel_update
                self._hooks_installed = True
            self.connected, self.error = True, None
            nvm = self.printer.lookup_object('m300_nvm', None)
            self.sleep_enabled = nvm is None or nvm.get_setting('sleep_mode', '15MIN') != 'OFF'
            if nvm is not None:
                self._set_brightness(nvm.get_setting('oled_brightness', MAX_BRIGHTNESS))
            self._consume_gesture = False
            self.activity('ready')
            self.reactor.update_timer(self.timer, self.reactor.NOW)
        except Exception as exc:
            self.connected = False
            self.error = str(exc)
            logging.exception('Optional M300 display idle unavailable')
            from .m300_error_codes import report
            report(self.printer, exc, source='m300_display')

    def _stop(self, *args):
        self.connected = False
        self._consume_gesture = False
        self.phase = 'DISCONNECTED'
        self._notice_shown_at = None
        self._presentation_wait = False
        self.reactor.update_timer(self.timer, self.reactor.NEVER)
        # Existing OLED/MCU lifecycle retains ownership of the local waiting
        # and error screen. No host command is sent after disconnect/shutdown.

    def _command_error(self, *args):
        self.activity('command_error')

    def _setting_changed(self, name, value):
        if name == 'sleep_mode':
            self.sleep_enabled = value != 'OFF'
            # Use the existing notice/wake/ACK path; preserve configured times.
            self.activity('sleep_setting')
        elif name == 'oled_brightness' and self.stream is not None:
            self._set_brightness(value)
            self.activity('brightness_setting')

    def _set_brightness(self, value):
        self.brightness = value
        self.stream.set_contrast(
            max(1, round(self.normal * value / MAX_BRIGHTNESS)),
            max(1, round(self.dim * value / MAX_BRIGHTNESS)))

    def activity(self, source):
        if not self.connected:
            return
        now = self.reactor.monotonic()
        self.last_activity, self.last_source = now, source
        self._leave_notice()
        self.phase = AWAKE
        self.stream.set_mode(AWAKE)
        self.oled.render_at = 0.
        self.reactor.update_timer(self.oled.timer, self.reactor.NOW)

    def _invalidate_view(self):
        self.oled._input_epoch = getattr(self.oled, '_input_epoch', 0) + 1
        self.oled._presented_context = self.oled._presented_actions = None
        self.oled.render_at = 0.

    def _leave_notice(self):
        if self.phase == 'ENTERING_SLEEP':
            self._notice_shown_at = None
            self.stream.set_dim_override(None)
            self._presentation_wait = True
            self._invalidate_view()

    def _sync_presentation(self):
        b = self.stream._base
        if (self._presentation_wait and b.ready and b.enabled
                and b.previous is not None and b.previous != self.notice_wire
                and b.operations is None and not self.stream.pending
                and not self.stream.inflight and self.stream.display_mode != OFF):
            self._presentation_wait = False

    def _begin_notice(self):
        self.phase = 'ENTERING_SLEEP'
        self._notice_shown_at = None
        self._notice_start_contrast = self.stream.display_contrast
        self.stream.set_dim_override(self._notice_start_contrast)
        self._invalidate_view()

    def _notice_mode(self, now):
        b = self.stream._base
        if not b.ready or b.previous != self.notice_wire:
            # Reinitialization requires a fresh acknowledged moon frame.
            self._notice_shown_at = None
            self.stream.set_dim_override(self._notice_start_contrast)
            return DIM
        if self._notice_shown_at is None:
            if (self.stream.display_mode != DIM or b.operations is not None
                    or self.stream.pending or self.stream.inflight):
                return DIM
            self._notice_shown_at = now
        fraction = (now - self._notice_shown_at) / self.notice_seconds
        if fraction >= 1.:
            self.stream.set_dim_override(None)
            self.phase = OFF
            return OFF
        step = int(fraction * MAX_BRIGHTNESS)
        contrast = 1 + round((self._notice_start_contrast - 1)
                             * (1. - step / (MAX_BRIGHTNESS - 1)))
        if self.stream.set_dim_override(contrast):
            self.reactor.update_timer(self.oled.timer, self.reactor.NOW)
        return DIM

    def _maintenance_sleep(self, now):
        maintenance = self.printer.lookup_object('m300_maintenance', None)
        if maintenance is None:
            return False
        try:
            return maintenance.get_status(now).get('state') in ('SLEEP', 'SLEEPING')
        except Exception:
            return False

    def _working(self, now):
        names = ('print_stats', 'm300_job', 'm300_filament',
                 'm300_calibration', 'm300_motion', 'm300_thermal', 'm300_fans',
                 'm300_models', 'm300_sd')
        for name in names:
            obj = self.printer.lookup_object(name, None)
            if obj is None:
                continue
            try:
                status = obj.get_status(now)
                if not isinstance(status, dict) or not (
                        isinstance(status.get('state'), str) or 'busy' in status):
                    return True
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
        asleep = self._maintenance_sleep(now)
        entered_sleep = asleep and not self._maintenance_asleep
        self._maintenance_asleep = asleep
        if entered_sleep and not self.busy and self.sleep_enabled:
            self._begin_notice()
        if not self.sleep_enabled:
            self._leave_notice()
            self.phase, desired = AWAKE, AWAKE
        elif self.busy:
            self._leave_notice()
            desired = DIM if now - self.last_activity >= self.timeout else AWAKE
            self.phase = desired
        elif self.phase == 'ENTERING_SLEEP':
            desired = self._notice_mode(now)
        elif now - self.last_activity >= self.timeout:
            if self.phase == OFF:
                desired = OFF
            else:
                self._begin_notice()
                desired = DIM
        else:
            desired = AWAKE
            self.phase = AWAKE
        self._sync_presentation()
        if desired != self.stream.requested_mode:
            self.stream.set_mode(desired)
            self.reactor.update_timer(self.oled.timer, self.reactor.NOW)
        return now + (.1 if self.phase == 'ENTERING_SLEEP' else 1.)

    def get_status(self, now):
        return {'revision': REVISION, 'connected': self.connected,
                'error': self.error, 'timeout': self.timeout,
                'mode': self.stream.display_mode if self.stream else 'UNAVAILABLE',
                'requested_mode': self.stream.requested_mode if self.stream else None,
                'normal_contrast': self.normal, 'dim_contrast': self.dim,
                'brightness': self.brightness,
                'applied_contrast': self.stream.display_contrast if self.stream else None,
                'phase': self.phase, 'notice_seconds': self.notice_seconds,
                'sleep_enabled': self.sleep_enabled,
                'notice': ENTERING_TEXT if self.phase == 'ENTERING_SLEEP' else None,
                'oem_moon_descriptor': '0x0801d908',
                'ui_guarded': self.phase == 'ENTERING_SLEEP' or self._presentation_wait,
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
