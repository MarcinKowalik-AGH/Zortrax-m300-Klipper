# SPDX-License-Identifier: GPL-3.0-or-later
"""Native software PWM with M300 qualification gates; no duplicate ADC owner."""
import json
import math

OUTPUTS = {
    'HEATER_HOTEND': ('PC8', 'heater'),
    'HEATER_BED': ('PC9', 'heater'),
    'FAN_PRINT': ('PE13', 'fan'),
    'FAN_HOTEND': ('PE14', 'fan'),
}


class M300PWM:
    def __init__(self, owner, name):
        self.owner = owner
        self.board = owner.board
        self.name = name
        self.pin, self.role = OUTPUTS[name]
        # One underlying native PWM owner per physical GPIO. The native PWM
        # implementation owns scheduling, shutdown, and MCU command encoding.
        ppins = owner.printer.lookup_object('pins')
        self.native = ppins.setup_pin('pwm', self.board.mcu_name + ':' + self.pin)
        self.configured = False
        self.cycle_time = None
        self.start_value = 0.
        self.shutdown_value = 1. if self.role == 'fan' else 0.
        self.last_requested = 0.
        self.native.setup_start_value(self.start_value, self.shutdown_value)

    def get_mcu(self):
        return self.native.get_mcu()

    def setup_max_duration(self, max_duration):
        self.native.setup_max_duration(max_duration)

    def setup_cycle_time(self, cycle_time, hardware_pwm=False):
        if hardware_pwm:
            raise self.owner.config.error('M300 %s requires native software PWM (hardware_pwm=False)' % self.name)
        if not math.isfinite(cycle_time) or not .001 <= cycle_time <= .300:
            raise self.owner.config.error('M300 PWM cycle_time must be finite and between 0.001 and 0.300 seconds')
        self.cycle_time = cycle_time
        self.native.setup_cycle_time(cycle_time, hardware_pwm=False)
        self.configured = True

    def setup_start_value(self, start_value, shutdown_value):
        required_shutdown = 1. if self.role == 'fan' else 0.
        if start_value != 0. or shutdown_value != required_shutdown:
            raise self.owner.config.error(
                'M300 %s requires start=0 shutdown=%d (protective fan cooling)' %
                (self.name, required_shutdown))
        self.start_value, self.shutdown_value = start_value, shutdown_value
        self.native.setup_start_value(start_value, shutdown_value)

    def next_aligned_print_time(self, print_time, allow_early=0.):
        return self.native.next_aligned_print_time(print_time, allow_early)

    def set_pwm(self, print_time, value):
        if not math.isfinite(value) or not 0. <= value <= 1.:
            raise self.owner.printer.command_error('M300 PWM value must be finite and within 0..1')
        if self.role == 'heater' and value > 0.:
            self.board.require_heating()
        self.last_requested = value
        # Fans remain controllable in the native queue. The MCU independently
        # applies its selected fan policy independently of ARM. R14 can use
        # its local ADC2 thermostat while offline; invalid local samples force
        # both outputs HIGH. Healthy host operation retains native PWM.
        self.native.set_pwm(print_time, value)


class M300IO:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.board = self.printer.load_object(config, 'm300_mcu')
        self.outputs = {}
        self.guards_installed = False
        self.printer.lookup_object('pins').register_chip('m300', self)
        self.printer.register_event_handler('klippy:connect', self._handle_connect)
        self.printer.lookup_object('gcode').register_command(
            'ZORTRAX_IO_STATUS', self.cmd_status, when_not_ready=True)

    def setup_pin(self, pin_type, pin_params):
        name = pin_params['pin']
        if name not in OUTPUTS or pin_type != 'pwm':
            raise self.config.error('M300 virtual pins support only the four named PWM outputs')
        if pin_params.get('invert') or pin_params.get('pullup'):
            raise self.config.error('M300 virtual PWM outputs must be active HIGH without inversion/pullup')
        if name in self.outputs:
            raise self.config.error('M300 virtual PWM output %s used multiple times' % name)
        result = self.outputs[name] = M300PWM(self, name)
        return result

    def _handle_connect(self):
        if getattr(self.board, 'native_control', False):
            return
        if self.guards_installed:
            return
        toolhead = self.printer.lookup_object('toolhead')
        original_move = toolhead.move

        def guarded_move(newpos, speed):
            if list(newpos) != list(toolhead.get_position()):
                self.board.require_motion()
            return original_move(newpos, speed)

        toolhead.move = guarded_move
        kin = toolhead.get_kinematics()
        original_home = kin.home

        def guarded_home(homing_state):
            self.board.require_motion()
            return original_home(homing_state)

        kin.home = guarded_home
        steppers = self.printer.lookup_object('stepper_enable')
        original_enable = steppers.set_motors_enable

        def guarded_enable(names, enable):
            if enable:
                self.board.require_motion()
            return original_enable(names, enable)

        steppers.set_motors_enable = guarded_enable

        def enable_callback(print_time, enabled):
            if enabled:
                self.board.require_motion()

        # Also cover direct force_move/STEPPER_BUZZ and step generation auto
        # enable, which do not pass through toolhead.move or SET_STEPPER_ENABLE.
        for name in steppers.get_steppers():
            steppers.lookup_enable(name).register_state_callback(enable_callback)
        for heater in self.printer.lookup_object('heaters').heaters.values():
            for method in ('set_temp', 'alter_target'):
                original = getattr(heater, method)

                def guarded_target(target, original=original):
                    if not math.isfinite(target):
                        raise self.printer.command_error('M300 heater target must be finite')
                    if target > 0.:
                        self.board.require_heating()
                    return original(target)

                setattr(heater, method, guarded_target)
        self.guards_installed = True

    def get_status(self, eventtime):
        board = self.board.get_status(eventtime)
        return {'guards_installed': self.guards_installed,
                'allow_actuators': self.board.allow_actuators,
                'allow_motion': self.board.allow_motion,
                'allow_heating': self.board.allow_heating,
                'armed': board['armed'], 'forced_cooling': board['forced_cooling'],
                'adc_owner': 'two_native_heater_sensor_objects_observed_without_reallocation',
                'outputs': {name: {'physical_pin': output.pin, 'role': output.role,
                                   'software_pwm': True,
                                   'cycle_time': output.cycle_time,
                                   'start_value': output.start_value,
                                   'shutdown_value': output.shutdown_value,
                                   'requested': output.last_requested}
                            for name, output in self.outputs.items()}}

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_IO ' + json.dumps(
            self.get_status(self.printer.get_reactor().monotonic()), sort_keys=True))


def load_config(config):
    return M300IO(config)
