# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact classic-M300 resource census, before MCU configuration is sent."""
import json
from .m300_io import OUTPUTS
from .m300_mcu import ABI, MODEL, CLOCK_FREQ

MCU_ONLY = {
    'PB10': 'X MS1 HIGH', 'PB11': 'X MS2 HIGH', 'PD8': 'X MS3 HIGH',
    'PD10': 'Y MS1 HIGH', 'PD11': 'Y MS2 HIGH', 'PD12': 'Y MS3 HIGH',
    'PA15': 'Z MS1 LOW', 'PC10': 'Z MS2 LOW', 'PC11': 'Z MS3 HIGH',
    'PE15': 'platform small connector guard input', 'PD5': 'filament module present input',
    'PD1': 'filament input',
    'PB13': 'OLED private hardware SPI2 TX-only clock', 'PB15': 'OLED private hardware SPI2 MOSI',
    'PB12': 'OLED chip select', 'PB14': 'OLED D/C (not SPI2 MISO)',
    'PE10': 'OLED reset', 'PE9': 'OLED power gate',
    'PE7': 'encoder A', 'PE8': 'encoder B', 'PC5': 'encoder button',
    'PA9': 'USART1 TX host transport', 'PA10': 'USART1 RX host transport',
}
EXCLUDED = {'PA4': 'physical SD chip select outside P01',
            'PA5': 'physical SD SPI1 clock outside P01',
            'PA6': 'physical SD SPI1 MISO outside P01',
            'PA7': 'physical SD SPI1 MOSI outside P01',
            'PA8': 'unassigned; no verified stock consumer',
            'PB2': 'boot strap/unassigned; no verified stock consumer',
            'PD15': 'unassigned; no verified stock consumer',
            'PA13': 'SWDIO', 'PA14': 'SWCLK'}
WIRING = {
    'stepper_x': {'step_pin': 'PB3', 'dir_pin': 'PD9', 'enable_pin': 'PD14',
                  'endstop_pin': 'PE12'},
    'stepper_y': {'step_pin': 'PB4', 'dir_pin': 'PD13', 'enable_pin': 'PD14',
                  'endstop_pin': 'PC6'},
    'stepper_z': {'step_pin': 'PB7', 'dir_pin': 'PC12', 'enable_pin': 'PD14'},
    'extruder': {'step_pin': 'PA0', 'dir_pin': 'PD0', 'enable_pin': 'PD14'},
    'probe': {'pin': 'PC7'},
    'output_pin m300_led_r': {'pin': 'PD7'},
    'output_pin m300_led_g': {'pin': 'PB5'},
    'output_pin m300_led_b': {'pin': 'PD6'},
    'output_pin m300_buzzer': {'pin': 'PC4'},
}
REQUIRED_STEPPERS = {'stepper_x', 'stepper_y', 'stepper_z', 'extruder'}
REQUIRED_HEATERS = {'extruder', 'heater_bed'}
ADC_PINS = {'extruder': 'PB1', 'heater_bed': 'PB0'}
PRIVATE_SD = {'PA4': 'private physical SD chip select',
              'PA5': 'private physical SD SPI1 clock',
              'PA6': 'private physical SD SPI1 MISO',
              'PA7': 'private physical SD SPI1 MOSI'}


class M300Resources:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.board = self.printer.load_object(config, 'm300_mcu')
        self.io = self.printer.load_object(config, 'm300_io')
        self.report = {'validated': False}
        self.board.get_mcu().register_config_callback(self._audit)
        # The M06 profile keeps one homing owner even if its optional section
        # is omitted: load defaults with all execution gates disabled.
        self.require_motion_owner = config.getboolean('require_motion_owner', False)
        if self.require_motion_owner:
            self.printer.load_object(config, 'm300_motion')
        # A release profile can pin the calibration policy independently of
        # optional section presence. This is an interface requirement, not an
        # execution/qualification gate. The adapter derives its default from
        # this requirement and still starts with qualified=False.
        self.require_calibration_workflow = config.get('require_calibration_workflow', None)
        if self.require_calibration_workflow not in (None, 'M07_STOCK'):
            raise config.error('M300 require_calibration_workflow must be M07_STOCK or omitted')
        if self.require_calibration_workflow is not None:
            self.printer.load_object(config, 'm300_calibration')
        self.require_cycle_owner = config.getboolean('require_cycle_owner', False)
        self.printer.lookup_object('gcode').register_command(
            'ZORTRAX_CONFIG_STATUS', self.cmd_status, when_not_ready=True)

    def _audit(self):
        if self.require_cycle_owner:
            cycle = self.printer.lookup_object('m300_cycle', None)
            if cycle is None:
                raise self.config.error('M300 required M08 cycle owner is unavailable')
            from .m300_cycle_state import STATES
            if len(STATES) != 22 or len(set(STATES)) != 22:
                raise self.config.error('M300 M08 cycle contract must expose exactly 22 unique states')
        if self.require_calibration_workflow is not None:
            calibration = self.printer.lookup_object('m300_calibration', None)
            if (calibration is None or getattr(calibration, 'workflow', None)
                    != self.require_calibration_workflow):
                raise self.config.error('M300 required calibration workflow is unavailable or inconsistent')
        ppins = self.printer.lookup_object('pins')
        prefix = self.board.mcu_name + ':'
        resolver = ppins.get_pin_resolver(self.board.mcu_name)
        canonical = lambda pin: resolver.aliases.get(pin, pin)
        if ppins.allow_multi_use_pins:
            raise self.config.error('M300 duplicate_pin_override is forbidden; each peripheral has one owner')
        active = {}
        for key, params in ppins.active_pins.items():
            if not key.startswith(prefix):
                continue
            pin = canonical(key[len(prefix):])
            if pin in active:
                raise self.config.error('M300 aliased pin %s used multiple times' % pin)
            active[pin] = params
        for pin, reason in dict(MCU_ONLY, **EXCLUDED).items():
            if pin in active:
                raise self.config.error('M300 pin %s is owned/excluded: %s' % (pin, reason))
        if self.config.getsection('printer').get('kinematics') != 'cartesian':
            raise self.config.error('M300 P01 requires Cartesian kinematics')
        native = getattr(self.board, 'native_control', False)
        if not native and (set(self.io.outputs) != set(OUTPUTS) or any(
                not output.configured for output in self.io.outputs.values())):
            raise self.config.error('M300 full profile requires 2 guarded heaters + 2 configured fan outputs')
        if native and self.io.outputs:
            raise self.config.error('M300 native control requires physical PWM pins, not virtual LAB outputs')
        heaters = self.printer.lookup_object('heaters')
        if set(heaters.heaters) != REQUIRED_HEATERS:
            raise self.config.error('M300 full profile requires exactly extruder and heater_bed')
        for name, virtual_name in (('extruder', 'HEATER_HOTEND'),
                                   ('heater_bed', 'HEATER_BED')):
            pwm = heaters.lookup_heater(name).mcu_pwm
            if native:
                if canonical(pwm._pin) != OUTPUTS[virtual_name][0]:
                    raise self.config.error('M300 native heater wiring mismatch: ' + name)
            elif pwm is not self.io.outputs[virtual_name]:
                raise self.config.error('M300 direct heater pin bypass is forbidden: ' + name)
        query_adc = self.printer.lookup_object('query_adc')
        if set(query_adc.adc) != REQUIRED_HEATERS or set(self.board.adcs) != REQUIRED_HEATERS:
            raise self.config.error('M300 requires exactly two native heater ADC owners; diagnostics only observe')
        for name, pin in ADC_PINS.items():
            adc = self.board.adcs[name]
            if (query_adc.adc[name] is not adc or canonical(adc._pin) != pin
                    or heaters.lookup_heater(name).sensor.mcu_adc is not adc):
                raise self.config.error('M300 ADC ownership/wiring mismatch: ' + name)
        steppers = self.printer.lookup_object('stepper_enable')
        physical = set(steppers.get_steppers())
        if physical != REQUIRED_STEPPERS:
            raise self.config.error('M300 requires exactly X/Y/Z plus ONE physical E driver')
        common = [steppers.lookup_enable(name).enable for name in sorted(physical)]
        if any(obj is not common[0] for obj in common):
            raise self.config.error('M300 all four drivers must share one active-HIGH PD14 enable object')
        if 'PD14' not in active or active['PD14']['invert']:
            raise self.config.error('M300 PD14 enable must be active HIGH')
        for section, assignments in WIRING.items():
            cfg = self.config.getsection(section)
            for option, expected in assignments.items():
                params = ppins.parse_pin(cfg.get(option), can_invert=True, can_pullup=True)
                if params['chip'] is not self.board.mcu or canonical(params['pin']) != expected:
                    raise self.config.error('M300 wiring mismatch: %s %s must use %s' %
                                            (section, option, expected))
                if option == 'step_pin' and params['invert']:
                    raise self.config.error('M300 STEP must use a positive pulse')
                if option == 'endstop_pin' or section == 'probe':
                    if not params['invert'] or params['pullup'] != 1:
                        raise self.config.error('M300 endstop/probe requires pullup and active LOW: ' + section)
                if section.startswith('output_pin '):
                    if params['invert'] or cfg.getboolean('pwm', False):
                        raise self.config.error('M300 RGB/buzzer P01 uses active-HIGH digital outputs')
                    if cfg.getfloat('value', 0.) != 0. or cfg.getfloat('shutdown_value', 0.) != 0.:
                        raise self.config.error('M300 RGB/buzzer must start and shut down LOW')
        z_endstop = ppins.parse_pin(self.config.getsection('stepper_z').get('endstop_pin'), True, True)
        if z_endstop['chip_name'] != 'probe' or z_endstop['pin'] != 'z_virtual_endstop':
            raise self.config.error('M300 Z must use probe:z_virtual_endstop (one PC7 owner)')
        for name, steps in (('stepper_x', 128), ('stepper_y', 128), ('stepper_z', 16)):
            if self.config.getsection(name).getint('microsteps') != steps:
                raise self.config.error('M300 %s microsteps must match MCU static MS mode %d' % (name, steps))
        for name, virtual_name in (('fan', 'FAN_PRINT'), ('heater_fan hotend', 'FAN_HOTEND')):
            obj = self.printer.lookup_object(name, None)
            if native:
                if obj is None or canonical(obj.fan.mcu_fan._pin) != OUTPUTS[virtual_name][0]:
                    raise self.config.error('M300 native fan wiring mismatch: ' + name)
            elif obj is None or obj.fan.mcu_fan is not self.io.outputs[virtual_name]:
                raise self.config.error('M300 requires native fan and heater_fan hotend objects on guarded outputs')
        if self.printer.lookup_object('m300_oled', None) is None:
            raise self.config.error('M300 full profile requires m300_oled (single OLED/encoder owner)')
        expected = set(ADC_PINS.values()) | {item[0] for item in OUTPUTS.values()}
        expected |= {pin for assignments in WIRING.values() for pin in assignments.values()}
        if set(active) != expected:
            raise self.config.error('M300 unexpected/missing host GPIO owners: ' +
                                    ','.join(sorted(set(active) ^ expected)))
        self.report = {
            'validated': True, 'abi': ABI, 'model': MODEL, 'clock_freq': CLOCK_FREQ,
            'mode': ('FILEOUTPUT_NO_MCU_EXECUTION' if self.board.mcu.is_fileoutput()
                     else 'LIVE_HOST_CONFIGURATION'),
            'kinematics': 'cartesian', 'adc_physical_count': 2,
            'adc_owner': 'native_heater_sensors', 'adc_diagnostics': 'same_objects_read_only',
            'adc_pins': ADC_PINS, 'heater_count': 2, 'fan_count': 2,
            'software_pwm_count': 4, 'hardware_pwm_count': 0,
            'physical_steppers': sorted(physical),
            'enable': 'PD14 active-HIGH, ONE shared native object',
            'z_endstop': 'probe:z_virtual_endstop -> one active-LOW PC7 object',
            'host_physical_pin_count': len(active), 'host_physical_pins': sorted(active),
            'mcu_owned_pins': dict(MCU_ONLY, **PRIVATE_SD),
            'excluded_pins': {k: v for k, v in EXCLUDED.items() if k not in PRIVATE_SD},
            'sd_owner': 'M04 private read-only SPI1 driver; generic SPI remains unavailable',
            'microstep_owner': 'MCU C initialization: XY HHH, Z LLH; E unverified nominal',
            'timers': 'native Klipper scheduler, native software PWM; no inherited stock timer allocation',
            'hardware_qualified': False,
            'thermal_profile': 'nominal stock linear hotend and interpolated stock bed table; unmeasured',
            'full_print_cycle_implemented': True,
            'full_print_cycle_owner': 'M08 22-state supervisor over M02/M03/M06/M07',
        }

    def get_status(self, eventtime):
        report = dict(self.report)
        report['required_motion_owner'] = self.require_motion_owner
        report['required_calibration_workflow'] = self.require_calibration_workflow
        report['required_cycle_owner'] = self.require_cycle_owner
        cycle = self.printer.lookup_object('m300_cycle', None)
        report['cycle_installed'] = bool(cycle is not None and getattr(cycle, 'installed', False))
        report['cycle_state_count'] = 22 if cycle is not None else 0
        calibration = self.printer.lookup_object('m300_calibration', None)
        report['calibration_workflow'] = getattr(calibration, 'workflow', None)
        report['allow_actuators'] = self.board.allow_actuators
        report['allow_motion'] = self.board.allow_motion
        report['allow_heating'] = self.board.allow_heating
        report['forced_cooling'] = self.board.get_status(eventtime)['forced_cooling']
        report['guards_installed'] = self.io.guards_installed
        return report

    def cmd_status(self, gcmd):
        report = self.get_status(self.printer.get_reactor().monotonic())
        report['klippy_state'] = self.printer.get_state_message()[1]
        report['gcode_ready'] = self.printer.lookup_object('gcode').is_printer_ready
        gcmd.respond_info('M300_CONFIG ' + json.dumps(report, sort_keys=True))


def load_config(config):
    return M300Resources(config)
