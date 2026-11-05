# SPDX-License-Identifier: GPL-3.0-or-later
"""Classic M300 diagnostics and token-bound optional job/filament controls.

Only the respective job or filament owner executes its requested actions. The
panel does not arm the board, start work, choose a material temperature, clear
faults or issue motion/heater G-code itself.
"""
import logging
import math
import textwrap

from .m300_oled_render import Frame
from .m300_oled_transport import EncoderSnapshots, OledStream, FastOledStream
from .m300_settings_ui import menu_label_pixels, menu_frame, notice_frame
from .m300_ui_labels import english_label

PANEL_RESPONSE = ('m300_panel_state clock=%u sequence=%u position=%u pressed=%c'
                  ' presses=%u releases=%u shorts=%u longs=%u invalid=%u')
PANEL_RESPONSE_V2 = ('m300_panel_state_v2 clock=%u sequence=%u position=%u pressed=%c'
                     ' presses=%u releases=%u shorts=%u longs=%u invalid=%u nav_position=%u')
PANEL_PINS = ('PB12', 'PB13', 'PB14', 'PB15', 'PE9', 'PE10', 'PE7', 'PE8', 'PC5')
OLED_STATS = ('m300_oled_stats blocks=%u wire=%u queued=%c peak=%c fault=%c'
              ' spi_hz=%u max_busy_ticks=%u')
OLED_RLE_RESULT = 'm300_oled_rle_result c_ticks=%u asm_ticks=%u'
# Same native serialqueue background priority used by Klipper's UC1701/OLED.
BACKGROUND_PRIORITY_CLOCK = 0x7fffffff00000000
_DIRECT_SELECT = object()



class M300OLED:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.board = self.printer.load_object(config, 'm300_mcu')
        self.status_screen = self.printer.load_object(config, 'm300_klipper_status')
        self.mcu = self.board.get_mcu()
        mcu_name = self.mcu.get_name()
        mcu_section = 'mcu' if mcu_name == 'mcu' else 'mcu ' + mcu_name
        # Read the public config section. Recent pinned Klipper stores baud in
        # MCUConnectHelper, not in MCU._baud; the firmware constant is only the
        # compile-time fallback and must not size the runtime bandwidth budget.
        self.host_baud = config.getsection(mcu_section).getint('baud', 250000)
        self.gcode = self.printer.lookup_object('gcode')
        self.speed = config.getint('spi_speed', 1000000,
                                   minval=500000, maxval=4500000)
        self.interval = config.getfloat('chunk_interval', .002,
                                       minval=.002, maxval=.050)
        self.stream = OledStream(
            config.getfloat('ack_timeout', 1., minval=.1, maxval=10.),
            config.getfloat('refresh_interval', .2, minval=.2, maxval=10.))
        self._fast_options = dict(
            window=config.getint('dma_window', 4, minval=1, maxval=4),
            interactive_interval=config.getfloat('interactive_interval', .020,
                                                 minval=.020, maxval=.200),
            work_interval=config.getfloat('work_interval', .100,
                                          minval=.050, maxval=1.),
            work_bytes_per_second=(config.getfloat('work_uart_fraction', .20,
                                                   minval=.05, maxval=.50)
                                   * self.host_baud / 10.),
            optimize_windows=config.getboolean('optimize_windows', True))
        self.fast = False
        self.mcu_oled_stats = None
        self.stats_at = self.work_at = 0.
        self.render_last_ms = self.render_max_ms = 0.
        self.render_count = self.tick_count = 0
        steps = config.getint('encoder_steps_per_detent', 4)
        if steps not in (1, 2, 4):
            raise config.error('encoder_steps_per_detent must be 1, 2 or 4')
        self.encoder = EncoderSnapshots(steps, config.getboolean('encoder_reverse', False))
        # Menu orientation is independent of encoder capture and hold-to-jog.
        self.menu_reverse = config.getboolean('menu_reverse', True)
        self.page = 'status'
        self.selection = 0
        self.message = None
        self.job_token = None
        self.cancel_token = None
        self.job_notice = None
        self.job_notice_accepted = False
        self.filament_token = self.filament_cancel_token = None
        self.filament_phase_id = None
        self.filament_notice = None
        self.filament_notice_accepted = False
        self.connected = False
        self.generation = 0
        self.render_at = self.query_at = 0.
        self._user_refresh_pending = False
        self._render_key = self._render_wire = None
        self._input_epoch = 0
        self._presented_context = self._presented_actions = None
        self.commands = {}
        self.cq = self.mcu.alloc_command_queue()
        self.timer = self.reactor.register_timer(self._tick)
        self.mcu.register_config_callback(self._build_config)
        self.printer.register_event_handler('klippy:ready', self._ready)
        self.printer.register_event_handler('klippy:shutdown', self._shutdown)
        self.printer.register_event_handler('klippy:disconnect', self._disconnect)
        self.gcode.register_command('ZORTRAX_OLED_STATUS', self.cmd_status)
        self.gcode.register_command('ZORTRAX_OLED_REINIT', self.cmd_reinit)
        self.gcode.register_command('ZORTRAX_OLED_TEXT', self.cmd_text)
        self.gcode.register_command('ZORTRAX_OLED_PERF_RESET', self.cmd_perf_reset)
        self.gcode.register_command('ZORTRAX_OLED_RLE_BENCH', self.cmd_rle_bench)

    def _build_config(self):
        constants = self.mcu.get_constants()
        if int(constants.get('M300_ABI', -1)) != 1 or \
                constants.get('M300_MODEL') != 'M300_CLASSIC':
            raise self.printer.config_error('M300 OLED requires M300_CLASSIC ABI1')
        if int(constants.get('M300_OLED_MAX_CHUNK', 0)) != 32:
            raise self.printer.config_error('M300 OLED chunk ABI mismatch')
        capture_abi = int(constants.get('M300_PANEL_CAPTURE_ABI', 0))
        if capture_abi > 3:
            raise self.printer.config_error('M300 encoder capture ABI mismatch')
        self.encoder.validated = capture_abi == 3
        panel_response = PANEL_RESPONSE_V2 if self.encoder.validated else PANEL_RESPONSE
        panel_config = ('m300_panel_config_v2 steps=%c' if self.encoder.validated
                        else 'm300_panel_config')
        self.fast = int(constants.get('M300_OLED_FAST_ABI', 0)) == 1
        if self.fast:
            if (int(constants.get('M300_OLED_FAST_QUEUE', 0)) != 4 or
                    int(constants.get('M300_OLED_FAST_WIRE', 0)) != 256):
                raise self.printer.config_error('M300 OLED DMA ABI mismatch')
            if not self.mcu.check_valid_response(OLED_STATS):
                raise self.printer.config_error('M300 OLED DMA statistics ABI mismatch')
            self.stream = FastOledStream(self.stream.timeout,
                                         self.stream.refresh_interval,
                                         **self._fast_options)
            self.commands['burst'] = self.mcu.lookup_command(
                'm300_oled_burst token=%hu dc=%c encoding=%c length=%hu data=%*s',
                cq=self.cq)
            self.commands['stats'] = self.mcu.lookup_command('m300_oled_query_stats', cq=self.cq)
            self.mcu.register_serial_response(self._stats, OLED_STATS)
        elif self.speed > 2000000:
            raise self.printer.config_error('MCU OLED R3 required for SPI above 2000000')
        # AsyncResponseWrapper performs its own format validation only during
        # post-init. Validate here so an incompatible reply dictionary cannot
        # be discovered after earlier MCU configuration has already been sent.
        for response in ('m300_oled_ack token=%hu', panel_response):
            if not self.mcu.check_valid_response(response):
                raise self.printer.config_error(
                    'M300 OLED missing/incompatible response: ' + response)
        # Validate config-only commands now as well; add_config_cmd alone does
        # not perform dictionary lookup before the configuration is encoded.
        self.mcu.lookup_command('m300_oled_config rate=%u')
        self.mcu.lookup_command(panel_config)
        self.commands['write'] = self.mcu.lookup_command(
            'm300_oled_write token=%hu dc=%c data=%*s', cq=self.cq)
        self.commands['control'] = self.mcu.lookup_command(
            'm300_oled_control token=%hu reset=%c gate=%c', cq=self.cq)
        self.commands['query'] = self.mcu.lookup_command('m300_panel_query', cq=self.cq)
        self.mcu.register_serial_response(self._ack, 'm300_oled_ack token=%hu')
        self.mcu.register_serial_response(self._panel, panel_response)
        self.mcu.add_config_cmd('m300_oled_config rate=%d' % self.speed)
        self.mcu.add_config_cmd('m300_panel_config_v2 steps=%d' % self.encoder.steps_per_detent
                                if self.encoder.validated else 'm300_panel_config')

    def _link(self):
        return self.printer.lookup_object('m300_oled_link', None)

    def _ready(self):
        lifecycle = self.printer.lookup_object('m300_lifecycle', None)
        if lifecycle is not None:
            lifecycle.claim()
        self.generation += 1
        self.connected = True
        self.encoder.reset()
        self.page, self.selection, self.message = 'status', 0, None
        self._clear_job_view()
        self._clear_filament_view()
        now = self.reactor.monotonic()
        self.render_at = self.query_at = now
        self.stats_at = self.work_at = now
        self.mcu_oled_stats = None
        self._user_refresh_pending = False
        self._render_key = self._render_wire = None
        self._render(now)
        self.stream.start(now)
        link = self._link()
        if link is not None:
            link.on_ready(now)
        self.reactor.update_timer(self.timer, self.reactor.NOW)

    def _stop(self, state, reason):
        self.generation += 1
        self.connected = False
        self.stream.stop(reason, state)
        self._user_refresh_pending = False
        self._render_key = self._render_wire = None
        link = self._link()
        if link is not None:
            link.on_stop()
        self.encoder.reset()
        self._clear_job_view()
        self._clear_filament_view()
        self.reactor.update_timer(self.timer, self.reactor.NEVER)

    def _shutdown(self):
        # Firmware DECL_SHUTDOWN independently drives PE9/PE10 LOW. Do not
        # attempt normal serial commands after MCU shutdown or promise a
        # freshly rendered error screen without a functioning transport.
        self._stop('shutdown', 'Klipper shutdown; local MCU Waiting owns the panel')

    def _disconnect(self):
        self._stop('disconnected', 'MCU disconnected; displayed content is untrusted')

    def _ack(self, params):
        generation = self.generation
        token = params['token']
        def deliver(now):
            if self.connected and generation == self.generation:
                if self.stream.ack(token, now):
                    # One application ACK proves the previous SPI operation
                    # completed. Continue promptly; the fallback tick must not
                    # add Linux timer latency to every 32-byte operation.
                    self._send_one(now)
                    if self.fast:
                        self.reactor.update_timer(self.timer, self._deadline(now))
        self.reactor.register_async_callback(deliver)

    def _stats(self, params):
        generation = self.generation
        snapshot = {k: params[k] for k in
                    ('blocks', 'wire', 'queued', 'peak', 'fault', 'spi_hz', 'max_busy_ticks')}
        def deliver(now):
            if self.connected and generation == self.generation:
                self.mcu_oled_stats = snapshot
                if snapshot['fault']:
                    self.stream.stop('OLED DMA fault; MCU reset required', 'reset_required')
                    link = self._link()
                    if link is not None:
                        link.on_stop()
        self.reactor.register_async_callback(deliver)

    def _input_context(self):
        menu = self.printer.lookup_object('m300_menu', None)
        return (self.generation, self._input_epoch, self.page, id(menu),
                getattr(menu, 'generation', None), getattr(menu, 'page', None),
                id(self.message), self.job_token, self.cancel_token,
                self.filament_token, self.filament_phase_id, self.filament_cancel_token)

    def _panel(self, params):
        generation = self.generation
        received_context = self._input_context()
        presented_actions = (self._presented_actions
                             if self._presented_context == received_context else None)
        received_page = self.page
        print_ui = self.printer.lookup_object('m300_print_ui', None)
        print_receipt = print_ui.receipt(self.stream, received_context) if print_ui else None
        received_stream = self.stream

        def print_guard():
            return (self.connected and received_stream is self.stream
                    and received_context == self._input_context()
                    and self.stream.enabled and self.stream.ready
                    and getattr(self.stream, 'requested_mode', None) != 'OFF')
        received_menu = self.printer.lookup_object('m300_menu', None)
        received_menu_generation = getattr(received_menu, 'generation', None)
        received_menu_page = getattr(received_menu, 'page', None)
        received_motion_token = getattr(received_menu, '_motion_jog_token', None)
        received_ui = self.printer.lookup_object('m300_menu_ui', None)
        receipt = getattr(received_ui, 'leveling_receipt', None)
        received_leveling = receipt(self.stream) if receipt is not None else None
        brightness_receipt = getattr(received_ui, 'brightness_receipt', None)
        received_brightness = brightness_receipt(self.stream) if brightness_receipt else None
        platform_receipt=getattr(received_ui,'platform_receipt',None)
        received_platform=platform_receipt(self.stream) if platform_receipt is not None else None
        # Native serialhdl records this before dispatching its handler. A
        # delayed serial callback must not freshen a stale press/rotation.
        received_at = params.get('#receive_time', self.reactor.monotonic())
        snapshot = dict(params)
        def deliver(now):
            if not self.connected or generation != self.generation:
                return
            timestamp_valid = (isinstance(received_at, (int, float))
                               and not isinstance(received_at, bool)
                               and math.isfinite(received_at)
                               and 0. <= now - received_at)
            events = self.encoder.update(snapshot, received_at) if timestamp_valid else None
            if not timestamp_valid or now - received_at > 1.:
                events = None
            menu = self.printer.lookup_object('m300_menu', None)
            motion = self.printer.lookup_object('m300_motion', None)
            current_view = (menu is not None and menu is received_menu
                            and received_page == self.page
                            and received_menu_generation == menu.generation
                            and received_menu_page == menu.page
                            and self.page in ('home', 'm04'))
            jog_view = (current_view and menu.page == 'motion_jog'
                        and received_motion_token is not None
                        and received_motion_token == menu._motion_jog_token
                        and (not self.fast or (self.stream.enabled and self.stream.ready)))
            if motion is not None:
                # First/stale encoder baselines still carry a release/STOP.
                # Only a matching captured view/token can grant a fresh jog
                # press. The timestamp is native serial receipt, not either
                # the delayed serial callback or reactor dispatch time.
                try:
                    motion.panel_update(snapshot, received_at,
                                        received_motion_token,
                                        view_current=jog_view)
                except Exception as exc:
                    logging.info('M300 motion panel refused: %s', exc)
                    if (received_motion_token is not None
                            and motion.get_status(now).get('session_token') == received_motion_token):
                        motion.cancel('invalid/stale panel update', token=received_motion_token)
                    if menu is not None:
                        menu.reason = self._job_text(str(exc))
                if jog_view:
                    # The MCU reports a long event after 600ms while held.
                    # It is part of this deadman hold, not menu navigation.
                    # A release ends the owner's jog session; consume its
                    # coalesced click before exposing ordinary menu actions.
                    if not motion.is_busy():
                        menu._motion_jog_token = None
                        menu._navigate('motion_status')
                        self.selection = 0
                    self.render_at = 0.
                    return
                if (current_view and menu.page == 'motion_status'
                        and events is not None and events['longs']):
                    motion.cancel('operator long press during homing')
            platform_panel=getattr(received_ui,'platform_panel',None)
            if platform_panel is not None and platform_panel(
                    snapshot,received_at,received_platform,events,now):
                self.render_at=0.
                return
            if print_ui is not None and print_ui.panel(events, received_at, now,
                                                        print_receipt, print_guard,
                                                        reverse=getattr(self, 'menu_reverse', False),
                                                        printing_status=received_page == 'status'):
                if events and any(events[k] for k in ('delta', 'shorts', 'longs')):
                    self.render_at = 0.
                return
            if events is None:
                return
            if self.fast and not (self.stream.enabled and self.stream.ready):
                # Counters are consumed and the motion owner already saw STOP/
                # release above; a blank or uninitialized panel cannot select
                # unseen menu actions. Fluidd and native print work continue.
                return
            if received_page != self.page:
                # Consume counters, but never apply a queued status click to
                # a newly opened menu, even without the optional menu module.
                return
            if any(events[key] for key in ('longs', 'shorts', 'delta')):
                self._user_refresh_pending = True
            # The raw event remains diagnostic. Job actions below go through
            # the sole job owner with the token of the displayed session.
            self.printer.send_event('m300:panel', now, events)
            if received_context != self._input_context():
                self.render_at = 0.
                return
            menu = self.printer.lookup_object('m300_menu', None)
            if menu is not None:
                if (menu is not received_menu or received_page != self.page
                        or received_menu_generation != menu.generation):
                    # Consume cumulative encoder counters, but never bind an
                    # old click to an entry in a newly displayed menu.
                    self.render_at = 0.
                    return
                if any(events[key] for key in ('longs', 'shorts', 'delta')):
                    menu.maintenance.activity()
                if events['shorts']:
                    menu.maintenance.click()
            leveling_panel = getattr(received_ui, 'leveling_panel', None)
            if leveling_panel is not None and leveling_panel(events, received_leveling, now):
                return
            brightness_selection = getattr(received_ui, 'brightness_selection', None)
            brightness = (self.page == 'm04' and brightness_selection is not None
                          and brightness_selection() is not None)
            if events['longs']:
                if brightness:
                    menu._navigate('settings', remember=False)
                    self.selection = 0
                else:
                    self._show_status()
            elif self.message:
                # A notice is modal. Rotation cannot select the menu behind
                # it, including when rotation and click arrive in one packet.
                if events['shorts']:
                    self.message = None
                    self._input_epoch += 1
            elif self.page == 'status':
                # Rotation is informational on the status screen: never
                # change feedrate, temperature, position or a hidden selection.
                if events['shorts']:
                    if self.message:
                        self.message = None
                    else:
                        if menu is not None:
                            menu.home()
                        self.page = 'm04' if menu is not None else 'home'
                        self.selection = 0
            else:
                if events['delta']:
                    self.message = None
                    _, rows = self._rows(now)
                    count = len(presented_actions) if presented_actions is not None else len(rows)
                    delta = -events['delta'] if self.menu_reverse else events['delta']
                    self.selection = max(0, min(count - 1, self.selection + delta))
                if events['shorts'] and (not brightness or (
                        not events['delta'] and received_brightness == (menu.generation, self.selection))):
                    # Coalesced clicks never cascade through several menus.
                    self._select(now, presented_actions=presented_actions)
            self.render_at = 0.
        def dispatch(now):
            deliver(now)
            if self.fast and self.connected and generation == self.generation and self.render_at <= now:
                self.reactor.update_timer(self.timer, self.reactor.NOW)
        self.reactor.register_async_callback(dispatch)

    def _deadline(self, now):
        return min(now+.050, self.query_at, self.render_at,
                   self.stream.next_wakeup(now))

    def _working(self, now):
        stats = self.printer.lookup_object('print_stats', None)
        if stats is not None and stats.get_status(now).get('state') == 'printing':
            return True
        toolhead = self.printer.lookup_object('toolhead', None)
        if toolhead is not None:
            print_time, estimated_time, empty = toolhead.check_busy(now)
            return not empty or print_time > estimated_time
        return False

    def _tick(self, now):
        if not self.connected:
            return self.reactor.NEVER
        self.tick_count += 1
        if self.fast:
            if now >= self.work_at:
                self.stream.active_work = self._working(now)
                self.work_at = now+.100
            if now >= self.stats_at:
                self.commands['stats'].send([], reqclock=BACKGROUND_PRIORITY_CLOCK)
                self.stats_at = now+2.
        if now >= self.query_at:
            if not self.fast or self.encoder.last_time is None or now-self.encoder.last_time > .5:
                self.commands['query'].send([])
            self.query_at = now + .5
        if now >= self.render_at:
            self._render(now)
            self.render_at = now + (.5 if self.page == 'status' else .25)
        link = self._link()
        if link is not None:
            link.service(now)
        self._send_one(now)
        return self._deadline(now) if self.fast else now+self.interval

    def _send_one(self, now):
        # Firmware bounds the DMA FIFO to four slots. Delays/reset are barriers;
        # native Klipper serial scheduling and non-OLED queues stay independent.
        if not self.connected:
            return
        link = self._link()
        try:
            for _ in range(self.stream.window if self.fast else 1):
                operation = self.stream.step(now)
                if not operation:
                    break
                kind, token, args = operation
                if self.fast:
                    self.commands[kind].send([token, *args], reqclock=BACKGROUND_PRIORITY_CLOCK)
                else:
                    self.commands[kind].send([token, *args])
        except TimeoutError as exc:
            logging.error('M300 optional OLED stopped: %s', exc)
            if link is not None:
                if self.fast:
                    link.on_stop()
                else:
                    link.on_timeout(now, str(exc))

    @staticmethod
    def _temperature(status):
        value = status.get('temperature')
        if isinstance(value, (int, float)) and math.isfinite(value):
            return '%.1f°C' % value
        return '---'

    def _clear_job_view(self):
        self.job_token = self.cancel_token = None
        self.job_notice = None
        self.job_notice_accepted = False

    def _job_status(self, now):
        job = self.printer.lookup_object('m300_job', None)
        if job is None:
            return {'available': False, 'state': 'BRAK MODUŁU',
                    'session_token': None, 'filename': None,
                    'reason': 'Moduł m300_job nie jest skonfigurowany',
                    'can_pause': False, 'can_resume': False, 'can_cancel': False}
        try:
            status = dict(job.get_status(now))
        except Exception:
            logging.exception('M300 OLED cannot read optional job status')
            return {'available': False, 'state': 'BRAK STATUSU',
                    'session_token': None, 'filename': None,
                    'reason': 'Brak poprawnego statusu zadania',
                    'can_pause': False, 'can_resume': False, 'can_cancel': False}
        token = status.get('session_token')
        status['available'] = (isinstance(token, int) and not isinstance(token, bool)
                               and token >= 0 and isinstance(status.get('state'), str)
                               and bool(status['state']))
        for action in ('pause', 'resume', 'cancel'):
            key = 'can_' + action
            status[key] = status['available'] and status.get(key) is True
        return status

    @staticmethod
    def _job_text(value):
        # Bound text before wrapping; filenames/reasons are data, never G-code.
        return ' '.join(str(value or '').split())[:240]

    def _job_matches(self, status, token):
        return (status.get('available', False) and token is not None
                and token == status.get('session_token'))

    def _job_denial(self, action, status, token, now=None):
        if action not in ('PAUSE', 'RESUME', 'CANCEL'):
            return 'Panel nie obsługuje tej akcji'
        if not status.get('available'):
            return status.get('reason') or 'Brak poprawnego statusu zadania'
        if not self._job_matches(status, token):
            return 'Sesja zmieniła się. Otwórz Zadanie ponownie.'
        if not self.connected or not self.stream.enabled or not self.stream.ready:
            return 'Panel nie jest gotowy. Poczekaj na pełną inicjalizację.'
        if action == 'RESUME':
            filament = self._filament_status(
                self.reactor.monotonic() if now is None else now)
            if filament.get('installed'):
                if not filament.get('available') or not isinstance(
                        filament.get('busy'), bool):
                    return 'Brak poprawnego statusu usługi filamentu; wznowienie zablokowane'
                if filament['busy']:
                    return 'Najpierw zakończ usługę filamentu: ' + self._job_text(
                        filament.get('state'))
        if not status.get('can_' + action.lower(), False):
            reason = self._job_text(status.get('resume_block_reason')
                                    if action == 'RESUME' else None)
            reason = reason or self._job_text(status.get('reason'))
            return 'Niedostępne w fazie %s%s' % (
                status.get('state', '?'), ': ' + reason if reason else '')
        return None

    def _job_feedback(self, message, accepted=False):
        self.page = 'job'
        self.cancel_token = None
        self.job_notice = self._job_text(message)
        self.job_notice_accepted = accepted
        # Rows 0..5 have stable roles; selecting the first information row
        # cannot turn a repeated click into another action.
        self.selection = 6

    def _job_action(self, action, now, confirm=False):
        token = self.cancel_token if confirm else self.job_token
        status = self._job_status(now)
        reason = self._job_denial(action, status, token, now)
        if reason:
            self._job_feedback(reason)
            return
        if action == 'CANCEL' and not confirm:
            self.cancel_token = token
            self.page, self.selection = 'job_cancel', 0
            self.job_notice = None
            return
        # The job module validates token/state both now and in its asynchronous
        # callback. Acceptance is not completion and does not change our phase.
        job = self.printer.lookup_object('m300_job', None)
        try:
            result = job.request_ui(action, token)
            if not isinstance(result, dict) or result.get('accepted') is not True:
                error = (result.get('error') if isinstance(result, dict) else None)
                self._job_feedback(error or 'Żądanie nie zostało przyjęte')
                return
        except Exception as exc:
            logging.exception('M300 OLED job request rejected')
            self._job_feedback('Odmowa: ' + str(exc))
            return
        self._job_feedback('Przyjęto %s; oczekiwanie na zmianę fazy' % action,
                           accepted=True)

    def _job_rows(self, now):
        status = self._job_status(now)
        state = self._job_text(status.get('state', '?'))
        token = status.get('session_token')
        filename = self._job_text(status.get('filename')) or 'brak'
        if self.page == 'job_cancel':
            denied = self._job_denial('CANCEL', status, self.cancel_token, now)
            return 'Anulować zadanie?', [
                ('Nie, wróć', 'job_back'),
                ('Tak, anuluj' + (' [blokada]' if denied else ''), 'job_confirm'),
                ('Faza: ' + state, None), ('Plik: ' + filename, None),
                ('Sesja: %s' % self.cancel_token, None),
                (self._job_text(denied) if denied else 'Anulowanie kończy tę sesję', None)]
        progress = status.get('progress')
        progress = ('%.1f%%' % (100. * max(0., min(1., progress)))
                    if isinstance(progress, (int, float)) and math.isfinite(progress)
                    else '---')
        rows = [('Back', 'home'), ('Postęp: ' + progress, None)]
        for action, label in (('PAUSE', 'Pauza'), ('RESUME', 'Wznów'),
                              ('CANCEL', 'Anuluj...')):
            denied = self._job_denial(action, status, self.job_token, now)
            rows.append((label + (' [blokada]' if denied else ''),
                         'job_' + action.lower()))
        rows.append(('Plik: ' + filename, None))
        notices = []
        if self.job_notice and not self.job_notice_accepted:
            notices.append(self.job_notice)
        if not self._job_matches(status, self.job_token):
            notices.append(status.get('reason') if not status.get('available') else
                           'Sesja zmieniła się. Otwórz Zadanie ponownie.')
        if status.get('reason'):
            notices.append(status['reason'])
        if self.job_notice and self.job_notice_accepted:
            notices.append(self.job_notice)
        if not notices:
            notices = ['Stan i dostępność akcji według m300_job']
        if (self.printer.lookup_object('m300_menu', None) is not None
                and state in ('PAUSED', 'PAUSING', 'RESUMING')):
            notices.insert(0, 'UWAGA: gorąca głowica. Nie dotykaj dyszy.')
        # A refusal is immediately visible. A current phase/fault reason takes
        # precedence over an earlier accepted request, which is not completion.
        for message in dict.fromkeys(notices):
            rows.extend((line, None) for line in textwrap.wrap(
                english_label(self._job_text(message)), width=38, max_lines=7,
                placeholder='...'))
        rows.append(('Sesja: %s' % token, None))
        for key, label in (('target_hotend', 'Cel dyszy'), ('target_bed', 'Cel stołu')):
            value = status.get(key)
            value = ('%.1f°C' % value if isinstance(value, (int, float))
                     and math.isfinite(value) else '---')
            rows.append((label + ': ' + value, None))
        remaining = status.get('phase_remaining')
        remaining = ('%.1f s' % max(0., remaining)
                     if isinstance(remaining, (int, float)) and math.isfinite(remaining)
                     else '---')
        rows.append(('Czas fazy: ' + remaining, None))
        return 'Zadanie: ' + state, rows

    def _clear_filament_view(self):
        self.filament_token = self.filament_cancel_token = None
        self.filament_phase_id = None
        self.filament_notice = None
        self.filament_notice_accepted = False

    def _filament_status(self, now):
        service = self.printer.lookup_object('m300_filament', None)
        unavailable = dict(available=False, installed=service is not None,
                           state='BRAK MODUŁU', operation=None,
                           session_token=None, phase_id=None, busy=False,
                           can_confirm=False, can_purge=False, can_cancel=False,
                           reason='Moduł m300_filament nie jest skonfigurowany')
        if service is None:
            return unavailable
        try:
            status = dict(service.get_status(now))
        except Exception:
            logging.exception('M300 OLED cannot read optional filament status')
            unavailable.update(state='BRAK STATUSU', busy=None,
                               reason='Brak poprawnego statusu usługi filamentu')
            return unavailable
        token = status.get('session_token')
        status['installed'] = True
        status['available'] = (isinstance(token, int) and not isinstance(token, bool)
                               and token >= 0 and isinstance(status.get('state'), str)
                               and bool(status['state']))
        for action in ('confirm', 'purge', 'cancel'):
            key = 'can_' + action
            status[key] = status['available'] and status.get(key) is True
        return status

    def _filament_denial(self, action, status, token, phase_id=None):
        if action not in ('CONFIRM', 'PURGE', 'CANCEL'):
            return 'Panel nie obsługuje tej akcji'
        if not status.get('available'):
            return status.get('reason') or 'Brak poprawnego statusu usługi filamentu'
        if not self._job_matches(status, token):
            return 'Sesja zmieniła się. Otwórz Filament ponownie.'
        if not self.connected or not self.stream.enabled or not self.stream.ready:
            return 'Panel nie jest gotowy. Poczekaj na pełną inicjalizację.'
        if status.get('busy') is not True:
            reason = self._job_text(status.get('last_rejection') or status.get('reason'))
            return 'Brak aktywnej usługi filamentu (%s)%s' % (
                status.get('state', '?'), ': ' + reason if reason else '')
        if action in ('CONFIRM', 'PURGE'):
            current_phase = status.get('phase_id')
            if not (isinstance(phase_id, int) and not isinstance(phase_id, bool)
                    and phase_id >= 0 and isinstance(current_phase, int)
                    and not isinstance(current_phase, bool)
                    and phase_id == current_phase):
                return 'Etap zmienił się. Wybierz Odśwież etap przed kolejną akcją.'
        if not status.get('can_' + action.lower(), False):
            reason = self._job_text(status.get('last_rejection'))
            reason = reason or self._job_text(status.get('reason'))
            return 'Niedostępne w fazie %s%s' % (
                status.get('state', '?'), ': ' + reason if reason else '')
        return None

    def _filament_feedback(self, message, accepted=False):
        self.page = 'filament'
        self.filament_cancel_token = None
        self.filament_notice = self._job_text(message)
        self.filament_notice_accepted = accepted
        # Stable rows 0..6 precede information. A repeated click cannot repeat
        # CONFIRM/PURGE or silently approve a cancellation.
        self.selection = 7

    def _filament_action(self, action, now, confirm=False):
        token = self.filament_cancel_token if confirm else self.filament_token
        status = self._filament_status(now)
        reason = self._filament_denial(action, status, token, self.filament_phase_id)
        if reason:
            self._filament_feedback(reason)
            return
        if action == 'CANCEL' and not confirm:
            self.filament_cancel_token = token
            self.page, self.selection = 'filament_cancel', 0
            self.filament_notice = None
            return
        service = self.printer.lookup_object('m300_filament', None)
        try:
            if action == 'CANCEL':
                result = service.request_ui(action, token)
            else:
                result = service.request_ui(action, token, self.filament_phase_id)
            if not isinstance(result, dict) or result.get('accepted') is not True:
                error = (result.get('error') if isinstance(result, dict) else None)
                self._filament_feedback(error or 'Żądanie nie zostało przyjęte')
                return
        except Exception as exc:
            logging.exception('M300 OLED filament request rejected')
            self._filament_feedback('Odmowa: ' + str(exc))
            return
        self._filament_feedback('Przyjęto %s; oczekiwanie na zmianę fazy' % action,
                                accepted=True)

    def _filament_refresh(self, now):
        status = self._filament_status(now)
        if not self._job_matches(status, self.filament_token):
            self._filament_feedback('Sesja zmieniła się. Otwórz Filament ponownie.')
            return
        phase_id = status.get('phase_id')
        if not (isinstance(phase_id, int) and not isinstance(phase_id, bool)
                and phase_id >= 0):
            self._filament_feedback('Brak poprawnego identyfikatora etapu filamentu')
            return
        # Refresh is a separate read-only action. It never upgrades an old
        # click into an approval of the next prompt, or adopts another job.
        self.filament_phase_id = phase_id
        self.filament_notice = None
        self.filament_notice_accepted = False
        self.selection = 0

    def _filament_rows(self, now):
        status = self._filament_status(now)
        state = self._job_text(status.get('state', '?'))
        operation = self._job_text(status.get('operation')) or 'brak'
        if self.page == 'filament_cancel':
            denied = self._filament_denial('CANCEL', status, self.filament_cancel_token)
            return 'Anulować usługę filamentu?', [
                ('Nie, wróć', 'filament_back'),
                ('Tak, anuluj' + (' [blokada]' if denied else ''), 'filament_cancel_confirm'),
                ('Faza: ' + state, None), ('Operacja: ' + operation, None),
                ('Sesja: %s' % self.filament_cancel_token, None),
                (self._job_text(denied) if denied else 'Anulowanie kończy tę usługę', None)]
        rows = [('Back', 'home'), ('Operacja: ' + operation, None)]
        for action, label in (('CONFIRM', 'Potwierdź'), ('PURGE', 'Przepchnij'),
                              ('CANCEL', 'Anuluj usługę...')):
            denied = self._filament_denial(action, status, self.filament_token,
                                           self.filament_phase_id)
            rows.append((label + (' [blokada]' if denied else ''),
                         'filament_' + action.lower()))
        def number(key):
            value = status.get(key)
            return ('%.1f' % value if isinstance(value, (int, float))
                    and not isinstance(value, bool) and math.isfinite(value) else '---')
        rows.append(('E: %s / %s mm' % (number('completed_mm'), number('budget_mm')), None))
        rows.append(('Odśwież etap', 'filament_refresh'))
        notices = []
        if self.filament_notice and not self.filament_notice_accepted:
            notices.append(self.filament_notice)
        if not self._job_matches(status, self.filament_token):
            notices.append(status.get('reason') if not status.get('available') else
                           'Sesja zmieniła się. Otwórz Filament ponownie.')
        elif status.get('phase_id') != self.filament_phase_id:
            notices.append('Etap zmienił się. Wybierz Odśwież etap przed kolejną akcją.')
        if status.get('reason'):
            notices.append(status['reason'])
        if status.get('last_rejection'):
            notices.append(status['last_rejection'])
        if self.filament_notice and self.filament_notice_accepted:
            notices.append(self.filament_notice)
        if not notices:
            notices = ['Stan i dostępność akcji według m300_filament']
        for message in dict.fromkeys(notices):
            rows.extend((line, None) for line in textwrap.wrap(
                english_label(self._job_text(message)), width=38, max_lines=7, placeholder='...'))
        rows.extend([('Sesja: %s' % status.get('session_token'), None),
                     ('Etap: %s' % status.get('phase_id'), None),
                     ('Dysza: ' + number('temperature') + '°C', None),
                     ('Cel dyszy: ' + number('target') + '°C', None)])
        return 'Filament: ' + state, rows

    def _rows(self, now):
        menu = self.printer.lookup_object('m300_menu', None)
        if menu is not None and self.page in ('home', 'm04'):
            title, rows = menu.rows(now)
            if menu.page == 'main' or menu.maintenance.get_status(now)['sleep']:
                rows = [(menu.t('Back'), ('oled', 'status'))] + list(rows)
            return title, rows
        status = self.board.get_status(now)
        if self.page == 'home':
            return 'Diagnostyka M300', [
                ('Back', 'status'), ('Stan płyty', 'board'), ('Temperatury', 'temps'),
                ('Wejścia / pokrętło', 'inputs'), ('Informacje', 'about'),
                ('Zadanie', 'job'), ('Filament', 'filament')]
        if self.page in ('job', 'job_cancel'):
            return self._job_rows(now)
        if self.page in ('filament', 'filament_cancel'):
            return self._filament_rows(now)
        if self.page == 'oled_link':
            link = self._link()
            if link is not None:
                return link.menu_rows(now)
            return 'M10 OLED link', [('Back', 'oled_link_back'), ('Not installed', None)]
        if self.page == 'board':
            return 'Stan płyty', [('Back', 'home'),
                ('M300_CLASSIC / ABI1', None),
                ('Uzbrojona: %s' % status.get('armed', False), None),
                ('Błąd: %s' % status.get('fault', '?'), None),
                ('Etap: P01 LAB', None)]
        if self.page == 'temps':
            rows = [('Back', 'home')]
            observations = status.get('native_adc_observation', {})
            for name, label in (('extruder', 'Dysza'), ('heater_bed', 'Stół')):
                sensor = self.printer.lookup_object(name, None)
                observed = observations.get(name, {}).get('sample_observed', False)
                value = ('brak czujnika' if sensor is None else '---'
                         if not observed else self._temperature(sensor.get_status(now)))
                rows.append((label + ': ' + value, None))
            return 'Odczyt temperatur', rows
        if self.page == 'inputs':
            snapshot = self.encoder.previous or {}
            age = None if self.encoder.last_time is None else now - self.encoder.last_time
            rows = [('Back', 'home'),
                    ('PC5: ' + ('BRAK ODCZYTU' if age is None or age > 1.
                               else ('wciśnięty' if snapshot.get('pressed') else 'zwolniony')), None),
                    ('Enkoder: %s' % snapshot.get('position', '?'), None),
                    ('Błędy przejść: %s' % snapshot.get('invalid', '?'), None)]
            inputs = status.get('inputs', {})
            if isinstance(inputs, dict):
                rows.extend((str(name)[:24] + ': ' + str(value)[:8], None)
                            for name, value in sorted(inputs.items())[:16])
            return 'Wejścia M300', rows
        return 'Informacje', [('Back', 'home'),
            ('M300 Klipper / M03 LAB', None),
            ('Diagnostyka, zadanie, filament', None), ('Bez prób fizycznych', None),
            ('Obrót: wybór; klik: wejście', None), ('Przytrzymanie: menu główne', None)]

    def _show_status(self):
        self._input_epoch += 1
        self.page, self.selection, self.message = 'status', 0, None
        menu = self.printer.lookup_object('m300_menu', None)
        if menu is not None:
            menu.home()  # also releases an owned jog view; never cancels print
        self._clear_job_view()
        self._clear_filament_view()
        self.render_at = 0.

    def _render(self, now):
        started = self.reactor.monotonic()
        previous_wire = self._render_wire
        previous_context = self._presented_context
        maintenance_wire = None
        print_ui = self.printer.lookup_object('m300_print_ui', None)
        ui = self.printer.lookup_object('m300_menu_ui', None)
        print_wire = (print_ui.render(now, self._input_context(), Frame,
                                      show_status=self._show_status,
                                      sprites=getattr(ui, 'oem_sprites', None)) if print_ui else None)
        leveling_frame = getattr(ui, 'leveling_frame', None)
        leveling_wire = (leveling_frame(self.page, now, Frame)
                         if leveling_frame is not None and not self.message else None)
        if print_wire is not None:
            key = ('native_print_context', print_wire)
        elif self.message:
            title, message = (english_label(x) for x in self.message)
            notice_sprite = (ui.notice_sprite(title, message, now) if ui is not None else None)
            key = ('notice', (title, message), notice_sprite)
        elif leveling_wire is not None:
            key = ('leveling', leveling_wire)
        elif self.page == 'status':
            status_wire = self.status_screen.render(now)
            key = ('klipper_default', status_wire)
        else:
            title, rows = self._rows(now)
            self.selection = max(0, min(self.selection, len(rows) - 1))
            ui = self.printer.lookup_object('m300_menu_ui', None)
            sprite = (ui.get_oem_sprite(self.page, rows, self.selection, now)
                      if ui is not None else None)
            pixels = menu_label_pixels(sprite) if sprite else None
            if ui is not None and self.page in ('home', 'm04'):
                menu = self.printer.lookup_object('m300_menu', None)
                if menu is not None:
                    title, labels = ui.present(title, rows, self.selection, now,
                                               menu.page, menu.generation, pixels)
                else:
                    title, labels = ui.present_panel(title, rows, self.selection,
                                                     now, self.page, pixels)
            elif ui is not None:
                title, labels = ui.present_panel(title, rows, self.selection,
                                                 now, self.page, pixels)
            else:
                labels = [english_label(row[0]) for row in rows]
            renderer = getattr(ui, 'maintenance_frame', None)
            maintenance_wire = (renderer(self.page,rows,self.selection,Frame, labels=labels, sprite=sprite)
                                if renderer is not None else None)
            key = (('oem_menu',maintenance_wire) if maintenance_wire is not None
                   else ('menu', tuple(labels), self.selection, sprite))
        if key != self._render_key:
            if key[0] == 'notice':
                wire = notice_frame(title, message, Frame, key[2])
            elif key[0] == 'menu':
                wire = menu_frame(tuple(labels), (), self.selection, Frame, sprite)
            else:
                wire = key[1]
            self._render_wire = wire
            self._render_key = key
            self.render_last_ms = max(0., 1000.*(self.reactor.monotonic()-started))
            self.render_max_ms = max(self.render_max_ms, self.render_last_ms)
            self.render_count += 1
        self.stream.request(self._render_wire,
                            urgent=self._user_refresh_pending)
        context = self._input_context()
        if print_ui is not None and key[0] == 'klipper_default':
            print_ui.present_status(self._render_wire, context)
        if context != previous_context or self._render_wire != previous_wire:
            # A new invisible token (or a changed offscreen row) is not a new
            # displayed consent. Keep the previous actions until the operator
            # navigates/reviews a changed view. The next stale click is refused.
            self._presented_actions = (tuple(row[1] for row in rows)
                                       if key[0] in ('menu','oem_menu') else None)
        self._presented_context = context
        self._user_refresh_pending = False

    def _select(self, now, presented_actions=_DIRECT_SELECT):
        self._input_epoch += 1
        if self.message:
            self.message = None
            return
        if self.page == 'status':
            menu = self.printer.lookup_object('m300_menu', None)
            if menu is not None:
                menu.home()
            self.page, self.selection = ('m04' if menu is not None else 'home'), 0
            return
        _, rows = self._rows(now)
        index = max(0, min(self.selection, len(rows) - 1))
        action = rows[index][1]
        if presented_actions is not _DIRECT_SELECT and (
                presented_actions is None or not 0 <= self.selection < len(rows)
                or index >= len(presented_actions)
                or presented_actions[index] != action):
            self.message = ('View changed', 'Review the current view and select again.')
            self.selection = 0
            return
        if action in ('status', ('oled', 'status')):
            self._show_status()
            return
        menu = self.printer.lookup_object('m300_menu', None)
        if menu is not None and self.page in ('home', 'm04'):
            if not self.connected or not self.stream.enabled or not self.stream.ready:
                menu.reason = 'Panel is not ready; action refused.'
                return
            previous_page, previous_selection = menu.page, self.selection
            page = menu.select(action, now)
            # OEM fan and Settings choices redraw in place with the same cursor.
            in_place = previous_page == menu.page and not menu.reason and (
                menu.page == 'fan_test' or
                (menu.page.startswith('setting_') and action and action[0] == 'set'))
            self.page, self.selection = 'm04', previous_selection if in_place else 0
            if previous_page != menu.page:
                ui = self.printer.lookup_object('m300_menu_ui', None)
                brightness_selection = getattr(ui, 'brightness_selection', None)
                if brightness_selection is not None:
                    self.selection = brightness_selection() or 0
            if page == 'job':
                status = self._job_status(now)
                self.job_token = status.get('session_token') if status.get('available') else None
                self.cancel_token, self.job_notice = None, None
                self.page = 'job'
            elif page == 'filament':
                status = self._filament_status(now)
                self.filament_token = status.get('session_token') if status.get('available') else None
                self.filament_phase_id = status.get('phase_id')
                self.filament_cancel_token, self.filament_notice = None, None
                self.page = 'filament'
            elif page is not None:
                self.page = page
            elif menu.reason:
                # Existing owners keep the full refusal/acceptance semantics.
                # Present their result immediately, without relocating actions.
                self.message = ('Notice', menu.reason)
            return
        if action in ('job_pause', 'job_resume', 'job_cancel'):
            self._job_action(action[4:].upper(), now)
        elif action == 'job_confirm':
            self._job_action('CANCEL', now, confirm=True)
        elif action == 'job_back':
            self.page, self.selection, self.cancel_token = 'job', 0, None
        elif action == 'oled_link_back':
            self.page, self.selection = 'm04', 0
        elif action == 'oled_link_reinit':
            self._reinitialize(now)
            self.page, self.selection = 'oled_link', 0
        elif action == 'job':
            self._clear_filament_view()
            status = self._job_status(now)
            self.job_token = status.get('session_token') if status.get('available') else None
            self.cancel_token, self.job_notice = None, None
            self.page, self.selection = 'job', 0
        elif action in ('filament_confirm', 'filament_purge', 'filament_cancel'):
            self._filament_action(action[9:].upper(), now)
        elif action == 'filament_cancel_confirm':
            self._filament_action('CANCEL', now, confirm=True)
        elif action == 'filament_back':
            self.page, self.selection, self.filament_cancel_token = 'filament', 0, None
        elif action == 'filament_refresh':
            self._filament_refresh(now)
        elif action == 'filament':
            self._clear_job_view()
            status = self._filament_status(now)
            self.filament_token = (status.get('session_token')
                                   if status.get('available') else None)
            phase_id = status.get('phase_id')
            self.filament_phase_id = (phase_id if isinstance(phase_id, int)
                and not isinstance(phase_id, bool) and phase_id >= 0 else None)
            self.filament_cancel_token, self.filament_notice = None, None
            self.page, self.selection = 'filament', 0
        elif action is not None:
            self.page, self.selection = action, 0
            self._clear_job_view()
            self._clear_filament_view()

    def _reinitialize(self, now, lifecycle_recovery=False):
        if not self.connected:
            raise self.printer.command_error('M300 MCU is not ready; restart/reconnect first')
        if self.fast and self.stream.state == 'reset_required' and not lifecycle_recovery:
            raise self.printer.command_error('OLED transaction uncertain; use FIRMWARE_RESTART')
        lifecycle = self.printer.lookup_object('m300_lifecycle', None)
        if lifecycle is not None:
            lifecycle.claim()
        if lifecycle_recovery:
            self.generation += 1
            self._input_epoch += 1
            self._presented_context = self._presented_actions = None
            self._render_key = self._render_wire = None
            self.encoder.reset()
            self._clear_job_view()
            self._clear_filament_view()
            self.page, self.selection, self.message = 'status', 0, None
        self._render(now)
        self.stream.start(now)
        link = self._link()
        if link is not None:
            link.on_manual(now)

    def cmd_reinit(self, gcmd):
        if not self.connected:
            raise gcmd.error('M300 MCU is not ready; restart/reconnect first')
        self._reinitialize(self.reactor.monotonic())

    def cmd_text(self, gcmd):
        self.message = (gcmd.get('LINE1', 'M300')[:80], gcmd.get('LINE2', '')[:80])
        self.render_at = 0.
        self._user_refresh_pending = True

    def cmd_status(self, gcmd):
        gcmd.respond_info(str(self.get_status(self.reactor.monotonic())))

    def cmd_perf_reset(self, gcmd):
        if self.fast:
            self.stream.frame_samples.clear()
        self.render_max_ms = self.render_last_ms = 0.
        self.render_count = self.tick_count = 0
        gcmd.respond_info('OLED performance samples reset; transport/session unchanged')

    def cmd_rle_bench(self, gcmd):
        if not self.connected or not self.mcu.check_valid_response(OLED_RLE_RESULT):
            raise gcmd.error('OLED RLE benchmark requires a ready M300 OLED RLE MCU')
        length = gcmd.get_int('LENGTH', 128, minval=1, maxval=128)
        offset = gcmd.get_int('OFFSET', 1, minval=0, maxval=3)
        query = self.mcu.lookup_query_command(
            'm300_oled_rle_bench length=%c offset=%c', OLED_RLE_RESULT, cq=self.cq)
        result = query.send([length, offset])
        gcmd.respond_info('OLED RLE fill, %d bytes, offset %d: C %d cycles, ASM %d cycles'
                          % (length, offset, result['c_ticks'], result['asm_ticks']))

    def get_status(self, now):
        age = None if self.encoder.last_time is None else now - self.encoder.last_time
        return {'model': 'M300_CLASSIC', 'abi': 1,
                'host_revision': '0.13.9-OLED-R9-LIFECYCLE',
                'ui_revision': 'KLIPPER_DEFAULT_16X4_EN',
                'connected': self.connected, 'state': self.stream.state,
                'ready': self.stream.ready and self.stream.enabled and self.connected,
                'enabled': self.stream.enabled, 'error': self.stream.failure,
                'frames': self.stream.completed_frames, 'sent': self.stream.sent,
                'acked': self.stream.acked, 'ignored_acks': self.stream.ignored_acks,
                'last_frame_ms': self.stream.last_frame_ms,
                'transport': 'DMA_RLE_WINDOW4' if self.fast else 'LEGACY_ACK32',
                'optimize_windows': self.fast and self.stream.optimize_windows,
                'optimized_frames': self.stream.optimized_frames if self.fast else 0,
                'frame_samples': len(self.stream.frame_samples) if self.fast else 0,
                'frame_mean_ms': (sum(self.stream.frame_samples)/len(self.stream.frame_samples)
                                  if self.fast and self.stream.frame_samples else None),
                'frame_max_ms': (max(self.stream.frame_samples)
                                 if self.fast and self.stream.frame_samples else None),
                'frame_p95_ms': (sorted(self.stream.frame_samples)[int(.95*(len(self.stream.frame_samples)-1))]
                                 if self.fast and self.stream.frame_samples else None),
                'render_last_ms': self.render_last_ms, 'render_max_ms': self.render_max_ms,
                'render_count': self.render_count, 'timer_ticks': self.tick_count,
                'pending_operations': len(self.stream.inflight) if self.fast else int(self.stream.pending is not None),
                'max_pending': self.stream.max_pending if self.fast else 1,
                'coalesced_requests': self.stream.coalesced_requests if self.fast else None,
                'last_payload_bytes': self.stream.last_payload_bytes if self.fast else None,
                'last_wire_bytes': self.stream.last_wire_bytes if self.fast else None,
                'work_budget_active': self.stream.active_work if self.fast else None,
                'work_uart_budget_bytes_s': self.stream.work_bytes_per_second if self.fast else None,
                'mcu_oled': self.mcu_oled_stats,
                'configured_host_baud': self.host_baud,
                'urgent_refresh_pending': self.stream.urgent_refresh,
                'encoder_age': age, 'encoder_fresh': age is not None and age <= 1.,
                'encoder': self.encoder.previous, 'page': self.page,
                'encoder_capture': ('MCU_VALIDATED_DETENTS' if self.encoder.validated
                                    else 'LEGACY_RAW_POSITION'),
                'encoder_steps_per_detent': self.encoder.steps_per_detent,
                'menu_reverse': self.menu_reverse,
                'encoder_discontinuities': self.encoder.discontinuities,
                'selection': self.selection, 'hardware_verified': False,
                'job': self._job_status(now), 'job_view_token': self.job_token,
                'cancel_confirmation_token': self.cancel_token,
                'job_notice': self.job_notice,
                'filament': self._filament_status(now),
                'filament_view_token': self.filament_token,
                'filament_view_phase_id': self.filament_phase_id,
                'filament_cancel_confirmation_token': self.filament_cancel_token,
                'filament_notice': self.filament_notice}


def load_config(config):
    return M300OLED(config)
