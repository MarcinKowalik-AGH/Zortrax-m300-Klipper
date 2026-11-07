# SPDX-License-Identifier: GPL-3.0-or-later
"""Normal M300 homing on Klipper's native Cartesian/probe implementation.

M300 Z preheat, contact location, five reference updates and clearance are adapted.
G0/G1, motion limits, step generation and endstop stopping remain native.
"""
import json
import logging
import math


class M300NativeMotion:
    HOMING_UI_ABI = 2
    normal_control = True

    def __init__(self, config):
        self.config, self.printer = config, config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.board = self.printer.load_object(config, 'm300_mcu')
        self.home_xy = config.getfloatlist('home_xy', (150., 158.), count=2)
        self.travel_speed = config.getfloat('home_travel_speed', 50., above=0.)
        self.z_home_hotend_target = config.getfloat('z_home_hotend_target', 180., above=0.)
        self.z_home_heat_timeout = config.getfloat(
            'z_home_heat_timeout', 600., minval=60., maxval=1800.)
        self.z_home_temperature_tolerance = config.getfloat(
            'z_home_temperature_tolerance', 5., minval=.5, maxval=5.)
        self.clearance = config.getfloat('z_contact_clearance', 5., above=0.)
        self.lift_speed = config.getfloat('z_lift_speed', 5., above=0.)
        if not all(math.isfinite(v) for v in (*self.home_xy, self.travel_speed,
                                              self.z_home_hotend_target, self.z_home_heat_timeout,
                                              self.z_home_temperature_tolerance, self.clearance,
                                              self.lift_speed)):
            raise config.error('M300 native homing settings must be finite')
        self.token = self.phase_id = 0
        self.state = self.phase = 'IDLE'
        self.operator_homing = None
        self.reason, self.result = '', None
        self.failure_phase = None
        self.native_z_checks = []
        self.ready = False
        self.precision = self.homing_speeds = None
        self._z_target = None
        self._xy_clearance_position = None
        self.toolhead = self.hotend = self.heaters = self.native_G28 = None
        self.printer.load_object(config, 'homing')
        self.printer.register_event_handler('klippy:connect', self._connect)
        self.printer.register_event_handler('klippy:ready', self._ready)
        self.printer.register_event_handler('homing:homing_move_begin', self._native_probe_begin)
        for name in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(name, lambda *args, event=name: self._stop(event))
        self.gcode.register_command('ZORTRAX_MOTION_STATUS', self.cmd_status,
                                     when_not_ready=True)
        self.gcode.register_command('ZORTRAX_HOME', self.cmd_home)
        self.gcode.register_command('ZORTRAX_MOTION_CANCEL', self.cmd_cancel)
        self.gcode.register_command('ZORTRAX_IDLE_RELEASE_XYE', self.cmd_idle_release)

    def _connect(self):
        if not self.board.native_control:
            raise self.config.error('M300 normal motion requires native board initialization')
        self.toolhead = self.printer.lookup_object('toolhead')
        self.heaters = self.printer.lookup_object('heaters')
        self.hotend = self.heaters.lookup_heater('extruder')
        if not self.hotend.min_temp < self.z_home_hotend_target < self.hotend.max_temp:
            raise self.config.error('M300 Z homing temperature outside native heater limits')
        kin = self.toolhead.get_kinematics()
        if not hasattr(kin, 'rails') or len(kin.rails) != 3:
            raise self.config.error('M300 normal motion requires native Cartesian XYZ')
        for i, coordinate in enumerate(self.home_xy):
            lo, hi = kin.rails[i].get_range()
            if not lo <= coordinate <= hi:
                raise self.config.error('M300 Z contact XY outside native axis bounds')
        lo, hi = kin.rails[2].get_range()
        probe = self.printer.lookup_object('probe')
        if not lo <= probe.get_offsets()[2] + self.clearance <= hi:
            raise self.config.error('M300 final Z clearance outside native range')
        original = self.gcode.register_command('G28', None)
        # An explicit conflicting homing_override/safe_z_home must not be
        # silently stacked under this M300 contact-location adapter.
        if (getattr(original, '__module__', None) != 'extras.homing'
                or getattr(original, '__name__', None) != 'cmd_G28'):
            if original is not None:
                self.gcode.register_command('G28', original)
            raise self.config.error('M300 normal homing requires the native G28 owner')
        self.native_G28 = original
        self.gcode.register_command('G28', self.cmd_G28)
        from .m300_native_z import M300ZRefinement
        self.precision = M300ZRefinement(self, probe)
        self.homing_speeds = self._homing_speeds(kin)
        enables = self.printer.lookup_object('stepper_enable',None)
        if enables is not None:
            enables.lookup_enable('stepper_z').register_state_callback(self._z_enable_changed)

    def _ready(self):
        self.ready = True
        self.operator_homing = None

    def _stop(self, event='host lifecycle'):
        self.token += 1
        self._xy_clearance_position = None
        self.ready = False
        if self.is_busy():
            self.failure_phase = self.phase
            self.state, self.phase = 'CANCELLED', 'INVALIDATED'
            self.reason = '%s during %s' % (event, self.failure_phase)

    def _z_enable_changed(self, print_time, enabled):
        if not enabled:
            self._xy_clearance_position = None
            if self.toolhead is not None:
                self.toolhead.get_kinematics().clear_homing_state('z')

    def _phase(self, name):
        self.phase, self.phase_id = name, self.phase_id + 1
        if self.operator_homing is not None:
            self.printer.send_event('m300:homing_view_changed')

    def _check(self, token):
        if token != self.token or not self.ready or self.printer.is_shutdown():
            raise self.printer.command_error(
                'M300 homing session ended: ' + (self.reason or 'host or MCU is unavailable'))

    def _preheat(self, token, target, oem_leveling):
        self.heaters.set_temperature(self.hotend, target, wait=False)
        self._check(token)
        if self.board.mcu.is_fileoutput():
            return
        now = self.reactor.monotonic()
        deadline = now + self.z_home_heat_timeout
        while True:
            self._check(token)
            measured, requested = self.hotend.get_temp(now)
            if requested != target:
                raise self.printer.command_error('M300 homing nozzle target changed during preheat')
            if oem_leveling:
                ready = not self.hotend.check_busy(now)
            else:
                ready = math.isfinite(measured) and measured >= self.z_home_hotend_target
            if ready:
                return
            if now >= deadline:
                raise self.printer.command_error(
                    'M300 homing preheat timed out after %.0f s (%.1f / %.1f C)'
                    % (self.z_home_heat_timeout, measured, target))
            now = self.reactor.pause(min(now + 1., deadline))

    def _native_home(self, axes):
        params = {axis.upper(): '0' for axis in axes}
        cmd = self.gcode.create_gcode_command('G28', 'G28 ' + ' '.join(params), params)
        return self.native_G28(cmd)

    def ensure_xy_clearance(self, check):
        """Bounded Z-only retreat; a temporary frame never establishes homed Z."""
        if self.board.mcu.is_fileoutput():
            return dict(physical_contact_checked=False)
        self.toolhead.wait_moves()
        check()
        endstop = self.precision.endstop
        active = endstop.query_endstop(self.toolhead.get_last_move_time())
        check()
        kin = self.toolhead.get_kinematics()
        rail = kin.rails[2]
        if rail.get_homing_info().positive_dir:
            raise self.printer.command_error('M300 homing CLEARANCE: expected Z homing toward the minimum')
        unhomed = 'z' not in kin.get_status(self.reactor.monotonic())['homed_axes']
        position = self.toolhead.get_position()
        signature = (tuple(position),not unhomed)
        if not active and getattr(self,'_xy_clearance_position',None) == signature:
            # Reuse only the unchanged, electrically open position just
            # prepared by a parent wizard; never accumulate another 5 mm.
            return dict(commanded_distance_mm=0.,clearance_reused=True,
                        physical_contact_checked=True,pc7_open=True)
        self._xy_clearance_position = None
        lower,upper = rail.get_range()
        clearance = max(5.,self.clearance)
        start = max(lower,position[2]) if unhomed else position[2]
        target = (start+clearance if unhomed or active else
                  max(start,self.precision.probe.get_offsets()[2]+clearance))
        if not math.isfinite(target) or not lower <= target <= upper:
            raise self.printer.command_error(
                'M300 homing CLEARANCE: no room for %.1f mm Z clearance within native bounds; XY was not started'
                % clearance)
        if target > start:
            self.board.require_motion()
            try:
                if unhomed:
                    position[2]=start
                    self.toolhead.set_position(position,homing_axes='z')
                    check()
                self.toolhead.manual_move([None,None,target],self.lift_speed)
            finally:
                if unhomed:
                    kin.clear_homing_state('z')
            self.toolhead.wait_moves()
            check()
        active = endstop.query_endstop(self.toolhead.get_last_move_time())
        check()
        if active:
            raise self.printer.command_error(
                'M300 homing NO_RELEASE: PC7 is still closed after the initial Z clearance; XY was not started')
        self._xy_clearance_position = (tuple(self.toolhead.get_position()),not unhomed)
        return dict(commanded_distance_mm=target-start,temporary_z_frame=unhomed,
                    physical_contact_checked=True,pc7_open=True)

    def _check_z_contact(self, token):
        if self.board.mcu.is_fileoutput():return
        self.toolhead.wait_moves()
        self._check(token)
        active = self.precision.endstop.query_endstop(self.toolhead.get_last_move_time())
        self._check(token)
        if active:
            raise self.printer.command_error(
                'M300 homing NO_RELEASE: PC7 closed again after the initial Z clearance; motion stopped')

    def _native_probe_begin(self, hmove):
        # The pinned native probe home has two passes. Its ordinary retract
        # does not verify electrical release before starting the second pass.
        # Keep the native HomingMove and its no-movement check intact; check
        # PC7 before it captures the start position or arms the endstop.
        if (not self.is_busy() or self.phase != 'HOME_Z_NATIVE_PROBE'
                or self.board.mcu.is_fileoutput()):
            return
        endstop = self.precision.endstop
        endstops = hmove.get_mcu_endstops()
        if endstop not in endstops:
            return  # XY and unrelated probes grant no Z recovery authority.
        steppers = endstop.get_steppers()
        if endstops != [endstop] or len(steppers) != 1 or steppers[0].get_name() != 'stepper_z':
            raise self.printer.command_error('M300 homing: PC7 must own exactly one native Z stepper')
        token = self.token
        self.toolhead.wait_moves()
        self._check(token)
        active = bool(endstop.query_endstop(self.toolhead.get_last_move_time()))
        self._check(token)
        check = dict(pass_number=len(self.native_z_checks)+1,
                     pc7_active_before=active, retreat_mm=0., pc7_open=not active)
        self.native_z_checks.append(check)
        logging.info('M300_Z_PROBE_CHECK %s', json.dumps(check, sort_keys=True))
        if not active:
            return
        if check['pass_number'] != 2:
            # Native first home temporarily assigns forcepos beyond Z max.
            # Only the second pass has the bounded post-contact retract frame.
            raise self.printer.command_error(
                'M300 homing NO_RELEASE: PC7 closed before native Z pass %d; approach was not started'
                % check['pass_number'])
        lower, upper = self.toolhead.get_kinematics().rails[2].get_range()
        start = self.toolhead.get_position()[2]
        distance = max(5., self.clearance)
        target = start + distance
        if (not math.isfinite(start) or not math.isfinite(target)
                or not lower <= start < target <= upper):
            raise self.printer.command_error(
                'M300 homing CLEARANCE: no room for native Z pass 2 release; approach was not started')
        self.board.require_motion()
        self._check(token)
        self.toolhead.manual_move([None, None, target], self.lift_speed)
        self.toolhead.wait_moves()
        self._check(token)
        check['retreat_mm'] = distance
        check['pc7_open'] = not endstop.query_endstop(self.toolhead.get_last_move_time())
        self._check(token)
        logging.info('M300_Z_PROBE_RELEASE %s', json.dumps(check, sort_keys=True))
        if not check['pc7_open']:
            raise self.printer.command_error(
                'M300 homing NO_RELEASE: PC7 still closed before native Z pass 2 after %.1f mm retreat; approach was not started'
                % distance)

    def cmd_idle_release(self, gcmd):
        # This is the default idle script's motor stage. Preserve a held Z
        # without commanding it to enable or changing its reference.
        now = self.reactor.monotonic()
        stats = self.printer.lookup_object('print_stats', None)
        if self.is_busy() or stats and stats.get_status(now)['state'] in ('printing', 'paused'):
            return
        queued, current, empty = self.toolhead.check_busy(now)
        if not empty or queued > current:
            return
        motors = self.printer.lookup_object('stepper_enable')
        names = [name for name in motors.get_steppers() if name != 'stepper_z']
        motors.set_motors_enable(names, False)
        self.toolhead.get_kinematics().clear_homing_state('xy')

    def _homing_speeds(self, kin):
        axes = {}
        for axis, rail in zip('xyz', kin.rails):
            info = rail.get_homing_info()
            axes[axis] = {'seek': info.speed,
                          'retract': info.retract_speed if info.retract_dist else None,
                          'second_seek': info.second_homing_speed if info.retract_dist else None}
        return {'native_rails': axes, 'z_axis_limit': kin.max_z_velocity,
                'xy_to_contact': self.travel_speed, 'z_precision': self.precision.speed,
                'z_final_clearance': self.lift_speed}

    def cmd_G28(self, gcmd):
        params = dict(gcmd.get_command_parameters())
        params.pop('G', None)
        if any(key not in ('X', 'Y', 'Z') for key in params):
            raise gcmd.error('G28 accepts X/Y/Z axis selectors')
        self.home(axes=''.join(params).lower() or 'xyz')

    def home_oem(self, contact_xy):
        return self.home(axes='xyz',oem_leveling=True,contact_xy=contact_xy)

    def home(self, owner_job=None, job_token=None, axes='xyz',oem_leveling=False,contact_xy=None):
        control=self.printer.lookup_object('m300_print_control',None)
        if control is not None and control.context is not None:
            raise self.printer.command_error('Cancel the protected print before homing')
        axes = axes.lower()
        if not axes or any(a not in 'xyz' for a in axes) or len(set(axes)) != len(axes):
            raise self.printer.command_error('M300 homing axes must be X/Y/Z')
        if self.is_busy():
            raise self.printer.command_error('M300 homing already active')
        if owner_job is not None:
            if (owner_job is not self.printer.lookup_object('m300_job', None)
                    or owner_job.machine.token != job_token
                    or owner_job.machine.state != 'HOMING'):
                raise self.printer.command_error('M300 stale OEM job homing request')
        elif job_token is not None:
            raise self.printer.command_error('M300 job token without an owner')
        self._check(self.token)
        kin = self.toolhead.get_kinematics()
        homed = kin.get_status(self.reactor.monotonic())['homed_axes']
        if 'z' in axes and any(a not in axes and a not in homed for a in 'xy'):
            raise self.printer.command_error('Home XY first, or use G28 for XYZ')
        self.operator_homing = None
        if owner_job is None and not oem_leveling:
            operation = {'x': 'HOME_X', 'y': 'HOME_Y', 'xy': 'HOME_XY',
                         'z': 'HOME_Z', 'xyz': 'HOME_ALL'}.get(''.join(sorted(axes)))
            if operation is not None:
                stats = self.printer.lookup_object('print_stats', None)
                sd = self.printer.lookup_object('virtual_sdcard', None)
                if (getattr(sd, 'work_timer', None) is None
                        and (stats is None or stats.get_status(self.reactor.monotonic()).get('state')
                             not in ('printing', 'paused'))):
                    self.operator_homing = operation
        self.token += 1
        token = self.token
        self.state, self.reason, self.result = 'HOMING', '', None
        self.failure_phase = None
        self.native_z_checks = []
        previous_target, owned_target = None, None
        reference = None
        try:
            self._phase('Z_INITIAL_CLEARANCE')
            initial_clearance = self.ensure_xy_clearance(lambda:self._check(token))
            if 'z' in axes:
                self._phase('Z_PREHEAT')
                _, previous_target = self.hotend.get_temp(self.reactor.monotonic())
                target = max(previous_target, self.z_home_hotend_target)
                self._z_target = target
                if target != previous_target:
                    owned_target = target
                self._preheat(token, target, oem_leveling)
                self._phase('Z_CHECK_CONTACT')
                self._check_z_contact(token)
            # Both OEM G28/Z-code and M07 home Y before X.
            for axis in 'yx':
                if axis in axes:
                    self._phase('HOME_' + axis.upper())
                    self._native_home(axis)
                    self._check(token)
            if 'z' in axes:
                self._phase('Z_CONTACT_POSITION')
                point = self.home_xy if contact_xy is None else tuple(contact_xy)
                if len(point)!=2 or any(not math.isfinite(v) for v in point):
                    raise self.printer.command_error('M300 invalid contact XY')
                self.toolhead.manual_move([*point, None], self.travel_speed)
                self.toolhead.wait_moves()
                self._check(token)
                self._phase('HOME_Z_NATIVE_PROBE')
                self._check_z_contact(token)
                if not oem_leveling and not self.board.mcu.is_fileoutput():
                    self.precision.check_temperature()
                self._native_home('z')
                self._check(token)
                # M07's 0x0801456c is its own initial coarse contact. Ordinary
                # homing instead follows the five-update 0x0800ab90 policy.
                if not oem_leveling:
                    mcu = getattr(self.board,'mcu',None)
                    if mcu is not None and mcu.is_fileoutput():
                        reference = dict(method='FILEOUTPUT_NO_PHYSICAL_CONTACT',contacts=0)
                    else:
                        self._phase('Z_FIVE_CONTACT_REFERENCES')
                        try:
                            reference = self.precision.run(token)
                        except Exception:
                            if not self.printer.is_shutdown():
                                self.printer.invoke_shutdown('M300 precision Z reference failed')
                            raise
                # Native homing has just established contact Z. Never add a
                # blind 5 mm retreat to an old Z299 coordinate before homing.
                self._phase('Z_FINAL_CLEARANCE')
                # Refinement can leave a stable opening above its reference.
                # Clearance is measured from contact, never accumulated.
                target = (self.precision.probe.get_offsets()[2]+self.clearance
                          if reference and reference.get('contacts')==5 else
                          self.toolhead.get_position()[2]+self.clearance)
                self.toolhead.manual_move([None, None, target], self.lift_speed)
                self.toolhead.wait_moves()
                self._check(token)
            self.state = 'COMPLETE'
            self._phase('COMPLETE')
            self.result = {'axes': axes, 'position': list(self.toolhead.get_position()),
                           'native_endstop_stopping': True,'z_reference':reference,
                           'oem_leveling':oem_leveling,'initial_clearance':initial_clearance}
        except Exception as exc:
            self.reason = str(exc)
            from .m300_error_codes import report
            report(self.printer, exc, source='m300_motion', fatal=self.printer.is_shutdown())
            if self.state != 'CANCELLED':
                self.failure_phase = self.phase
                self.state = 'FAULT'
                self._phase('FAULT')
            raise
        finally:
            self._z_target = None
            if owned_target is not None and not self.printer.is_shutdown():
                _, current_target = self.hotend.get_temp(self.reactor.monotonic())
                if current_target == owned_target:
                    restored = previous_target if self.state == 'COMPLETE' else 0.
                    self.heaters.set_temperature(self.hotend, restored, wait=False)
        return self.get_status(self.reactor.monotonic())

    def cancel(self, reason='operator cancel', **kwargs):
        if self.is_busy():
            self.token += 1
            self.state, self.phase, self.reason = 'CANCELLED', 'CANCELLED', reason
            # Native homing is not resumable after an asynchronous stop.
            self.printer.invoke_shutdown('M300 homing cancelled')

    def panel_update(self, snapshot, received_at, token=None, view_current=False):
        # The OLED also delivers raw counters to the older leased M06 jog
        # owner. Native jogs are ordinary G-code; receiving telemetry grants
        # no movement or homing authority here.
        return None

    def is_busy(self):
        return self.state == 'HOMING'

    def get_status(self, eventtime):
        kin_status = (self.toolhead.get_kinematics().get_status(eventtime)
                      if self.toolhead is not None else {})
        hardware = self.board.hardware.get_status()
        return {'version': '0.13.16.23-NATIVE-Z-RELEASE', 'model': 'M300_CLASSIC',
                'normal_control': True, 'installed': True, 'ready': self.ready,
                'state': self.state, 'busy': self.is_busy(), 'phase': self.phase,
                'operation': self.operator_homing,
                'phase_id': self.phase_id, 'session_token': self.token,
                'homed_axes': kin_status.get('homed_axes', ''),
                'position_valid': kin_status.get('homed_axes') == 'xyz',
                'native_position': (list(self.toolhead.get_position())
                                    if self.toolhead is not None else None),
                'reason': self.reason, 'result': self.result,
                'failure_phase': self.failure_phase,
                'native_z_checks': [dict(check) for check in self.native_z_checks],
                'z_home_hotend_target_c': self.z_home_hotend_target,
                'z_home_heat_timeout_s': self.z_home_heat_timeout,
                'z_home_temperature_tolerance_c': self.z_home_temperature_tolerance,
                'homing_speed_mm_s': self.homing_speeds,
                'z_contact_clearance_mm': self.clearance,
                'z_initial_clearance_mm': max(5.,self.clearance),
                'z_steps_per_mm': hardware['effective_z_steps_per_mm'],
                'hardware_revision': hardware['hardware_revision'],
                'native_G28': 'extras.homing.PrinterHoming.cmd_G28',
                'physical_hardware_tests_by_CI': False}

    def cmd_home(self, gcmd):
        self.home(axes=gcmd.get('AXES', 'XYZ'))

    def cmd_cancel(self, gcmd):
        self.cancel()

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_MOTION ' + json.dumps(
            self.get_status(self.reactor.monotonic()), sort_keys=True))
