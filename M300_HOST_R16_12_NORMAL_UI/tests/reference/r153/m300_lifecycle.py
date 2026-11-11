# SPDX-License-Identifier: GPL-3.0-or-later
"""M300 restart policy and private OLED host lease; never enables actuators."""
import json
import logging

RESPONSE = 'm300_oled_host_state state=%c local=%c fault=%c reason=%c'


class M300Lifecycle:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.board = self.printer.load_object(config, 'm300_mcu')
        self.mcu = self.board.get_mcu()
        self.connected = self.claimed = self.resyncing = False
        self.recovery_failed = False
        self.error = None
        self.state = {}
        self.generation = self.sent = self.restarts = 0
        self.claim_at = self.reactor.monotonic()
        self.command = None
        self.timer = self.reactor.register_timer(self._tick)
        self.mcu.register_config_callback(self._build_config)
        # Bind before connect: an explicit FIRMWARE_RESTART remains available
        # on a configuration error. Ordinary RESTART only resets the MCU when
        # issued from Ready; it never silently clears an existing fault.
        native_restart = self.gcode.request_restart
        def request_restart(result):
            if result == 'restart' and self.gcode.is_printer_ready:
                self.restarts += 1
                result = 'firmware_restart'
            return native_restart(result)
        self.gcode.request_restart = request_restart
        self.printer.register_event_handler('klippy:ready', self._ready)
        self.printer.register_event_handler('gcode:request_restart', self._restart)
        self.printer.register_event_handler('klippy:shutdown', self._shutdown)
        self.printer.register_event_handler('klippy:disconnect', self._disconnect)
        self.gcode.register_command('ZORTRAX_LINK_STATUS', self.cmd_status, when_not_ready=True)

    def _build_config(self):
        constants = self.mcu.get_constants()
        if (constants.get('M300_MODEL') != 'M300_CLASSIC'
                or int(constants.get('M300_OLED_HOSTLINK_ABI', 0)) != 1):
            raise self.printer.config_error('M300 R9 lifecycle requires matching R9 MCU application')
        if not self.mcu.check_valid_response(RESPONSE):
            raise self.printer.config_error('M300 R9 OLED host-lease response missing')
        self.command = self.mcu.lookup_command('m300_oled_host state=%c')
        self.mcu.register_serial_response(self._response, RESPONSE)

    def claim(self):
        if self.command is None:
            raise self.printer.command_error('M300 OLED host-lease command is not configured')
        self.recovery_failed = False
        self.error = None
        self.claim_at = self.reactor.monotonic()
        self.command.send([1])
        self.sent += 1
        self.claimed = False  # Only the current MCU reply confirms ownership.
        self.resyncing = True

    def _ready(self):
        # OLED Ready may claim before this Ready handler runs. Disconnect
        # already advances the epoch; do not discard that initial claim ACK.
        self.connected = True
        self.error = None
        if not self.claimed and not self.resyncing:
            self.claim()
        self.reactor.update_timer(self.timer, self.reactor.monotonic()+.5)

    def _tick(self, now):
        if not self.connected:
            return self.reactor.NEVER
        self.command.send([2])
        self.sent += 1
        return now+.5

    def _response(self, params):
        generation = self.generation
        def deliver(now):
            if not self.connected or generation != self.generation:
                return
            self.state = {key: params[key] for key in ('state', 'local', 'fault', 'reason')}
            if params['fault']:
                self.claimed = False
                self.error = 'MCU display fault/shutdown; explicit FIRMWARE_RESTART required'
                return
            if self.recovery_failed:
                # A delayed claim reply cannot erase a failed-render result.
                # A new explicit claim may clear this display-only latch.
                return
            if params['state']:
                self.claimed = True
                self.resyncing = False
                self.error = None
                return
            self.claimed = False
            if self.resyncing and now-self.claim_at < 1.5:
                return
            oled = self.printer.lookup_object('m300_oled', None)
            if oled is not None and oled.connected:
                # A lease timeout with healthy MCU invalidates only display
                # transport/input. No print/filament/calibration continuation.
                self.resyncing = True
                try:
                    oled._reinitialize(now, lifecycle_recovery=True)
                except Exception as exc:
                    # Rendering/optional-panel failure is not permission to
                    # interrupt a print or invoke an actuator shutdown.
                    self.recovery_failed = True
                    self.claimed = self.resyncing = False
                    self.error = 'Display recovery failed: ' + str(exc)
                    logging.exception('M300 optional display recovery failed')
                    oled._stop('fault', self.error)
                    try:
                        self.command.send([0])
                        self.sent += 1
                    except Exception:
                        logging.exception('M300 optional display release failed')
        self.reactor.register_async_callback(deliver)

    def _release(self):
        if self.command is not None and self.connected:
            try:
                self.command.send([0])
                self.sent += 1
            except Exception:
                logging.exception('M300 optional OLED release; local MCU watchdog owns fallback')
        self._disconnect()

    def _restart(self, *args):
        self._release()

    def _shutdown(self):
        self._release()

    def _disconnect(self):
        # Transport may already be gone: never send from this event.
        self.connected = self.claimed = self.resyncing = False
        self.generation += 1
        self.reactor.update_timer(self.timer, self.reactor.NEVER)

    def get_status(self, now):
        return {'revision': '0.13.9-LIFECYCLE-R9', 'connected': self.connected,
                'claimed': self.claimed, 'resyncing': self.resyncing, 'error': self.error,
                'recovery_failed': self.recovery_failed,
                'mcu': dict(self.state), 'generation': self.generation,
                'lease_seconds': 1.5, 'heartbeat_seconds': .5, 'sent': self.sent,
                'ready_restarts_reset_mcu': True, 'mapped_restarts': self.restarts,
                'automatic_arm': False, 'automatic_fault_clear': False,
                'automatic_action_resume': False}

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_LINK ' + json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))


def load_config(config):
    return M300Lifecycle(config)
