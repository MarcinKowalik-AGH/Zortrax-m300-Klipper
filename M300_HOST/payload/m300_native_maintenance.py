# SPDX-License-Identifier: GPL-3.0-or-later
"""OEM Maintenance on the existing native Klipper heaters and Z rail.

The MCU stops the native Z move on a local button release. The host reconciles
the halted position using Klipper's native probe-move position accounting.
"""
from .m300_temperature_policy import target_limit
import math

from .m300_maintenance import M300Maintenance, other_service
from .m300_native_probe import BoundedProbeToolhead, boundary_z
from .m300_native_service import NativeServiceLease, native_service_frame, require_idle_print

PERIOD = .05
PANEL_LEASE = .75
PLATFORM_STEP_MM = 1.
PLATFORM_STEP_SECONDS = 1.
PLATFORM_SPEED = 10.
PLATFORM_HOLD_STEPS_PER_SECOND = 8000.


class PanelRelease:
    """One same-MCU stop signal, tied to the panel's physical press counter."""
    def __init__(self, mcu):
        from mcu import MCU_trsync, TriggerDispatch
        self.mcu = mcu
        self.dispatch = TriggerDispatch(mcu)
        self.reasons = MCU_trsync
        self.arm_cmd = None
        self.active = self.stop_requested = False
        mcu.register_config_callback(self._build_config)

    def _build_config(self):
        if self.mcu.get_constants().get('M300_PANEL_RELEASE_ABI') != 1:
            return
        queue = self.dispatch.get_command_queue()
        self.arm_cmd = self.mcu.lookup_command('m300_panel_release_arm oid=%c press=%u', cq=queue)
        self.disarm_cmd = self.mcu.lookup_command('m300_panel_release_disarm oid=%c', cq=queue)
        self.stop_cmd = self.mcu.lookup_command('trsync_trigger oid=%c reason=%c', cq=queue)

    def home_start(self, print_time, sample_time, sample_count, rest_time, triggered=True):
        completion = self.dispatch.start(print_time)
        self.active = True
        clock = self.mcu.print_time_to_clock(print_time)
        self.arm_cmd.send([self.dispatch.get_oid(), self.press_id], reqclock=clock)
        if self.stop_requested:
            self.stop()
        return completion

    def home_wait(self, end_time):
        try:
            self.dispatch.wait_end(end_time)
        finally:
            self.active = False
            self.disarm_cmd.send([self.dispatch.get_oid()])
            reason = self.dispatch.stop()
        if reason >= self.reasons.REASON_COMMS_TIMEOUT:
            raise self.mcu.get_printer().command_error('Communication timeout during platform hold')
        # The caller needs the actual halt count. No trigger timestamp is used
        # as a position reference for this manual move.
        return 0.

    def get_steppers(self):
        return self.dispatch.get_steppers()

    def stop(self):
        self.stop_requested = True
        if self.active:
            self.stop_cmd.send([self.dispatch.get_oid(), self.reasons.REASON_HOST_REQUEST])

    def move(self, printer, toolhead, target, speed, press_id):
        from .homing import HomingMove
        self.press_id = press_id
        self.stop_requested = False
        HomingMove(printer, [(self, 'panel release')], toolhead).homing_move(
            target, speed, probe_pos=True, check_triggered=False)


class M300NativeMaintenance(M300Maintenance):
    def __init__(self, config):
        super().__init__(config)
        # Moonraker may subscribe while MCU identification yields, before
        # klippy:connect has bound the native heaters.
        self.hotend = self.bed = None
        self.platform_speed = self._number('platform_speed', PLATFORM_SPEED, .1, 25.)
        self.phase_id = 0
        self.target = 0.
        self._bed_target = None
        self._hotend_target = None
        self._hold_context = self._hold_received = None
        self._hold_direction = None
        self._hold_validate = None
        self._hold_started = False
        self._platform_panel_local = False
        mcu = self.board.get_mcu()
        self.panel_release = PanelRelease(mcu) if hasattr(mcu, 'create_oid') else None
        self._pending_z = None
        self._idle_saved = None
        self.lease = NativeServiceLease(self, lambda:(self.token,self.phase_id),
                                       self._move_guard,self.cancel)
        self.gcode.register_command('ZORTRAX_PLATFORM',self.cmd_platform)

    def _connect(self):
        super()._connect()
        release = self.panel_release
        if release is not None and release.arm_cmd is not None:
            steppers = [s for s in self.toolhead.get_kinematics().get_steppers()
                        if s.get_name() == 'stepper_z' and s.get_mcu() is release.mcu]
            for stepper in steppers:
                release.dispatch.add_stepper(stepper)

    def _stop_lifecycle(self, *args):
        fault=(self.state,self.reason) if self.state=='FAULT' else None
        super()._stop_lifecycle(*args)
        self.lease.release()
        self._hold_context = self._hold_received = None
        if fault is not None:
            self.state,self.reason=fault

    def is_busy(self):
        return self.state not in ('IDLE','COMPLETE','CANCELLED') or self._executing

    def _authority(self, position=False):
        if not self.ready or self.printer.is_shutdown():
            raise self._error('Klippy is not ready')
        if not self.qualified:
            raise self._error('qualified=False; native maintenance profile is disabled')
        if self.board.mcu.is_fileoutput():
            raise self._error('FILEOUTPUT cannot actuate a physical maintenance service')
        require_idle_print(self.printer,self.reactor.monotonic())
        if position and not native_service_frame(self.printer, self.gcode_move, self.toolhead):
            raise self._error('native maintenance requires untransformed Cartesian motion')
        owner=other_service(self.printer,('m300_filament','m300_calibration',
            'm300_sd','m300_nvm','m300_motion','m300_fans','m300_thermal'),
            self.reactor.monotonic())
        if owner:
            raise self._error(owner+' owns resources')
        if position:
            self.board.require_motion()
            status=self.toolhead.get_kinematics().get_status(self.reactor.monotonic())
            if 'z' not in status['homed_axes']:
                raise self._error('home Z before moving the platform')
        else:
            self.board.require_heating()
        return self.job._temperatures(self.reactor.monotonic())

    def _move_guard(self):
        self._authority(True)
        if self.state not in ('MOVING','PLATFORM_HOLD'):
            raise self._error('platform move outside its active phase')

    def _begin(self,operation,state):
        self._idle()
        self._authority(operation not in ('HOTEND','BED'))
        self.token+=1
        self.phase_id+=1
        self.operation,self.state,self.reason=operation,state,''
        self._platform_panel_local = state == 'PLATFORM_HOLD'
        self._deadline=self.reactor.monotonic()+self.timeout
        self._pending_z=None
        try:
            # The hold worker can yield to its watchdog and to operator Cancel.
            # Prevent a different command from flushing or disabling its rail.
            hold_commands = ('G4', 'M400', 'SET_STEPPER_ENABLE') if state == 'PLATFORM_HOLD' else ()
            self.lease.acquire(self.toolhead, self.gcode_move, (self.hotend,self.bed),
                               extra_commands=hold_commands)
            self._idle_saved=self.job.idle.idle_timeout
            self.job._set_idle(max(self._idle_saved,self.timeout+60.))
        except Exception:
            self.lease.release()
            self.state='CANCELLED'
            raise
        self.activity()
        self.reactor.update_timer(self._timer,self.reactor.NOW)

    def _z_endpoint(self,distance):
        position=list(self.toolhead.get_position())
        position[2]+=distance
        low,high=self.job._axis_bounds()
        if not low[2]<=position[2]<=high[2]:
            raise self._error('platform move exceeds native Z axis limits (target %.2f, range %.2f to %.2f)'
                              % (position[2], low[2], high[2]))
        return position

    def start(self,operation,value=None):
        if operation=='JOG_Z':
            return self.platform(value)
        if operation not in ('HOTEND','BED'):
            raise self._error('use native heater/fan controls for this operation')
        self._idle()
        heater=self.hotend if operation=='HOTEND' else self.bed
        value=(260. if operation=='HOTEND' else 60.) if value is None else value
        if (type(value) not in (float,int) or not math.isfinite(value)
                or not heater.min_temp<=value<=target_limit(heater) or value<=0.):
            raise self._error('temperature outside native heater limits')
        self._begin(operation,'HEATING')
        self.target=float(value)
        self._bed_target=self.bed.get_temp(self.reactor.monotonic())[1]
        self._hotend_target=self.hotend.get_temp(self.reactor.monotonic())[1]
        try:
            self.lease.heat(heater,self.target)
        except Exception as exc:
            self._fault(str(exc))
            raise

    def platform(self,distance,speed=None):
        if (type(distance) not in (int,float) or not math.isfinite(distance)
                or distance == 0.):
            raise self._error('DISTANCE must be finite and positive')
        speed=self.platform_speed if speed is None else speed
        if type(speed) not in (int,float) or not math.isfinite(speed) or speed<=0.:
            raise self._error('SPEED must be finite and positive')
        self._authority(True)
        endpoint=self._z_endpoint(distance)
        self._begin('PLATFORM_UP' if distance<0. else 'PLATFORM_DOWN','MOVING')
        self._pending_z=(endpoint,speed)

    def hold(self,direction,context,received_at,validate,press_id):
        if direction not in (-1,1):
            raise self._error('invalid platform direction')
        if self.gcode.get_mutex().test():
            raise self._error('wait for the current Klipper command before holding the platform button')
        release = self.panel_release
        if release is None or release.arm_cmd is None or len(release.get_steppers()) != 1:
            raise self._error('platform hold needs MCU firmware with local panel release stop')
        if type(press_id) is not int or not 0 <= press_id <= 0xffffffff:
            raise self._error('invalid physical panel press counter')
        self._z_endpoint(0.)
        self._hold_drip = self.toolhead.drip_move
        self._hold_set_position = self.toolhead.set_position
        self._begin('PLATFORM_UP' if direction<0 else 'PLATFORM_DOWN','PLATFORM_HOLD')
        self._hold_direction,self._hold_context=direction,context
        self._hold_received,self._hold_validate=received_at,validate
        self._hold_press_id = press_id
        self._hold_started = False

    def refresh_hold(self,context,received_at,pressed,visible):
        if self.state!='PLATFORM_HOLD':
            return
        now=self.reactor.monotonic()
        if (not pressed or not visible or context!=self._hold_context
                or type(received_at) not in (int,float) or not math.isfinite(received_at)
                or not 0.<=now-received_at<=PANEL_LEASE
                or received_at<=self._hold_received):
            self.cancel('platform button released or view/panel lease expired')
        else:
            self._hold_received=received_at

    def _run_hold(self, now, token):
        if token != self.token or self.state != 'PLATFORM_HOLD':
            return
        if now-self._hold_received > PANEL_LEASE or not self._hold_validate():
            self.cancel('platform view/panel lease expired')
            return
        if self.gcode.get_mutex().test():
            self._hold_started = False
            return
        self._executing = True
        try:
            self._authority(True)
            release = self.panel_release
            step = release.get_steppers()[0].get_step_dist()
            velocity, _ = self.toolhead.get_max_velocity()
            kinematics = self.toolhead.get_kinematics()
            # The MCU stops on the raw release edge. Limit the 1 kHz
            # fallback sampling window to at most eight Z steps.
            speed = min(self.platform_speed, velocity, kinematics.max_z_velocity,
                        PLATFORM_HOLD_STEPS_PER_SECOND * step)
            self.toolhead.flush_step_generation()
            if self.state != 'PLATFORM_HOLD' or not self.ready or self.printer.is_shutdown():
                return
            target = list(self.toolhead.get_position())
            start_z = target[2]
            # HomingMove reconstructs XYZ from the rail coordinates plus the
            # halted step counts. The last native move may have left the rail
            # coordinates a fraction of a step from the logical toolhead.
            rail_start = kinematics.calc_position({
                s.get_name(): s.get_commanded_position() for s in kinematics.get_steppers()
            }) + target[3:]
            rail_z = rail_start[2]
            if not math.isfinite(rail_z) or abs(rail_z - start_z) > .5 * step + 1.e-6:
                raise self._error('Z rail position does not match the toolhead')
            low, high = self.job._axis_bounds()
            bounds = low[2], high[2]
            direction = self._hold_direction
            limit = bounds[direction > 0]
            epsilon = 4. * math.ulp(max(1., abs(limit), abs(rail_z)))
            steps = math.floor((direction * (limit - rail_z) + epsilon) / step)
            target_z = rail_z + direction * steps * step
            if steps < 1 or direction * (target_z - start_z) <= 0.:
                self._finish('CANCELLED', 'native Z limit reached')
                return
            target[2] = boundary_z(target_z, bounds, self._error)

            def check():
                if (self.token != token or not self.ready or self.printer.is_shutdown()
                        or self.state not in ('PLATFORM_HOLD', 'CANCELLING')):
                    raise self._error('platform hold no longer owns Z')

            def normalize_halt(z):
                if abs(z - rail_z) <= 1.e-6:
                    return start_z
                return boundary_z(z, bounds, self._error)

            toolhead = BoundedProbeToolhead(self.toolhead, target, speed, check,
                self._hold_drip, self._hold_set_position, normalize_halt,
                self._error, halt_start=rail_start)
            release.move(self.printer, toolhead, target, speed, self._hold_press_id)
            check()
            self._finish('CANCELLED', self.reason or 'platform button released or native Z limit reached')
        except Exception as exc:
            if not self.printer.is_shutdown() and self.ready:
                self._fault(str(exc))
        finally:
            self._executing = False

    def _finish(self,state,reason=''):
        # A pending short native move must drain before ownership is restored.
        self._pending_z=None
        self._hold_context=self._hold_received=self._hold_validate=None
        if self.operation in ('HOTEND','BED'):
            self.lease.heat(self.hotend if self.operation=='HOTEND' else self.bed,0.)
            self.target=0.
        if self._idle_saved is not None:
            self.job._set_idle(self._idle_saved)
            self._idle_saved=None
        self.state,self.reason=state,reason
        self.phase_id+=1
        self.lease.release()
        self.activity()

    def confirm(self,token,phase):
        if (type(token) is not int or type(phase) is not int
                or token!=self.token or phase!=self.phase_id or self.state!='WAIT_CONFIRM'):
            raise self._error('expired maintenance confirmation')
        self._finish('COMPLETE')

    def cancel(self,reason='operator stop',token=None,phase=None):
        if token is not None and (token!=self.token or phase!=self.phase_id):
            raise self._error('expired maintenance cancellation')
        if not self.is_busy() or self.state=='FAULT':
            return
        if self.state == 'PLATFORM_HOLD' and self._executing:
            self.panel_release.stop()
        if self.operation in ('HOTEND','BED'):
            self.lease.heat(self.hotend if self.operation=='HOTEND' else self.bed,0.)
            self.target=0.
        self._pending_z=None
        self._hold_context=self._hold_received=self._hold_validate=None
        self.state,self.reason='CANCELLING',reason
        self.phase_id+=1
        self.reactor.update_timer(self._timer,self.reactor.NOW)

    def stop(self,reason='operator stop'):
        self.cancel(reason)

    def _fault(self,reason):
        self.state,self.reason='FAULT',str(reason).removeprefix('M300 maintenance: ')
        from .m300_error_codes import report
        report(self.printer, self.reason, source='m300_maintenance', fatal=True)
        self.phase_id+=1
        self._pending_z=None
        try:
            # A failed heating service may not leave its selected heater on.
            self.lease.heat(self.bed if self.operation=='BED' else self.hotend,0.)
        finally:
            self.target=0.
            if not self.printer.is_shutdown():
                self.printer.invoke_async_shutdown('M300 maintenance: ' + self.reason)

    def sleep(self):
        raise self._error('native idle_timeout owns inactivity')

    def wake(self):
        self.activity()

    def _tick(self,now):
        if not self.ready or self.printer.is_shutdown():
            return self.reactor.NEVER
        try:
            self._indicators(now)
            if not self.is_busy():
                return now+.5
            if self.state=='FAULT':
                return self.reactor.NEVER
            if self.state=='PLATFORM_HOLD' and (self._hold_received is None
                    or now-self._hold_received>PANEL_LEASE or not self._hold_validate()):
                self.cancel('platform view/panel lease expired')
            if now>=self._deadline and self.state!='CANCELLING':
                self.cancel('maintenance deadline expired')
            if self._executing:
                return now+PERIOD
            if self.gcode.get_mutex().test():
                return now+PERIOD
            with self.gcode.get_mutex():
                self._executing=True
                try:
                    if self.state=='CANCELLING':
                        if self.job._queue_drained(now):
                            self._finish('CANCELLED',self.reason)
                    elif self.state in ('HEATING','WAIT_CONFIRM'):
                        temperatures=self._authority()
                        channel,peer=('hotend','bed') if self.operation=='HOTEND' else ('bed','hotend')
                        measured,target=temperatures[channel]
                        expected_peer=self._bed_target if self.operation=='HOTEND' else self._hotend_target
                        if target!=self.target or temperatures[peer][1]!=expected_peer:
                            raise self._error('heater target changed outside maintenance')
                        # OEM hotend branch is 260 C / ready at 258 C.
                        ready=(measured>=self.target-2. if self.operation=='HOTEND'
                               else abs(measured-self.target)<=2.)
                        if self.state=='HEATING' and ready:
                            self.state='WAIT_CONFIRM'
                            self.phase_id+=1
                    elif self.state == 'PLATFORM_HOLD':
                        if not self._hold_started and self.job._queue_drained(now):
                            self._hold_started = True
                            self.reactor.register_callback(
                                lambda eventtime, token=self.token: self._run_hold(eventtime, token))
                    elif self.state == 'MOVING':
                        self._authority(True)
                        if not self.job._queue_drained(now):
                            return now+PERIOD
                        if self._pending_z is not None:
                            endpoint, speed = self._pending_z
                            z = self.toolhead.get_position()[2]
                            remaining = endpoint[2] - z
                            step = min(PLATFORM_STEP_MM, speed * PLATFORM_STEP_SECONDS)
                            if abs(remaining) <= step:
                                self._pending_z = None
                                position = endpoint
                            else:
                                position = list(endpoint)
                                position[2] = z + math.copysign(step, remaining)
                                if position[2] == z:
                                    self.cancel('platform step is below Z coordinate resolution')
                                    return now + PERIOD
                            self.lease.move(position, speed)
                            self.toolhead.get_last_move_time()
                            # The finite endpoint bounds travel; the timeout bounds
                            # waiting for progress, even on a full-height move.
                            self._deadline = self.reactor.monotonic() + self.timeout
                        else:
                            self._finish('COMPLETE')
                finally:
                    self._executing=False
        except Exception as exc:
            self._fault(str(exc))
        return now+PERIOD

    def get_status(self,now):
        live=self.ready and not self.printer.is_shutdown()
        return dict(super().get_status(now),phase_id=self.phase_id,
            installed=True,native_control=True,target=self.target,
            target_hotend=self.target if self.operation=='HOTEND' else self.hotend.get_temp(now)[1] if self.hotend is not None else 0.,
            target_bed=self.target if self.operation=='BED' else self.bed.get_temp(now)[1] if self.bed is not None else 0.,
            can_confirm=live and self.state=='WAIT_CONFIRM',
            can_cancel=live and self.is_busy() and self.state not in ('FAULT','CANCELLING'),
            platform_held=self.state=='PLATFORM_HOLD',
            platform_panel_local=self._platform_panel_local,
            platform_speed_mm_s=self.platform_speed,
            revision='0.13.16.30-SERVICE-STARTUP')

    def cmd_platform(self,gcmd):
        direction=gcmd.get('DIRECTION').upper()
        if direction not in ('UP','DOWN'):
            raise gcmd.error('DIRECTION must be UP or DOWN')
        distance=gcmd.get_float('DISTANCE',1.,above=0.)
        self.platform((-1 if direction=='UP' else 1)*distance,
                      gcmd.get_float('SPEED',self.platform_speed,above=0.))
