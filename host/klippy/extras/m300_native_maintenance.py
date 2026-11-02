# SPDX-License-Identifier: GPL-3.0-or-later
"""OEM Maintenance on the existing native Klipper heaters and Z rail.

The panel holds a short motion lease; only one bounded native move can be
outstanding. Releasing, leaving the acknowledged view or losing panel freshness
stops further steps. No homing, raw GPIO or coordinate/limit overrides.
"""
import math

from .m300_maintenance import M300Maintenance, other_service
from .m300_native_service import NativeServiceLease, require_idle_print

PERIOD = .05
PANEL_LEASE = .75
QUANTUM = .1


class M300NativeMaintenance(M300Maintenance):
    def __init__(self, config):
        super().__init__(config)
        self.phase_id = 0
        self.target = 0.
        self._bed_target = None
        self._hold_context = self._hold_received = None
        self._hold_direction = None
        self._hold_validate = None
        self._pending_z = None
        self._idle_saved = None
        self.lease = NativeServiceLease(self, lambda:(self.token,self.phase_id),
                                       self._move_guard,self.cancel)
        self.gcode.register_command('ZORTRAX_PLATFORM',self.cmd_platform)

    def _stop_lifecycle(self, *args):
        super()._stop_lifecycle(*args)
        self.lease.release()
        self._hold_context = self._hold_received = None

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
        if self.gcode_move.move_transform not in (None,self.toolhead):
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
        self._authority(operation!='HOTEND')
        self.token+=1
        self.phase_id+=1
        self.operation,self.state,self.reason=operation,state,''
        self._deadline=self.reactor.monotonic()+self.timeout
        self._pending_z=None
        try:
            self.lease.acquire(self.toolhead,self.gcode_move,(self.hotend,self.bed))
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
            raise self._error('platform move exceeds native Z axis limits')
        return position

    def start(self,operation,value=None):
        if operation=='JOG_Z':
            return self.platform(value)
        if operation!='HOTEND':
            raise self._error('use native heater/fan controls for this operation')
        value=260. if value is None else value
        if (type(value) not in (float,int) or not math.isfinite(value)
                or not self.hotend.min_temp<=value<=self.hotend.max_temp or value<=0.):
            raise self._error('temperature outside native heater limits')
        self._begin('HOTEND','HEATING')
        self.target=float(value)
        self._bed_target=self.bed.get_temp(self.reactor.monotonic())[1]
        try:
            self.lease.heat(self.hotend,self.target)
        except Exception as exc:
            self._fault(str(exc))
            raise

    def platform(self,distance,speed=None):
        if (type(distance) not in (int,float) or not math.isfinite(distance)
                or distance==0. or abs(distance)>self.jog_distance):
            raise self._error('DISTANCE must be positive and within max_jog_distance')
        speed=self.jog_speed if speed is None else speed
        if type(speed) not in (int,float) or not math.isfinite(speed) or speed<=0.:
            raise self._error('SPEED must be finite and positive')
        self._authority(True)
        endpoint=self._z_endpoint(distance)
        self._begin('PLATFORM_UP' if distance<0. else 'PLATFORM_DOWN','MOVING')
        self._pending_z=(endpoint,speed)

    def hold(self,direction,context,received_at,validate):
        if direction not in (-1,1):
            raise self._error('invalid platform direction')
        if self.gcode.get_mutex().test():
            raise self._error('wait for the current Klipper command before holding the platform button')
        self._begin('PLATFORM_UP' if direction<0 else 'PLATFORM_DOWN','PLATFORM_HOLD')
        self._hold_direction,self._hold_context=direction,context
        self._hold_received,self._hold_validate=received_at,validate

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

    def _finish(self,state,reason=''):
        # A pending short native move must drain before ownership is restored.
        self._pending_z=None
        self._hold_context=self._hold_received=self._hold_validate=None
        if self.operation=='HOTEND':
            self.lease.heat(self.hotend,0.)
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
        if self.operation=='HOTEND':
            self.lease.heat(self.hotend,0.)
            self.target=0.
        self._pending_z=None
        self._hold_context=self._hold_received=self._hold_validate=None
        self.state,self.reason='CANCELLING',reason
        self.phase_id+=1
        self.reactor.update_timer(self._timer,self.reactor.NOW)

    def stop(self,reason='operator stop'):
        self.cancel(reason)

    def _fault(self,reason):
        self.state,self.reason='FAULT',str(reason)
        self.phase_id+=1
        self._pending_z=None
        try:
            self.lease.heat(self.hotend,0.)
        finally:
            self.target=0.
            if not self.printer.is_shutdown():
                self.printer.invoke_async_shutdown('M300 maintenance: '+str(reason))

    def sleep(self):
        raise self._error('native idle_timeout owns inactivity')

    def wake(self):
        self.activity()

    def _tick(self,now):
        if not self.ready or self.printer.is_shutdown():
            return self.reactor.NEVER
        try:
            self._indicators(now)
            if not self.is_busy() or self._executing:
                return now+.5
            if self.state=='FAULT':
                return self.reactor.NEVER
            if self.state=='PLATFORM_HOLD' and (self._hold_received is None
                    or now-self._hold_received>PANEL_LEASE or not self._hold_validate()):
                self.cancel('platform view/panel lease expired')
            if now>=self._deadline and self.state!='CANCELLING':
                self.cancel('maintenance deadline expired')
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
                        measured,target=temperatures['hotend']
                        if target!=self.target or temperatures['bed'][1]!=self._bed_target:
                            raise self._error('heater target changed outside maintenance')
                        # OEM hotend branch is 260 C / ready at 258 C.
                        if self.state=='HEATING' and measured>=self.target-2.:
                            self.state='WAIT_CONFIRM'
                            self.phase_id+=1
                    elif self.state in ('MOVING','PLATFORM_HOLD'):
                        self._authority(True)
                        if not self.job._queue_drained(now):
                            return now+PERIOD
                        if self.state=='PLATFORM_HOLD':
                            low,high=self.job._axis_bounds()
                            z=self.toolhead.get_position()[2]
                            distance=self._hold_direction*min(QUANTUM,
                                z-low[2] if self._hold_direction<0 else high[2]-z)
                            if abs(distance)<1.e-6:
                                self.cancel('native Z limit reached')
                            else:
                                self.lease.move(self._z_endpoint(distance),self.jog_speed)
                                self.toolhead.get_last_move_time()
                        elif self._pending_z is not None:
                            endpoint,speed=self._pending_z
                            self._pending_z=None
                            self.lease.move(endpoint,speed)
                            self.toolhead.get_last_move_time()
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
            can_confirm=live and self.state=='WAIT_CONFIRM',
            can_cancel=live and self.is_busy() and self.state not in ('FAULT','CANCELLING'),
            platform_held=self.state=='PLATFORM_HOLD',
            revision='0.13.16.5-NATIVE-MAINTENANCE')

    def cmd_platform(self,gcmd):
        direction=gcmd.get('DIRECTION').upper()
        if direction not in ('UP','DOWN'):
            raise gcmd.error('DIRECTION must be UP or DOWN')
        distance=gcmd.get_float('DISTANCE',1.,above=0.)
        self.platform((-1 if direction=='UP' else 1)*distance,
                      gcmd.get_float('SPEED',self.jog_speed,above=0.))
