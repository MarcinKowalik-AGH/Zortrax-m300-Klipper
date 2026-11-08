# SPDX-License-Identifier: GPL-3.0-or-later
"""M300 startup reconnect and private OLED lease; never resumes actuators."""
import json
import logging
from .m300_mcu import STATE_FORMAT

RESPONSE = 'm300_oled_host_state state=%c local=%c fault=%c reason=%c'


class M300Lifecycle:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.board = self.printer.load_object(config, 'm300_mcu')
        self.mcu = self.board.get_mcu()
        self.reconnect_enabled = config.getboolean(
            'reconnect_on_host_start', self.board.native_control)
        self.startup_reconnect = {'enabled': self.reconnect_enabled,
                                  'decision': 'NOT_CHECKED', 'attempted': False,
                                  'max_attempts': 1, 'previous_guard': None}
        self.connected = self.claimed = self.resyncing = False
        self.recovery_failed = False
        self.error = None
        self.state = {}
        self.generation = self.sent = self.restarts = 0
        self.claim_at = self.reactor.monotonic()
        self.command = None
        self.timer = self.reactor.register_timer(self._tick)
        self.mcu.register_config_callback(self._build_config)
        # This runs after native serial identification/restart-command lookup
        # and before the first native get_config. A shutdown MCU otherwise
        # refuses configuration before the board's connect handler can run.
        self.printer.register_event_handler('klippy:mcu_identify', self._startup_identify)
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

    def _startup_identify(self):
        report = self.startup_reconnect
        if self.mcu.is_fileoutput():
            report['decision'] = 'FILEOUTPUT_NO_UART'
            return
        if not self.reconnect_enabled or not self.board.native_control:
            report['decision'] = 'DISABLED'
            return
        start_args = self.printer.get_start_args()
        previous = start_args.get('m300_startup_reconnect')
        if previous is not None:
            report.update(previous)
            report['decision'] = ('POST_RESET_ATTACH' if
                start_args.get('start_reason') == 'firmware_restart' else 'ATTEMPT_ALREADY_USED')
            return
        if start_args.get('start_reason') != 'startup':
            # RESTART/FIRMWARE_RESTART keep their existing native semantics.
            # Never turn an ordinary RESTART from Error into a fault clear.
            report['decision'] = 'NOT_A_HOST_PROCESS_START'
            return
        constants = self.mcu.get_constants()
        if (constants.get('M300_MODEL') != 'M300_CLASSIC'
                or int(constants.get('M300_ABI', 0)) != 1
                or not self.mcu.check_valid_response(STATE_FORMAT)):
            report['decision'] = 'UNSUPPORTED_MCU'
            return
        try:
            query = self.mcu.lookup_query_command('m300_query', STATE_FORMAT)
            state = self.board.startup_transport._bounded('m300_query(startup)', query.send)
        except Exception as exc:
            report['decision'], report['error'] = 'QUERY_FAILED', str(exc)
            raise
        fields = ('configured', 'armed', 'fault', 'inputs')
        if (any(type(state.get(key)) is not int for key in fields)
                or state['configured'] not in (0, 1) or state['armed'] not in (0, 1)
                or not 0 <= state['fault'] <= 255 or not 0 <= state['inputs'] <= 65535
                or (state['fault'] and state['armed'])):
            report['decision'] = 'INVALID_GUARD_STATE'
            raise self.printer.config_error('M300 invalid startup guard state')
        report['previous_guard'] = {key: state[key] for key in fields}
        fault = state['fault']
        if fault not in (0, 1) or state['inputs'] & 1:
            report['decision'] = 'HARDWARE_OR_EXPLICIT_SHUTDOWN_REQUIRES_OPERATOR'
            return
        # Only a previous configured session qualifies: fault 1 is the MCU's
        # heartbeat-loss latch. A rapid service restart may reconnect before
        # its one-second deadline, finding the old session still armed.
        if not state['configured'] or (not fault and not state['armed']):
            report['decision'] = 'NO_OLD_ACTIVE_SESSION'
            return
        helper = self.mcu._conn_helper.get_restart_helper()
        if helper._restart_method != 'command':
            report['decision'] = 'COMMAND_RESTART_REQUIRED'
            raise self.printer.config_error(
                'M300 startup reconnect requires [mcu] restart_method: command')
        report.update(decision='NATIVE_RESET_REQUESTED', attempted=True,
                      trigger='heartbeat_loss' if fault == 1 else 'previous_host_session')
        # Native Klippy reuses start_args for its internal restart loop. This
        # records the reason and consumes the only attempt for this process.
        start_args['m300_startup_reconnect'] = dict(report)
        logging.warning('M300_HOST_START_RECONNECT %s', json.dumps(report, sort_keys=True))
        helper._check_restart('M300 previous host session; ' + report['trigger'])

    def _build_config(self):
        constants = self.mcu.get_constants()
        if (constants.get('M300_MODEL') != 'M300_CLASSIC'
                or int(constants.get('M300_OLED_HOSTLINK_ABI', 0)) != 1):
            raise self.printer.config_error('M300 R9 lifecycle requires matching R9 MCU application')
        if not self.mcu.check_valid_response(RESPONSE):
            raise self.printer.config_error('M300 R9 OLED host-lease response missing')
        self.command = self.mcu.lookup_command('m300_oled_host state=%c')
        self.mcu.register_serial_response(self._response, RESPONSE)

    def claim(self, command_queue=None):
        if self.command is None:
            raise self.printer.command_error('M300 OLED host-lease command is not configured')
        self.recovery_failed = False
        self.error = None
        self.claim_at = self.reactor.monotonic()
        command = self.command
        if command_queue is not None:
            # An OLED re-claim cancels the MCU DMA FIFO. Keep it behind all
            # older display writes and before the new reset/init sequence.
            # A separate high-priority queue could overtake background data.
            command = self.mcu.lookup_command('m300_oled_host state=%c',
                                              cq=command_queue)
        command.send([1])
        self.sent += 1
        self.claimed = False  # Only the current MCU reply confirms ownership.
        self.resyncing = True

    def _ready(self):
        # OLED Ready may claim before this Ready handler runs. Disconnect
        # already advances the epoch; do not discard that initial claim ACK.
        self.connected = True
        self.error = None
        if self.startup_reconnect['decision'] == 'POST_RESET_ATTACH':
            self.startup_reconnect['decision'] = 'RECOVERED'
            logging.info('M300_HOST_START_RECONNECTED %s',
                         json.dumps(self.startup_reconnect, sort_keys=True))
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
        return {'revision': '0.13.16.31-OLED-QUEUE-SYNC', 'connected': self.connected,
                'claimed': self.claimed, 'resyncing': self.resyncing, 'error': self.error,
                'recovery_failed': self.recovery_failed,
                'mcu': dict(self.state), 'generation': self.generation,
                'lease_seconds': 1.5, 'heartbeat_seconds': .5, 'sent': self.sent,
                'ready_restarts_reset_mcu': True, 'mapped_restarts': self.restarts,
                'automatic_arm': False,
                'automatic_fault_clear': self.reconnect_enabled,
                'automatic_fault_clear_codes': [1] if self.reconnect_enabled else [],
                'automatic_hardware_fault_clear': False,
                'startup_reconnect': dict(self.startup_reconnect),
                'automatic_action_resume': False}

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_LINK ' + json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))


def load_config(config):
    return M300Lifecycle(config)
