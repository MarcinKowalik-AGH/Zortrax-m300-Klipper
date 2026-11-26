# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional STM32F103 die temperature telemetry; no heater or graph series."""
import json
import math

SAMPLE_TIME = 0.001
SAMPLE_COUNT = 8


def temperature_from_adc(value, voltage, offset):
    # STM32F103 nominal V25=1.43 V, Avg_Slope=4.3 mV/C (DS5792).
    return 25. + (1.43 - value * voltage) / .0043 + offset


class M300MCUTemperature:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.report_time = config.getfloat('report_time', 5., minval=1., maxval=60.)
        self.voltage = config.getfloat('adc_voltage', 3.3, minval=2.4, maxval=3.6)
        self.offset = config.getfloat('temperature_offset', 0., minval=-100., maxval=100.)
        if not all(math.isfinite(v) for v in (self.report_time, self.voltage, self.offset)):
            raise config.error('MCU temperature settings must be finite')
        self.temperature = self.fraction = self.received = None
        self.state = 'STARTING'
        pins = self.printer.lookup_object('pins')
        self.adc = pins.setup_pin('adc', 'mcu:ADC_TEMPERATURE')
        self.mcu = self.adc.get_mcu()
        self.adc.setup_adc_sample(self.report_time, SAMPLE_TIME, SAMPLE_COUNT,
                                  minval=0., maxval=1., range_check_count=0)
        self.adc.setup_adc_callback(self._receive)
        self.printer.register_event_handler('klippy:mcu_identify', self._identify)
        self.printer.register_event_handler('klippy:disconnect', self._disconnect)
        self.printer.register_event_handler('klippy:shutdown', self._shutdown)
        self.printer.lookup_object('gcode').register_command(
            'M300_MCU_TEMPERATURE', self.cmd_temperature, when_not_ready=True,
            desc='Read STM32 die temperature diagnostics without adding a graph series')

    def _identify(self):
        constants = self.mcu.get_constants()
        if (constants.get('MCU') != 'stm32f103xe'
                or constants.get('M300_MCU_TEMPERATURE_ABI') != 1):
            raise self.printer.config_error(
                'm300_mcu_temperature requires M300 Classic MCU 1.0.9 or newer '
                'with M300_MCU_TEMPERATURE_ABI=1; disable its include on older firmware')
        self.state = 'WAITING_FOR_SAMPLE'

    def _disconnect(self):
        self.temperature = self.fraction = self.received = None
        self.state = 'DISCONNECTED'

    def _shutdown(self):
        self.temperature = self.fraction = self.received = None
        self.state = 'SHUTDOWN'

    def _receive(self, samples):
        if not samples or self.state in ('DISCONNECTED', 'SHUTDOWN'):
            return
        read_time, value = samples[-1]
        age = self.mcu.estimated_print_time(self.reactor.monotonic()) - read_time
        if not math.isfinite(age) or age < -1. or age > self.report_time * 3.:
            self.temperature = self.fraction = self.received = None
            self.state = 'STALE'
            return
        # Do not present an ADC rail or non-finite conversion as a temperature.
        if not math.isfinite(value) or not 0. < value < 1.:
            self.temperature = self.fraction = self.received = None
            self.state = 'INVALID_ADC'
            return
        self.temperature = temperature_from_adc(value, self.voltage, self.offset)
        self.fraction = value
        self.received = self.reactor.monotonic() - max(0., age)
        self.state = 'READY'

    def get_status(self, eventtime):
        age = None if self.received is None else eventtime - self.received
        fresh = (self.state == 'READY' and age is not None
                 and 0. <= age <= self.report_time * 3.)
        state = 'STALE' if self.state == 'READY' and not fresh else self.state
        return {'state': state, 'temperature': self.temperature if fresh else None,
                'adc_fraction': self.fraction if fresh else None,
                'adc_raw': self.fraction * 4095. if fresh else None,
                'adc_voltage': self.voltage, 'temperature_offset': self.offset,
                'report_time': self.report_time, 'sample_age': age,
                'approximate': True, 'graph_series': False}

    def cmd_temperature(self, gcmd):
        gcmd.respond_info('M300_MCU_TEMPERATURE ' + json.dumps(
            self.get_status(self.reactor.monotonic()), sort_keys=True))


def load_config(config):
    return M300MCUTemperature(config)
