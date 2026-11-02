# SPDX-License-Identifier: GPL-3.0-or-later
"""Classic M300 P01 board protocol and fail-closed host qualification gates.

ADC objects belong to the two native Klipper heaters. This module observes them
and configures the independent MCU guard; it never allocates another ADC owner.
P01 is a LAB port. A valid dictionary or FILEOUTPUT run is not hardware proof.
"""
import json
import logging
import math
from . import m300_hardware

ABI = 1
MODEL = 'M300_CLASSIC'
STAGE = 'P01_LAB'
CLOCK_FREQ = 72000000
ADC_MAX = 4095
ARM_MAGIC = 0x4d333031
HOT_RAW_MAX = 1941
BED_RAW_MIN = 1741
BED_RAW_MAX = 3941
STATUS_TIMEOUT = 0.750
ADC_TIMEOUT = 1.000
HEARTBEAT_PERIOD = 0.250
STATE_FORMAT = (
    'm300_state clock=%u configured=%c armed=%c fault=%c gates=%c inputs=%hu'
    ' adc_seen=%c hot_raw=%hu bed_raw=%hu hot_age=%u bed_age=%u'
    ' heartbeat_age=%u forced_cooling=%c')
LOCAL_COOLING_FORMAT = (
    'm300_local_cooling_state clock=%u mode=%c reason=%c raw=%hu age=%u'
    ' valid=%c hotend_on=%c print_on=%c on_raw=%hu off_raw=%hu owner=%c')
COOLING_MODES = {0: 'UNKNOWN_FAILSAFE', 1: 'NATIVE_HOST_PWM',
                 2: 'LOCAL_THERMOSTAT', 3: 'FAULT_COOLING'}
COOLING_OWNERS = {0: 'none', 1: 'native_ADC1_observation', 2: 'local_ADC2'}
COOLING_REASONS = {0: 'native_host', 1: 'startup_unknown', 2: 'local_thermostat',
                   3: 'stale_sample', 4: 'sample_out_of_range',
                   5: 'ADC_calibration_or_conversion_timeout',
                   6: 'critical_fault_latched'}
LOCAL_COOLING_ON_RAW = 314
LOCAL_COOLING_OFF_RAW = 281
FAULTS = {0: 'none', 1: 'heartbeat', 2: 'adc_stale', 3: 'platform_connector_PE15',
          4: 'adc_raw_range', 5: 'disarm_requires_firmware_restart',
          6: 'configuration', 7: 'arm_denied', 8: 'pin_policy',
          9: 'actuator_request_denied', 255: 'klipper_shutdown'}


def raw_limits(adc_min, adc_max):
    """Single-sample 12-bit limits; deliberately exclude both ADC rails."""
    if not all(math.isfinite(v) for v in (adc_min, adc_max)):
        raise ValueError('M300 ADC limits must be finite')
    low = max(1, int(math.ceil(adc_min * ADC_MAX)))
    high = min(ADC_MAX - 1, int(math.floor(adc_max * ADC_MAX)))
    if not 1 <= low < high <= ADC_MAX - 1:
        raise ValueError('M300 ADC limits must form a nonempty rail-excluding range')
    return low, high


def newer_clock32(clock, baseline):
    delta = (int(clock) - int(baseline)) & 0xffffffff
    return 0 < delta < 0x80000000


class M300StartupTransport:
    """Pace startup only; preserve native parsing, queues and runtime windows.

    Configuration GPIO/ADC setup must finish before the next config frame can
    arrive. Physical IRQ latency is not inferred from FILEOUTPUT tests.
    """
    REVISION = '0.13.14.1-STARTUP-ACK'
    ACK_TIMEOUT = 5.0

    def __init__(self, board):
        self.board, self.reactor = board, board.reactor
        self.phase, self.pending, self.error = 'INITIAL', None, None
        self.acked, self.clock_rate_ready = 0, False
        if board.mcu.is_fileoutput():
            self.phase = 'FILEOUTPUT_NO_UART'
            return
        self.serial = serial = board.mcu._serial
        helper = board.mcu._config_helper
        self._native_connect = serial.connect_uart
        self._native_configure = helper._send_cfg_init_commands
        self._native_get_config = helper._send_get_config
        # Install before mcu_identify: the native attach loads the dictionary
        # and then immediately starts ClockSync. Its SERIAL_BAUD constant is
        # only a fallback; use the baud actually passed to connect_uart.
        serial.connect_uart = self._connect_uart
        helper._send_cfg_init_commands = self._configure
        helper._send_get_config = self._get_config

    def _connect_uart(self, serialport, baud, *args, **kwargs):
        self.clock_rate_ready = False
        result = self._native_connect(serialport, baud, *args, **kwargs)
        self.serial.ffi_lib.serialqueue_set_wire_frequency(
            self.serial.serialqueue, baud)
        self.clock_rate_ready = True
        self.phase = 'IDENTIFIED'
        return result

    def _timeout(self, now):
        self.error = ('M300 startup: no MCU acknowledgement/response within '
                      '%.1f seconds while executing %s; explicit recovery required'
                      % (self.ACK_TIMEOUT, self.pending))
        self.phase = 'FAILED'
        logging.error(self.error)
        try:
            logging.error('M300 startup transport snapshot:\n%s',
                          self.serial.dump_debug())
        except Exception:
            logging.exception('M300 startup snapshot could not be decoded')
        # Native abort retains notification ids until disconnect, so a late
        # ACK is harmless and cannot kill the receiver thread or resume this
        # failed transaction. It does not reset/clear/ARM the MCU.
        self.serial.abort_wait_acks()
        return self.reactor.NEVER

    def _bounded(self, label, operation):
        if self.error is not None:
            raise self.board.config.error(self.error)
        self.pending = label
        timer = self.reactor.register_timer(
            self._timeout, self.reactor.monotonic() + self.ACK_TIMEOUT)
        try:
            result = operation()
            if self.error is not None:
                raise self.board.config.error(self.error)
            return result
        except Exception:
            if self.error is not None:
                raise self.board.config.error(self.error) from None
            self.phase = 'FAILED'
            raise
        finally:
            self.reactor.unregister_timer(timer)
            self.pending = None

    def _get_config(self):
        return self._bounded('get_config', self._native_get_config)

    def _configure(self, commands):
        serial = self.serial
        original_send = serial.send
        window = serial.get_msgparser().get_constant_int('RECEIVE_WINDOW')
        if window < 64:
            raise self.board.config.error('M300 startup requires a 64-byte receive window')
        self.phase = 'CONFIGURING_ACK_SERIAL'
        # ClockSync has a separate queue. A one-frame window prevents even
        # its clock query overlapping configuration command execution.
        serial.ffi_lib.serialqueue_set_receive_window(serial.serialqueue, 64)

        def send_one(message, minclock=0, reqclock=0):
            encoded = serial.get_msgparser().create_command(message)
            self._bounded(message, lambda: serial.raw_send_wait_ack(
                encoded, minclock, reqclock, serial.get_default_command_queue()))
            self.acked += 1

        serial.send = send_one
        try:
            # Keep native enumeration/pin-error handling and command ordering.
            self._native_configure(commands)
        except Exception:
            self.phase = 'FAILED'
            raise
        else:
            self.phase = 'CONFIGURATION_ACKED'
            # Restore the dictionary's runtime window for OLED/print traffic.
            serial.ffi_lib.serialqueue_set_receive_window(serial.serialqueue, window)
        finally:
            serial.send = original_send

    def get_status(self):
        return {'revision': self.REVISION, 'phase': self.phase,
                'commands_acked': self.acked, 'pending': self.pending,
                'error': self.error, 'ack_timeout_seconds': self.ACK_TIMEOUT,
                'wire_rate_before_clock_sync': self.clock_rate_ready,
                'automatic_arm': False, 'automatic_reset': False}


class M300MCU:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.mcu_name = config.get('mcu', 'mcu')
        self.mcu = self.printer.lookup_object(self.mcu_name)
        self.allow_actuators = config.getboolean('allow_actuators', False)
        self.allow_motion = config.getboolean('allow_motion', False)
        self.allow_heating = config.getboolean('allow_heating', False)
        self.require_local_cooling = config.getboolean('require_local_cooling', False)
        self.native_control = config.getboolean('native_control', False)
        self.native_initialization = 'NOT_STARTED'
        self.native_core_report = {}
        if (self.allow_motion or self.allow_heating) and not self.allow_actuators:
            raise config.error('M300 allow_motion/allow_heating require allow_actuators=True')
        self.gates = ((int(self.allow_motion) | (int(self.allow_heating) << 1))
                      if self.allow_actuators else 0)
        self.identified = self.connected = self.ready = False
        self.local_stop = False
        self.arm_requested_at = None
        self.arm_request_clock = None
        self.arm_session_confirmed = False
        self.state = {}
        self.uart_state = {}
        self._uart_query = None
        self.fan_policy = 1
        self.local_cooling_abi = 0
        self.cooling_state = {}
        self.last_cooling_time = None
        self._cooling_query = None
        self.last_state_time = None
        self.adcs = {}
        self.guard_limits = {}
        self._heartbeat_cmd = self._query_cmd = self._arm_cmd = None
        self._disarm_cmd = None
        self._fault_reported = False
        self.startup_transport = M300StartupTransport(self)
        self.hardware = m300_hardware.M300Hardware(self, config)
        self._timer = self.reactor.register_timer(self._tick)
        self.mcu.register_config_callback(self._build_config)
        if self.native_control:
            self.printer.register_event_handler('klippy:connect', self._native_connect)
        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.printer.register_event_handler('klippy:shutdown', self._handle_shutdown)
        self.printer.register_event_handler('klippy:disconnect', self._handle_disconnect)
        self.printer.register_event_handler('gcode:request_restart', self._handle_restart)
        self.gcode.register_command('ZORTRAX_MCU_STATUS', self.cmd_status,
                                    when_not_ready=True)
        self.gcode.register_command('ZORTRAX_INPUTS', self.cmd_inputs,
                                    when_not_ready=True)
        self.gcode.register_command('ZORTRAX_NATIVE_STATUS', self.cmd_native_status,
                                    when_not_ready=True)
        self.gcode.register_command('ZORTRAX_ARM', self.cmd_arm)
        self.gcode.register_command('ZORTRAX_DISARM', self.cmd_disarm)

    def get_mcu(self):
        return self.mcu

    def is_ready(self):
        return self.ready and self.identified and not self.local_stop

    def _build_config(self):
        constants = self.mcu.get_constants()
        self.mcu_release = constants.get('M300_MCU_RELEASE', 'legacy')
        expected = {'MCU': 'stm32f103xe', 'M300_ABI': ABI, 'M300_MODEL': MODEL,
                    'M300_STAGE': STAGE, 'CLOCK_FREQ': CLOCK_FREQ,
                    'ADC_MAX': ADC_MAX, 'M300_SOFTWARE_PWM_ONLY': 1,
                    'M300_ARM_MAGIC': ARM_MAGIC,
                    'M300_HOT_RAW_MAX': HOT_RAW_MAX,
                    'M300_BED_RAW_MIN': BED_RAW_MIN,
                    'M300_BED_RAW_MAX': BED_RAW_MAX}
        for key, value in expected.items():
            actual = constants.get(key)
            if str(actual) != str(value):
                raise self.config.error('M300 %s must be %s (got %r)' %
                                        (key, value, actual))
        self.fan_policy = int(constants.get('M300_FAN_POLICY', 1))
        self.local_cooling_abi = int(constants.get('M300_LOCAL_COOLING_ABI', 0))
        if getattr(self, 'require_local_cooling', False) and self.fan_policy != 3:
            raise self.config.error('M300 R14 requires MCU fan policy 3 with autonomous cooling')
        if self.fan_policy not in (1, 2, 3):
            raise self.config.error('M300 unknown MCU fan policy')
        if self.fan_policy == 3:
            if self.local_cooling_abi != 1:
                raise self.config.error('M300 fan policy 3 requires local cooling ABI 1')
            if (int(constants.get('M300_LOCAL_COOLING_ON_RAW', 0)) != LOCAL_COOLING_ON_RAW
                    or int(constants.get('M300_LOCAL_COOLING_OFF_RAW', 0)) != LOCAL_COOLING_OFF_RAW):
                raise self.config.error('M300 local cooling thresholds do not match the R14 contract')
            if not self.mcu.check_valid_response(LOCAL_COOLING_FORMAT):
                raise self.config.error('M300 missing/incompatible local cooling response')
            self._cooling_query = self.mcu.lookup_command('m300_local_cooling_query')
            self.mcu.register_serial_response(self._handle_cooling, LOCAL_COOLING_FORMAT)
            self.mcu.add_config_cmd('m300_local_cooling_query', is_init=True)
        elif self.local_cooling_abi:
            raise self.config.error('M300 local cooling ABI requires fan policy 3')
        if int(constants.get('M300_UART_PERSIST_ABI', 0)) == 1:
            baud = self.config.getsection(self.mcu_name).getint('baud', 250000)
            if baud not in (19200,57600,115200,250000,500000,750000,1000000,1500000):
                raise self.config.error('Unsupported M300Boot UART baud')
            if baud > 500000 and int(constants.get('M300_UART_RATE_COUNT',5)) < 7:
                raise self.config.error('MCU UART7 firmware required for this baud')
            if baud > 1000000 and int(constants.get('M300_UART_RATE_COUNT',5)) < 8:
                raise self.config.error('MCU UART8 firmware required for 1500000 baud')
            self.uart_state = {'host_baud': baud, 'baud': None, 'match': None}
            # The dictionary's SERIAL_BAUD is the compile-time fallback only.
            # Identification is stop-and-wait. Set pacing before MCU config or
            # queued production traffic using the confirmed host UART setting.
            serial = self.mcu._serial
            serial.ffi_lib.serialqueue_set_wire_frequency(serial.serialqueue, baud)
            self._uart_query = self.mcu.lookup_command('m300_uart_query')
            fmt = 'm300_uart_state baud=%u saved=%c index=%c used=%hu invalid=%hu'
            if not self.mcu.check_valid_response(fmt):
                raise self.config.error('Missing M300 runtime UART response')
            self.mcu.register_serial_response(self._handle_uart, fmt)
        # Explicitly reject an incompatible native software-PWM protocol before
        # any config bytes are emitted. Native pins perform the same lookups.
        for fmt in ('set_digital_out_pwm_cycle oid=%c cycle_ticks=%u',
                    'queue_digital_out oid=%c clock=%u on_ticks=%u'):
            self.mcu.lookup_command(fmt)
        self._heartbeat_cmd = self.mcu.lookup_command('m300_heartbeat')
        self._query_cmd = self.mcu.lookup_command('m300_query')
        self._arm_cmd = self.mcu.lookup_command('m300_arm magic=%u')
        self._disarm_cmd = self.mcu.lookup_command('m300_disarm')
        self.mcu.lookup_command('m300_config gates=%c hot_min=%hu hot_max=%hu'
                                ' bed_min=%hu bed_max=%hu')
        if not self.mcu.check_valid_response(STATE_FORMAT):
            raise self.config.error('M300 missing/incompatible response: m300_state')
        self.mcu.register_serial_response(self._handle_state, STATE_FORMAT)
        heaters = self.printer.lookup_object('heaters')
        for name in ('extruder', 'heater_bed'):
            heater = heaters.lookup_heater(name)
            adc = getattr(heater.sensor, 'mcu_adc', None)
            if adc is None or adc.get_mcu() is not self.mcu:
                raise self.config.error('M300 %s requires one native local ADC sensor' % name)
            try:
                limits = raw_limits(adc._min_sample, adc._max_sample)
            except ValueError as exc:
                raise self.config.error(str(exc))
            self.adcs[name] = adc
            self.guard_limits[name] = limits
        hot = self.guard_limits['extruder']
        bed = self.guard_limits['heater_bed']
        if hot[1] > HOT_RAW_MAX or bed[0] < BED_RAW_MIN or bed[1] > BED_RAW_MAX:
            raise self.config.error('M300 heater ADC range exceeds independent MCU LAB hard limits')
        self.mcu.add_config_cmd(
            'm300_config gates=%d hot_min=%d hot_max=%d bed_min=%d bed_max=%d'
            % (self.gates, hot[0], hot[1], bed[0], bed[1]))
        # No automatic arm: file-output and a reconnect cannot authorize motion.
        self.mcu.add_config_cmd('m300_heartbeat', is_init=True)
        self.mcu.add_config_cmd('m300_query', is_init=True)
        self.identified = True

    def _native_connect(self):
        """Board enable is hardware initialization, before Klippy Ready.

        The existing MCU latch/heartbeat/ADC protection is retained. No G0/G1,
        heater or fan command is wrapped and no per-command enable is needed.
        Native ready callbacks may not pause, so all waiting is done here.
        """
        if self.mcu.is_fileoutput():
            self.native_initialization = 'FILEOUTPUT_NO_MCU_EXECUTION'
            return
        self.native_initialization = 'WAITING_FOR_NATIVE_ADC'
        self.connected = self.ready = True
        self.reactor.update_timer(self._timer, self.reactor.NOW)
        deadline = self.reactor.monotonic() + 6.
        try:
            while not self._healthy(self.reactor.monotonic()):
                if self.local_stop or self.printer.is_shutdown():
                    raise self.config.error('M300 native board initialization stopped by MCU fault')
                now = self.reactor.monotonic()
                if now >= deadline:
                    raise self.config.error('M300 native board initialization: native ADC/status timeout')
                self.reactor.pause(min(deadline, now + .020))
            if self.state.get('armed'):
                raise self.config.error('M300 native initialization found an old armed session')
            self.native_initialization = 'WAITING_FOR_BOARD_ENABLE'
            command = self.gcode.create_gcode_command(
                'ZORTRAX_ARM', 'ZORTRAX_ARM', {'ACK': 'M300_LAB_QUALIFIED'})
            self.cmd_arm(command)
            deadline = self.arm_requested_at + STATUS_TIMEOUT
            while not self._healthy(self.reactor.monotonic(), armed=True):
                if self.local_stop or self.printer.is_shutdown():
                    raise self.config.error('M300 native board enable failed')
                now = self.reactor.monotonic()
                if now >= deadline:
                    raise self.config.error('M300 native board enable acknowledgement timeout')
                self.reactor.pause(min(deadline, now + .010))
            self.native_initialization = 'READY'
        except Exception:
            self.native_initialization = 'FAILED'
            self._handle_stop()
            raise

    def _handle_ready(self):
        if getattr(self, 'native_control', False):
            self.connected = True
            self.ready = not self.local_stop
            if not self.mcu.is_fileoutput() and (
                    self.native_initialization != 'READY'
                    or not self._healthy(self.reactor.monotonic(), armed=True)):
                self.printer.invoke_async_shutdown('M300 native board initialization incomplete')
                return
            self.native_core_report = self.native_status()
            # Native Ready also needs to fetch the *actual* saved MCU baud.
            # Previously only the LAB branch sent m300_uart_query; reports
            # could stay baud=null/match=null indefinitely despite a live link.
            if not self.mcu.is_fileoutput():
                if self._uart_query is not None:
                    self._uart_query.send([])
                if self._cooling_query is not None:
                    self._cooling_query.send([])
            self.reactor.update_timer(self._timer, self.reactor.NOW)
            return
        self._close_arm_session()
        self.connected = True
        self.ready = not self.local_stop
        if self.local_stop:
            return
        if self.state.get('armed'):
            self.local_stop = True
            self.ready = False
            self.printer.invoke_async_shutdown(
                'M300 MCU already armed at host ready; FIRMWARE_RESTART required')
            return
        if getattr(self, '_uart_query', None) is not None:
            self._uart_query.send([])
        if getattr(self, '_cooling_query', None) is not None:
            self._cooling_query.send([])
        self.reactor.update_timer(self._timer, self.reactor.NOW)

    def _handle_uart(self, params):
        sample={key: params[key] for key in ('baud','saved','index','used','invalid')}
        state=self.uart_state
        def deliver(now):
            if not self.connected or self.local_stop or self.uart_state is not state:
                return
            state.update(sample)
            state['match'] = sample['baud'] == state['host_baud']
            if not state['match']:
                self.printer.invoke_async_shutdown('M300 host UART differs from MCU saved baud')
        self.reactor.register_async_callback(deliver)

    def _close_arm_session(self):
        self.arm_requested_at = None
        self.arm_request_clock = None
        self.arm_session_confirmed = False

    def _handle_cooling(self, params):
        # This telemetry cannot authorize ARM/heating/motion. It reports the
        # selected cooling owner and actual digital outputs while offline.
        keys = ('clock', 'mode', 'reason', 'raw', 'age', 'valid',
                'hotend_on', 'print_on', 'on_raw', 'off_raw', 'owner')
        sample = {key: params[key] for key in keys}
        if (sample['mode'] not in COOLING_MODES
                or sample['owner'] not in COOLING_OWNERS
                or any(sample[key] not in (0, 1)
                       for key in ('valid', 'hotend_on', 'print_on'))
                or not 0 <= sample['raw'] <= ADC_MAX
                or sample['on_raw'] != LOCAL_COOLING_ON_RAW
                or sample['off_raw'] != LOCAL_COOLING_OFF_RAW):
            self.cooling_state = {}
            self.last_cooling_time = None
            self.printer.invoke_async_shutdown('M300 invalid local cooling telemetry')
            return
        received = params.get('#receive_time', self.reactor.monotonic())
        if (self.last_cooling_time is not None
                and received < self.last_cooling_time):
            return
        self.cooling_state = sample
        self.last_cooling_time = received

    def _cooling_status(self, eventtime):
        state = getattr(self, 'cooling_state', {})
        received = getattr(self, 'last_cooling_time', None)
        fresh = (received is not None
                 and 0. <= eventtime - received <= STATUS_TIMEOUT)
        mode = state.get('mode')
        raw = state.get('raw')
        sample_age = (state.get('age', 0xffffffff) / CLOCK_FREQ
                      + eventtime - received if fresh else None)
        valid = (bool(state.get('valid')) and sample_age is not None
                 and 0. <= sample_age < ADC_TIMEOUT
                 and raw is not None and 0 < raw < ADC_MAX)
        return {'abi': getattr(self, 'local_cooling_abi', 0),
                'available': getattr(self, 'fan_policy', 1) == 3,
                'status_fresh': fresh, 'mode': COOLING_MODES.get(mode, 'UNKNOWN') if fresh else 'UNKNOWN',
                'mode_code': mode if fresh else None,
                'owner': COOLING_OWNERS.get(state.get('owner'), 'unknown') if fresh else 'unknown',
                'reason_code': state.get('reason') if fresh else None,
                'reason': COOLING_REASONS.get(state.get('reason'), 'unknown') if fresh else 'unknown',
                'sample_valid': valid,
                'sample_age_seconds': sample_age,
                'raw': raw if fresh else None,
                'temperature': raw * 654. / 4095. if valid and raw is not None else None,
                'hotend_on': bool(state.get('hotend_on')) if fresh else None,
                'print_on': bool(state.get('print_on')) if fresh else None,
                'on_raw': state.get('on_raw') if fresh else None,
                'off_raw': state.get('off_raw') if fresh else None,
                'on_temperature': state.get('on_raw') * 654. / 4095. if fresh else None,
                'off_temperature': state.get('off_raw') * 654. / 4095. if fresh else None,
                'automatic_arm': False, 'automatic_fault_clear': False}

    def _handle_stop(self, *args):
        self._close_arm_session()
        self.ready = False
        self.local_stop = True
        self.reactor.update_timer(self._timer, self.reactor.NEVER)

    def _handle_disconnect(self, *args):
        self.connected = False
        self._handle_stop()

    def _handle_shutdown(self, *args):
        self._handle_stop()
        # m300_query is explicitly HF_IN_SHUTDOWN in the existing MCU.
        # Read the latched reason after native emergency_stop; do not send a
        # heartbeat, ARM, fault clear, reset or any actuator command.
        if self.connected and self._query_cmd is not None:
            try:
                self._query_cmd.send()
            except Exception:
                logging.exception('M300 could not read latched guard after shutdown')

    def _handle_restart(self, *args):
        # Stop authorizing commands immediately. A real MCU retains its latch or
        # watchdog state; FIRMWARE_RESTART is required after disarm/fault.
        self._handle_stop()

    def _tick(self, eventtime):
        if not self.ready or self.local_stop:
            return self.reactor.NEVER
        if (self.arm_requested_at is not None and not self.arm_session_confirmed
                and eventtime - self.arm_requested_at > STATUS_TIMEOUT):
            self.local_stop = True
            self._close_arm_session()
            self.printer.invoke_shutdown('M300 ARM acknowledgement timeout; FIRMWARE_RESTART required')
            return self.reactor.NEVER
        if self.state.get('armed') and not self._healthy(eventtime, armed=True):
            self.local_stop = True
            self._close_arm_session()
            self.printer.invoke_shutdown('M300 armed guard status stale or unsafe')
            return self.reactor.NEVER
        self._heartbeat_cmd.send()
        self._query_cmd.send()
        if getattr(self, '_cooling_query', None) is not None:
            self._cooling_query.send([])
        return eventtime + HEARTBEAT_PERIOD

    def _handle_state(self, params):
        self.state = {key: value for key, value in params.items()
                      if not key.startswith('#')}
        # Preserve serial receipt time: a delayed callback must not make an old
        # packet appear fresh merely because the host finally processed it.
        self.last_state_time = params.get('#receive_time', self.reactor.monotonic())
        if self.state.get('fault') and not self._fault_reported:
            self._fault_reported = True
            logging.error('M300_LATCHED_GUARD %s', json.dumps(
                dict(self.state, fault_reason=FAULTS.get(self.state['fault'], 'unknown')),
                sort_keys=True))
            self.local_stop = True
            self._close_arm_session()
            # After a native Timer-too-close shutdown, fault=255 is a
            # consequence of Klipper shutting down. Read the diagnostic but
            # do not replace the original reason with a second shutdown.
            if not self.printer.is_shutdown():
                self.printer.invoke_async_shutdown(
                    'M300 guard fault %s (%s); FIRMWARE_RESTART required' %
                    (self.state['fault'], FAULTS.get(self.state['fault'], 'unknown')))
            return
        if self.state.get('armed'):
            # A fresh report from an old, still-armed MCU must not authorize a
            # newly started host. Confirmation belongs to THIS host request.
            requested = (self.arm_requested_at is not None
                         and self.arm_request_clock is not None)
            valid_ack = (requested and self.last_state_time >= self.arm_requested_at
                         and (self.arm_session_confirmed or (
                             self.last_state_time - self.arm_requested_at <= STATUS_TIMEOUT
                             and newer_clock32(self.state.get('clock', 0),
                                               self.arm_request_clock))))
            # Only the FIRST acknowledgement is compared with the ARM baseline.
            # A long-running session can cross the half/full 32-bit clock wrap;
            # subsequent packets are governed by their receipt/ADC freshness.
            if not valid_ack or self.local_stop:
                self.local_stop = True
                self._close_arm_session()
                if not self._fault_reported:
                    self._fault_reported = True
                    self.printer.invoke_async_shutdown(
                        'M300 unexpected or stale armed acknowledgement; FIRMWARE_RESTART required')
                return
            self.arm_session_confirmed = True
        elif self.arm_session_confirmed:
            # Any observed transition back to unarmed ends this authorization.
            self._close_arm_session()

    def _healthy(self, eventtime, armed=False):
        s = self.state
        if (not self.ready or not self.connected or self.local_stop
                or self.last_state_time is None
                or not 0. <= eventtime - self.last_state_time <= STATUS_TIMEOUT):
            return False
        if (not s.get('configured') or s.get('fault') or s.get('gates') != self.gates
                or s.get('adc_seen', 0) & 3 != 3 or s.get('inputs', 1) & 1):
            return False
        if armed and (not s.get('armed') or not self.arm_session_confirmed
                      or self.arm_requested_at is None):
            return False
        limit = int(ADC_TIMEOUT * CLOCK_FREQ)
        if any(not 0 <= s.get(key, 0xffffffff) < limit
               for key in ('hot_age', 'bed_age', 'heartbeat_age')):
            return False
        for name, key in (('extruder', 'hot_raw'), ('heater_bed', 'bed_raw')):
            low, high = self.guard_limits.get(name, (1, 0))
            if not low <= s.get(key, -1) <= high:
                return False
        return True

    def require_motion(self):
        if not self.allow_actuators or not self.allow_motion:
            raise self.printer.command_error('M300 motion is not qualified/enabled')
        if not self._healthy(self.reactor.monotonic(), armed=True):
            raise self.printer.command_error('M300 requires fresh armed fault-free MCU status for motion')

    def require_heating(self):
        if not self.allow_actuators or not self.allow_heating:
            raise self.printer.command_error('M300 heating is not qualified/enabled')
        if not self._healthy(self.reactor.monotonic(), armed=True):
            raise self.printer.command_error('M300 requires fresh armed fault-free MCU status for heating')

    def get_status(self, eventtime):
        fresh = (self.last_state_time is not None
                 and 0. <= eventtime - self.last_state_time <= STATUS_TIMEOUT)
        native_adc = {}
        for name, adc in self.adcs.items():
            stamp, normalized = adc.get_last_value()
            native_adc[name] = {'sample_print_time': stamp,
                                'normalized': normalized,
                                'sample_observed': bool(stamp),
                                'owner': 'native_heater_sensor'}
        bits = self.state.get('inputs', 0)
        inputs = {'status_fresh': fresh,
                  'platform_connector_fault': bool(bits & 1) if fresh else None,
                  'filament_module_present': not bool(bits & 2) if fresh else None,
                  'filament_runout': (not bool(bits & 4)
                                     if fresh and not bits & 2 else None)}
        policy = getattr(self, 'fan_policy', 1)
        cooling = self._cooling_status(eventtime)
        if policy == 3:
            policy_name = ('native_PWM_when_healthy_independent_of_ARM; '
                           'offline_local_hotend_thermostat_print_OFF; '
                           'invalid_or_stale_local_sample_or_critical_latch_both_HIGH')
        elif policy == 2:
            policy_name = ('both_PE13_PE14_HIGH_on_missing_configuration_stale_link_ADC_fault_or_shutdown; '
                           'native_PWM_when_healthy_independent_of_ARM')
        else:
            policy_name = 'both_PE13_PE14_HIGH_while_unarmed_or_fault'
        return {'model': MODEL, 'abi': ABI, 'stage': STAGE,
                'mcu_release': getattr(self, 'mcu_release', 'legacy'),
                'uart': dict(getattr(self, 'uart_state', {})),
                'hardware': self.hardware.get_status(),
                'startup_transport': (self.startup_transport.get_status()
                    if hasattr(self, 'startup_transport') else {}),
                'identified': self.identified, 'connected': self.connected,
                'native_control': getattr(self, 'native_control', False),
                'native_initialization': getattr(self, 'native_initialization', 'LEGACY'),
                'native_core': getattr(self, 'native_core_report', {}),
                'ready': self.ready, 'allow_actuators': self.allow_actuators,
                'allow_motion': self.allow_motion, 'allow_heating': self.allow_heating,
                'configured_gates': self.gates, 'status_fresh': fresh,
                'armed': (bool(self.state.get('armed')) and fresh
                          and self.arm_session_confirmed and not self.local_stop),
                'arm_requested': self.arm_requested_at is not None,
                'arm_session_confirmed': self.arm_session_confirmed,
                'fault': self.state.get('fault'), 'local_stop': self.local_stop,
                'forced_cooling': (True if not fresh or self.local_stop else
                                   bool(self.state.get('forced_cooling', 1))),
                'fan_policy_abi': policy, 'local_cooling': cooling,
                'local_cooling_required': getattr(self, 'require_local_cooling', False),
                'forced_cooling_policy': policy_name,
                'hardware_qualified': False,
                'mode': ('FILEOUTPUT_NO_MCU_EXECUTION' if self.mcu.is_fileoutput()
                         else 'LIVE_HOST_CONFIGURATION'),
                'guard_limits_single_adc': dict(self.guard_limits),
                'native_adc_observation': native_adc, 'inputs': inputs,
                'mcu_state': dict(self.state)}

    def cmd_status(self, gcmd):
        if (self.connected and self.printer.is_shutdown()
                and self._query_cmd is not None):
            previous = self.last_state_time
            self._query_cmd.send()
            deadline = self.reactor.monotonic() + .5
            while self.last_state_time == previous and self.reactor.monotonic() < deadline:
                self.reactor.pause(min(deadline, self.reactor.monotonic()+.02))
        gcmd.respond_info('M300_MCU ' + json.dumps(
            self.get_status(self.reactor.monotonic()), sort_keys=True))

    def native_status(self):
        def owner(value):
            fn = getattr(value, '__func__', value)
            # Native extended commands have one GCodeDispatch parameter-parser
            # lambda. Report its original handler, not a fabricated owner.
            if (getattr(fn, '__module__', '') == 'gcode'
                    and getattr(fn, '__qualname__', '').startswith(
                        'GCodeDispatch.register_command.')
                    and getattr(fn, '__closure__', None)):
                captures = dict(zip(fn.__code__.co_freevars,
                                    (cell.cell_contents for cell in fn.__closure__)))
                if callable(captures.get('origfunc')):
                    return owner(captures['origfunc'])
            return getattr(fn, '__module__', '') + '.' + getattr(fn, '__qualname__', str(fn))
        result = {'revision': '0.13.15-NATIVE-CORE',
                  'native_control': getattr(self, 'native_control', False),
                  'initialization': getattr(self, 'native_initialization', 'LEGACY'),
                  'owners': {}, 'physical_hardware_qualified': False}
        toolhead = self.printer.lookup_object('toolhead', None)
        if toolhead is not None:
            for name in ('move', 'drip_move', 'set_position'):
                result['owners']['toolhead.' + name] = owner(getattr(toolhead, name))
            result['owners']['extruder.check_move'] = owner(
                toolhead.get_extruder().check_move)
        heaters = self.printer.lookup_object('heaters', None)
        if heaters is not None:
            for name in ('extruder', 'heater_bed'):
                heater = heaters.lookup_heater(name)
                for method in ('set_temp', 'set_pwm', 'alter_target'):
                    result['owners'][name + '.' + method] = owner(getattr(heater, method))
                result['owners'][name + '.pwm'] = type(heater.mcu_pwm).__module__ + '.' + type(heater.mcu_pwm).__name__
        commands = getattr(self.gcode, 'ready_gcode_handlers', {})
        for name in ('G0', 'G1', 'M104', 'M140', 'M106', 'M107',
                     'PID_CALIBRATE', 'SAVE_CONFIG', 'PAUSE', 'RESUME'):
            result['owners'][name] = owner(commands.get(name))
        mux = getattr(self.gcode, 'mux_commands', {}).get('PID_CALIBRATE')
        if mux is not None:
            for heater, callback in mux[1].items():
                result['owners']['PID_CALIBRATE:' + str(heater)] = owner(callback)
        fan = self.printer.lookup_object('fan', None)
        if fan is not None:
            result['owners']['fan.set_speed'] = owner(fan.fan.set_speed)
        return result

    def cmd_native_status(self, gcmd):
        gcmd.respond_info('M300_NATIVE ' + json.dumps(self.native_status(), sort_keys=True))

    def cmd_inputs(self, gcmd):
        fresh = self.last_state_time is not None and (
            0. <= self.reactor.monotonic() - self.last_state_time <= STATUS_TIMEOUT)
        bits = self.state.get('inputs', 0)
        gcmd.respond_info('M300_INPUTS ' + json.dumps({
            'status_fresh': fresh, 'raw_mask': bits if fresh else None,
            'platform_connector_fault': bool(bits & 1) if fresh else None,
            'filament_module_present': not bool(bits & 2) if fresh else None,
            'filament_runout': (not bool(bits & 4) if fresh and not bits & 2 else None),
            'encoder_a': bool(bits & 8) if fresh else None,
            'encoder_b': bool(bits & 16) if fresh else None,
            'encoder_button_raw': bool(bits & 32) if fresh else None,
            'policy': 'diagnostic only; no automatic pause/resume in P01'}, sort_keys=True))

    def cmd_arm(self, gcmd):
        if not self.allow_actuators:
            raise gcmd.error('M300 allow_actuators=False; P01 defaults are unqualified')
        if not self.gates:
            raise gcmd.error('M300 no motion/heating gate is enabled')
        if gcmd.get('ACK', '') != 'M300_LAB_QUALIFIED':
            raise gcmd.error('M300 ARM requires ACK=M300_LAB_QUALIFIED after hardware qualification')
        if not self._healthy(self.reactor.monotonic()):
            raise gcmd.error('M300 ARM requires fresh healthy MCU/ADC/PE15 status')
        if self.state.get('armed'):
            raise gcmd.error('M300 already armed')
        if self.arm_requested_at is not None:
            raise gcmd.error('M300 ARM acknowledgement pending')
        self.arm_requested_at = self.reactor.monotonic()
        self.arm_request_clock = self.state['clock']
        self.arm_session_confirmed = False
        try:
            self._heartbeat_cmd.send()
            self._arm_cmd.send([ARM_MAGIC])
            self._query_cmd.send()
        except Exception:
            self.local_stop = True
            self._close_arm_session()
            self.printer.invoke_shutdown('M300 ARM transport failed; FIRMWARE_RESTART required')
            raise
        gcmd.respond_info('M300 ARM requested; motion/heating wait for fresh MCU armed acknowledgement')

    def cmd_disarm(self, gcmd):
        self.local_stop = True
        self._close_arm_session()
        if self._disarm_cmd is not None:
            self._disarm_cmd.send()
        self.printer.invoke_shutdown('M300 DISARM; FIRMWARE_RESTART required')


def load_config(config):
    return M300MCU(config)
