# SPDX-License-Identifier: GPL-3.0-or-later
"""M300 preparation and protected pauses around the pinned native SD owner.

The native pause object owns PAUSE_STATE and the native SD object owns its
worker/file position. No new feeder, kinematics, heater PWM or MCU driver.
"""
from collections import deque
import copy
import json
import logging
import math
import os

from .m300_job_state import bounded_park
from .m300_native_service import NativeServiceLease, lock_command

REVISION = '0.13.16.29-UNIFIED-NATIVE-START'
PERIOD = .25


class M300PrintControl:
    def __init__(self, config):
        self.config, self.printer = config, config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.board = self.printer.load_object(config, 'm300_mcu')
        self.pause = self.printer.load_object(config, 'pause_resume')
        self.sd = self.printer.load_object(config, 'virtual_sdcard')
        self.motion = self.printer.load_object(config, 'm300_motion')
        def number(name, default, low, high):
            value = config.getfloat(name, default, minval=low, maxval=high)
            if not math.isfinite(value):
                raise config.error('M300 print control: nonfinite '+name)
            return value
        self.park_xy = (number('park_x',300.,-1000.,1000.), number('park_y',305.,-1000.,1000.))
        self.z_hop = number('pause_z_hop',5.,.1,20.)
        self.clearance = number('min_park_clearance',5.,.1,20.)
        self.xy_speed = number('park_speed',100.,1.,300.)
        self.z_speed = number('z_lift_speed',5.,.1,35.)
        self.retract = number('pause_retract',2.,0.,10.)
        self.e_speed = number('retract_speed',2.,.1,20.)
        self.standby_after = number('pause_standby_after',600.,1.,14400.)
        self.off_after = number('pause_heater_off_after',1800.,1.,28800.)
        self.standby_temp = number('pause_standby_temperature',150.,0.,300.)
        self.heat_timeout = number('heat_timeout',1800.,60.,3600.)
        self.move_timeout = number('move_timeout',120.,1.,1200.)
        self.purge_length = number('purge_length',40.,1.,100.)
        self.purge_filament = number('purge_filament',3.,0.,10.)
        self.purge_height = number('purge_height',.3,.2,1.)
        self.platform_soak_seconds = number('platform_soak_seconds',60.,0.,600.)
        if self.standby_after > self.off_after or self.clearance > self.z_hop:
            raise config.error('M300 print control: invalid pause deadlines/clearance')
        self.generation = 0
        self.state, self.phase = 'IDLE', 'IDLE'
        self.ready = False
        self.context = None
        self.lease = None
        self.steps = deque()
        self.waiting = False
        self.deadline = self.stable_since = None
        self.last_error, self.notice = '', ''
        self._change_pending = False
        self._change_temperature = None
        self._material_was_busy = False
        self._cancel_park = False
        self._pending_file = None
        self.operation = None
        self._internal = False
        self._display_owned = False
        self._display_previous = self._display_message = None
        self._timer = self.reactor.register_timer(self._tick)
        self.printer.register_event_handler('klippy:connect', self._connect)
        self.printer.register_event_handler('klippy:ready', self._ready)
        for event in ('klippy:shutdown','klippy:disconnect','gcode:request_restart'):
            self.printer.register_event_handler(event, lambda *a,event=event:self._stop(event))
        self.printer.register_event_handler('stepper_enable:motor_off', self._motor_off)
        self.printer.register_event_handler('virtual_sdcard:reset_file', self._file_reset)
        for name, handler in (('M601',self.cmd_PAUSE), ('FILAMENT_READY',self.cmd_material_ready),
                              ('PAUSE_TEMP_STATUS',self.cmd_status),
                              ('PRINT_CONTROL_STATUS',self.cmd_status),
                              ('ZORTRAX_PAUSE_IDLE',self.cmd_idle),
                              ('ZORTRAX_PRINT_START',self.cmd_start),
                              ('ZORTRAX_PRINT_END',self.cmd_end)):
            self.gcode.register_command(name,handler)

    def _connect(self):
        if not self.board.native_control:
            raise self.config.error('M300 print control requires native control')
        self.toolhead = self.printer.lookup_object('toolhead')
        self.gcode_move = self.printer.lookup_object('gcode_move')
        self.heaters = self.printer.lookup_object('heaters')
        self.hotend = self.heaters.lookup_heater('extruder')
        self.bed = self.heaters.lookup_heater('heater_bed')
        self.base_pause, self.base_resume = self.pause.cmd_PAUSE, self.pause.cmd_RESUME
        self.base_cancel, self.base_clear = self.pause.cmd_CANCEL_PRINT, self.pause.cmd_CLEAR_PAUSE
        self.original_home = self.gcode.register_command('G28',None)
        self.gcode.register_command('G28',self.cmd_G28)
        for name, callback in (('PAUSE',self.cmd_PAUSE),('RESUME',self.cmd_RESUME),
                               ('CANCEL_PRINT',self.cmd_CANCEL_PRINT),('CLEAR_PAUSE',self.cmd_clear),
                               ('M25',self.cmd_PAUSE)):
            self.gcode.register_command(name,None)
            self.gcode.register_command(name,callback)
        self.command_guards = []
        self.command_backends = {}
        for name in ('M24','M23','SDCARD_PRINT_FILE','SDCARD_RESET_FILE','SET_KINEMATIC_POSITION',
                     'FORCE_MOVE','STEPPER_BUZZ','BED_MESH_CLEAR','BED_MESH_PROFILE','BED_MESH_OFFSET',
                     'BED_MESH_CALIBRATE','SET_GCODE_OFFSET','SAVE_CONFIG','G0','G1',
                     'PROBE','PROBE_ACCURACY','PROBE_CALIBRATE','SCREWS_TILT_CALCULATE',
                     'Z_TILT_ADJUST','QUAD_GANTRY_LEVEL','PID_CALIBRATE',
                     'SET_EXTRUDER_ROTATION_DISTANCE','SYNC_EXTRUDER_MOTION'):
            previous = self.gcode.ready_gcode_handlers.get(name)
            if previous is None:continue
            self.command_backends[name]=previous
            def guarded(gcmd, previous=previous, name=name):
                if (self.busy or self.context is not None) and not self._internal:
                    raise gcmd.error('M300 protected print: use RESUME or CANCEL_PRINT; '+name+' refused')
                return previous(gcmd)
            record = lock_command(self.gcode,name,guarded)
            if record:self.command_guards.append(record)
        enables = self.printer.lookup_object('stepper_enable')
        for name in enables.get_steppers():
            enables.lookup_enable(name).register_state_callback(self._enable_changed)
        # Native endpoints normally submit G-code. Cancel may instead revoke
        # a yielding homing/heat operation before its G-code mutex is free.
        web = self.printer.lookup_object('webhooks',None)
        if web is not None:
            for action in ('pause','resume','cancel'):
                path = 'pause_resume/'+action
                old = web._endpoints.get(path)
                if getattr(old,'__self__',None) is not self.pause:
                    raise self.config.error('M300 print control requires the native pause endpoint: '+path)
                def endpoint(req, action=action):
                    if action=='cancel' and self.busy:
                        self._request_cancel('Fluidd cancel')
                    else:
                        self.gcode.run_script({'pause':'PAUSE','resume':'RESUME','cancel':'CANCEL_PRINT'}[action])
                web._endpoints[path]=endpoint

    @property
    def busy(self):
        return self.state not in ('IDLE','PAUSED','FAILED')

    def _ready(self):
        self.ready = True

    def _error(self, reason):
        return self.printer.command_error('M300 print: '+str(reason))

    def _command(self, name, params=None):
        return self.gcode.create_gcode_command(name,name,params or {})

    def _wake(self):
        self.reactor.update_timer(self._timer,self.reactor.NOW)

    def _phase(self, name, seconds=None):
        self.phase = name
        self.deadline = self.reactor.monotonic() + (seconds or self.move_timeout)
        display = self.printer.lookup_object('display_status',None)
        if display is not None:
            if not self._display_owned:self._display_previous=display.message
            self._display_owned=True
            display.message = 'Print: '+name.replace('_',' ').title()
            self._display_message=display.message

    def _release(self):
        if self.lease is not None:
            lease,self.lease = self.lease,None
            lease.release()

    def _lease(self):
        if self.lease is None:
            token=self.generation
            self.lease=NativeServiceLease(self,lambda:token,lambda:self._guard(token),
                                          lambda reason:self._request_cancel(reason))
            self.lease.acquire(self.toolhead,self.gcode_move,(self.hotend,self.bed),
                               extra_commands=('CANCEL_PRINT_BASE',))

    def _off(self):
        if not hasattr(self,'heaters'):return
        try:self.heaters.turn_off_all_heaters()
        except Exception:
            logging.exception('M300 print heater-off')
            if not self.printer.is_shutdown():
                self.printer.invoke_async_shutdown('M300 print heater-off failed')

    def _drop(self, reason, *, off=True):
        self.generation += 1
        self.steps.clear()
        self.waiting = False
        self._release()
        self.context,self._pending_file = None,None
        self.operation = None
        self._change_pending = False
        self._cancel_park = False
        self.state,self.phase = 'IDLE','IDLE'
        if off:self._off()
        display=self.printer.lookup_object('display_status',None)
        if display is not None and self._display_owned and display.message==self._display_message:
            display.message=self._display_previous
        self._display_owned=False
        self.reactor.update_timer(self._timer,self.reactor.NEVER)

    def _stop(self, reason):
        active=self.busy or self.context is not None
        self.ready=False
        self._drop(reason,off=active)

    def _file_reset(self,*args):
        if self.context is not None or self.busy:
            self._drop('native file reset')

    def _motor_off(self,*args):
        if self.context is not None:
            self.context['invalid']='motor position was released; cancel this print'

    def _enable_changed(self, print_time, enabled):
        if not enabled:self._motor_off()

    def _file(self):
        stream=self.sd.current_file
        if stream is None:raise self._error('native print file is unavailable')
        try:
            s=os.fstat(stream.fileno())
            stamp=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
        except (AttributeError,OSError,ValueError):
            raise self._error('native print file cannot be verified')
        return (id(stream),getattr(stream,'name',None),self.sd.file_position,stamp)

    def _bounds(self):
        status=self.toolhead.get_kinematics().get_status(self.reactor.monotonic())
        return status['axis_minimum'],status['axis_maximum'],status['homed_axes']

    def _guard(self, token):
        if token != self.generation or not self.ready or self.printer.is_shutdown():
            raise self._error('print operation ended')
        self.board.require_motion()
        self.board.require_heating()
        if self.operation is not None and self.operation.get('file') is not None:
            if self.operation['file'] != self._file():
                raise self._error('preparation file identity or position changed')
        if self.context is not None:
            ctx=self.context
            if ctx.get('invalid'):raise self._error(ctx['invalid'])
            if not self.pause.is_paused:raise self._error('native pause state changed')
            if ctx.get('file') is not None and ctx['file'] != self._file():
                raise self._error('paused file identity or position changed')
            if self.gcode_move.saved_states.get('PAUSE_STATE') != ctx['saved']:
                raise self._error('native PAUSE_STATE was replaced')
            if self._mesh_identity() != ctx['mesh']:
                raise self._error('motion transform or active bed mesh changed')
            low,high,homed=self._bounds()
            if not set('xyz') <= set(homed) or (tuple(low[:3]),tuple(high[:3])) != ctx['bounds']:
                raise self._error('homing or machine limits changed')

    def _mesh_identity(self):
        transform=self.gcode_move.move_transform
        bedmesh=self.printer.lookup_object('bed_mesh',None)
        mesh=bedmesh.get_mesh() if bedmesh is not None else None
        return (id(transform),id(mesh),tuple(getattr(mesh,'mesh_offsets',())))

    def _drained(self, now):
        self.toolhead.get_last_move_time()  # Flush the final native lookahead segment.
        print_time,estimated,empty=self.toolhead.check_busy(now)
        return empty and print_time <= estimated

    def _position_is(self, expected):
        return all(abs(a-b) <= .01 for a,b in zip(self.toolhead.get_position()[:3],expected))

    def _plan(self, hop=None, clearance=None):
        low,high,homed=self._bounds()
        if not set('xyz') <= set(homed):raise self._error('known XYZ position is required')
        park=self.park_xy
        self.notice=''
        if not all(low[i] <= park[i] <= high[i] for i in (0,1)):
            park=tuple(self.toolhead.get_position()[:2])
            self.notice='Configured park is outside XY travel; paused in place'
        result=bounded_park(self.toolhead.get_position(),low,high,park,
                            self.z_hop if hop is None else hop,
                            self.clearance if clearance is None else clearance)
        if not result['xy_allowed']:
            self.notice='Insufficient Z clearance; XY park skipped'
        return result

    def _move(self, position, speed, *, extrusion=False):
        self._guard(self.generation)
        if len(position)==3:position=[*position,self.toolhead.get_position()[3]]
        self.lease.move(position,speed,extruder_only=extrusion)
        self.waiting=True
        self.deadline=self.reactor.monotonic()+self.move_timeout

    def _e(self, amount):
        measured,target=self.hotend.get_temp(self.reactor.monotonic())
        if measured < self.hotend.min_extrude_temp or target <= 0:
            raise self._error('extrusion requires a hot nozzle')
        pos=list(self.toolhead.get_position());pos[3]+=amount
        self._move(pos,self.e_speed,extrusion=True)

    def cmd_PAUSE(self,gcmd):
        if self.context is not None:
            gcmd.respond_info('M300: print is already paused')
            return
        if self.busy:raise self._error('preparation is busy; Cancel remains available')
        if self.sd.current_file is None or self.sd.work_timer is None:
            raise self._error('PAUSE requires an active native file print')
        self.board.require_motion();self.board.require_heating()
        targets={name:heater.get_temp(self.reactor.monotonic())[1]
                 for name,heater in (('hotend',self.hotend),('bed',self.bed))}
        self.base_pause(gcmd)
        saved=copy.deepcopy(self.gcode_move.saved_states['PAUSE_STATE'])
        low,high,homed=self._bounds()
        self.generation += 1
        now=self.reactor.monotonic()
        self.context=dict(saved=saved,file=None,origin=list(self.toolhead.get_position()[:3]),
            bounds=(tuple(low[:3]),tuple(high[:3])),targets=targets,started=now,thermal_since=now,
            mesh=self._mesh_identity(),invalid='',change_required=False,material_success=False,
            flow_confirmed=False,retracted=0.)
        self._pending_file=id(self.sd.current_file)
        self.state='PAUSING';self.last_error=''
        self._phase('WAIT_PAUSE')
        self._lease();self._wake()

    def _park_pause(self):
        ctx=self.context
        ctx['file']=self._file()
        if id(self.sd.current_file) != self._pending_file or not self._position_is(ctx['origin']):
            raise self._error('position or file changed before pause drained')
        ctx['plan']=self._plan()
        self.steps.clear()
        measured,target=self.hotend.get_temp(self.reactor.monotonic())
        if self.retract and measured >= self.hotend.min_extrude_temp and target > 0:
            self.steps.append(('e',-self.retract))
            ctx['retracted']=self.retract
        for pos in ctx['plan']['park_moves']:self.steps.append(('move',pos))
        self.steps.append(('paused',None))
        self._phase('PARKING')

    def _material(self):
        return self.printer.lookup_object('m300_filament',None)

    def _material_busy(self):
        obj=self._material()
        return obj is not None and obj.is_busy()

    def _paused_tick(self,now):
        self._guard(self.generation)
        ctx=self.context
        if self._material_busy():
            self._material_was_busy=True
            return
        if self._material_was_busy:
            ctx['thermal_since']=now
            self._material_was_busy=False
        if not self._position_is(ctx['plan']['target']):
            raise self._error('parked XYZ position changed; cancel this print')
        elapsed=now-ctx['thermal_since']
        target=self.hotend.get_temp(now)[1]
        if elapsed >= self.off_after and target > 0:
            self.hotend.set_temp(0.)
            self._phase('PAUSED_NOZZLE_OFF')
        elif elapsed >= self.standby_after and target > self.standby_temp:
            self.hotend.set_temp(min(self.standby_temp,ctx['targets']['hotend']))
            self._phase('PAUSED_STANDBY')

    def cmd_RESUME(self,gcmd):
        if self.context is None:raise self._error('no protected pause is available')
        if self.busy or self._material_busy():raise self._error('wait for the active procedure')
        self._guard(self.generation)
        if not self._position_is(self.context['plan']['target']):
            raise self._error('parked position changed')
        if self.context['change_required'] and not self.context['material_success']:
            raise self._error('finish the material change before resuming')
        for name,heater in (('hotend',self.hotend),('bed',self.bed)):
            target=self.context['targets'][name]
            if (not math.isfinite(target) or target < 0. or
                    target and not heater.min_temp <= target <= heater.max_temp):
                raise self._error('saved print temperature is outside heater limits')
        saved_hotend=self.context['targets']['hotend']
        if (saved_hotend and saved_hotend < self.hotend.min_extrude_temp
                or (self.context['retracted'] or self.context['change_required'])
                and saved_hotend < self.hotend.min_extrude_temp):
            raise self._error('saved print temperature is not valid for extrusion')
        velocity=gcmd.get_float('VELOCITY',self.pause.recover_velocity,above=0.)
        if not math.isfinite(velocity):raise self._error('resume velocity must be finite')
        self.context['resume_velocity']=velocity
        self.state='RESUMING';self.steps.clear();self.stable_since=None
        self._lease()
        for name,heater in (('hotend',self.hotend),('bed',self.bed)):
            target=self.context['targets'][name]
            self.lease.heat(heater,target)
        self._phase('HEATING',self.heat_timeout);self._wake()

    def _temperatures_ready(self,targets,now):
        ready=True
        for name,heater in (('hotend',self.hotend),('bed',self.bed)):
            measured,current=heater.get_temp(now);target=targets[name]
            if not all(math.isfinite(v) for v in (measured,current,target)) or current != target:
                raise self._error('temperature target changed during '+self.phase)
            if target > 0:ready=ready and abs(measured-target) <= 2.
        if not ready:self.stable_since=None
        elif self.stable_since is None:self.stable_since=now
        return ready and now-self.stable_since >= 2.

    def _resume_moves(self):
        ctx=self.context
        if ctx['change_required'] and not ctx['flow_confirmed']:
            self._release();self.state='PAUSED';ctx['thermal_since']=self.reactor.monotonic()
            self.notice='Verify nozzle flow, then FILAMENT_READY and RESUME'
            self._phase('WAIT_FILAMENT_READY')
            return
        for pos in ctx['plan']['return_moves']:self.steps.append(('move',pos))
        if ctx['retracted']:self.steps.append(('e',ctx['retracted']))
        self.steps.append(('resume',None));self._phase('RETURNING')

    def cmd_material_ready(self,gcmd):
        ctx=self.context
        if ctx is None or self.busy or self._material_busy():raise self._error('requires a settled pause')
        self._guard(self.generation)
        if not ctx['change_required'] or not ctx['material_success']:
            raise self._error('complete the material change first')
        measured,target=self.hotend.get_temp(self.reactor.monotonic())
        if measured < self.hotend.min_extrude_temp or target <= 0:
            raise self._error('heat the nozzle and verify visible flow before confirming')
        ctx['flow_confirmed']=True
        gcmd.respond_info('M300: filament flow confirmed; press Resume')

    def material_begin(self):
        if self.context is None or self.busy:
            raise self._error('material change requires a protected settled pause')
        self._guard(self.generation)
        if not self.context['plan']['xy_allowed'] or self.notice.startswith('Configured park'):
            raise self._error('not enough clearance for a material-change park')
        self.context.update(change_required=True,material_success=False,flow_confirmed=False)
        return self.context['targets']['hotend']

    def material_complete(self,success):
        if self.context is None:return
        self.context['material_success']=bool(success)
        self.context['thermal_since']=self.reactor.monotonic()
        if success:self.context['retracted']=0.  # The existing wizard has primed the new material.
        self._wake()

    def request_change(self,gcmd,temperature=None):
        if self.context is not None and (self.busy or self._material_busy()):
            raise self._error('wait for the active material/pause operation')
        self._change_temperature=temperature
        if self.context is None:
            self._change_pending=True
            try:self.cmd_PAUSE(self._command('PAUSE'))
            except Exception:
                self._change_pending=False
                raise
        else:self._begin_change()

    def _begin_change(self):
        self._change_pending=False
        obj=self._material()
        if obj is None:raise self._error('material service is not configured')
        obj.start('CHANGE',temperature=self._change_temperature)

    def cmd_idle(self,gcmd):
        if self.context is not None or self.busy:
            return  # Timed nozzle cooling is owned by this module, not M84.
        self.gcode.run_script_from_command('TURN_OFF_HEATERS\nZORTRAX_IDLE_RELEASE_XYE')

    def cmd_G28(self,gcmd):
        if self.context is not None or self.busy:
            raise self._error('homing is unavailable during a protected print operation')
        return self.original_home(gcmd)

    def cmd_clear(self,gcmd):
        if self.context is not None or self.busy:
            raise self._error('use CANCEL_PRINT to discard a protected pause')
        return self.base_clear(gcmd)

    def cmd_CANCEL_PRINT(self,gcmd):
        self._request_cancel('operator cancel')

    def _request_cancel(self,reason):
        if self.state=='CANCELLING':return
        self._cancel_park=self.context is not None or self.operation is not None or self.sd.current_file is not None
        self.generation += 1;self.steps.clear();self.waiting=False
        self._release()
        material=self._material()
        if material is not None:material.parent_cancel(reason)
        motion=self.printer.lookup_object('m300_motion',None)
        if motion is not None and motion.is_busy():motion.cancel(reason)
        self._off()
        self.sd.must_pause_work=True
        if not self.ready or self.printer.is_shutdown():return
        self.context=None;self.operation=None;self._change_pending=False
        self.state='CANCELLING';self._phase('WAIT_CANCEL');self._wake()

    def _cancel_drained(self):
        # Internal start/end barriers also pause the SD worker, while native
        # pause.sd_paused is false. Native cmd_CANCEL_PRINT alone then skips
        # do_cancel(); close via that native method after the worker drains.
        if self.sd.current_file is not None:self.sd.do_cancel()
        self.base_cancel(self._command('CANCEL_PRINT'))
        self._off();self._fan_off()
        self.steps.clear()
        if self._cancel_park and not self._material_busy() and not self.printer.is_shutdown():
            try:
                self.board.require_motion()
                self.board.require_heating()
                plan=self._plan()
            except Exception:
                plan=None
            if plan:
                self._lease()
                for pos in plan['park_moves']:self.steps.append(('move',pos))
        self.steps.append(('cancelled',None));self._phase('CANCEL_PARK')

    def _fan_off(self):
        fan=self.printer.lookup_object('fan',None)
        if fan is not None:self.gcode.run_script_from_command('M107')

    def _temperature_target(self,gcmd,key,heater,default,minimum=0.):
        value=gcmd.get_float(key,default,minval=minimum,maxval=heater.max_temp)
        if not math.isfinite(value) or value and value < heater.min_temp:
            raise self._error('invalid '+key)
        return value

    def _begin_operation(self,state):
        if (self.context is not None or self.busy or self.state=='FAILED'
                or self.pause.is_paused or self._material_busy()):
            raise self._error('finish or cancel the current print procedure')
        # A running native file is allowed; unrelated OEM/mesh work is not.
        for name in ('m300_motion','m300_pad_mesh','m300_calibration','m300_maintenance',
                     'm300_fans','m300_thermal'):
            obj=self.printer.lookup_object(name,None)
            if obj is None:continue
            if name=='m300_fans':
                owned=getattr(obj,'test',None) is not None
            elif hasattr(obj,'is_busy'):owned=obj.is_busy()
            elif hasattr(obj,'get_status'):owned=obj.get_status(self.reactor.monotonic()).get('busy',False)
            else:owned=getattr(obj,'busy',False)
            if owned:
                raise self._error(name+' owns resources')
        self.board.require_motion();self.board.require_heating()
        self.generation+=1;self.steps.clear();self.waiting=False;self.last_error=''
        self.state=state
        self.operation=dict(file=None,stream=id(self.sd.current_file) if self.sd.current_file else None,
                            resume=self.sd.work_timer is not None)
        if self.sd.work_timer is not None:self.sd.do_pause()
        self._phase('WAIT_START' if state=='STARTING' else 'WAIT_END')
        self._lease();self._wake()

    def cmd_start(self,gcmd):
        target=self._temperature_target(gcmd,'EXTRUDER_TEMP',self.hotend,
            self.hotend.get_temp(self.reactor.monotonic())[1],self.hotend.min_extrude_temp)
        bed=self._temperature_target(gcmd,'BED_TEMP',self.bed,
            self.bed.get_temp(self.reactor.monotonic())[1])
        mesh=gcmd.get('MESH','AUTO')
        bedmesh=self.printer.lookup_object('bed_mesh',None)
        requested_mesh=mesh
        if mesh.upper()=='AUTO':
            mesh=('m300_pads' if bedmesh is not None and 'm300_pads' in bedmesh.pmgr.get_profiles()
                  else 'NONE')
        if mesh.upper()!='NONE' and (bedmesh is None or mesh not in bedmesh.pmgr.get_profiles()):
            raise self._error('saved mesh '+mesh+' is unavailable; measure/save it or use MESH=NONE')
        nvm=self.printer.lookup_object('m300_nvm',None)
        full_preheat=bool(nvm is not None and nvm.get_setting('full_platform_preheat',False))
        self._begin_operation('STARTING')
        self.operation.update(targets=dict(hotend=target,bed=bed),mesh=mesh,
                              requested_mesh=requested_mesh,
                              soak_seconds=self.platform_soak_seconds if full_preheat and bed>0. else 0.)

    def cmd_end(self,gcmd):
        self._begin_operation('ENDING')

    def _operation_drained(self):
        op=self.operation
        if op['stream'] is not None:
            if id(self.sd.current_file)!=op['stream']:raise self._error('print file changed before preparation')
            op['file']=self._file()
        if self.state=='STARTING':
            for name,heater in (('hotend',self.hotend),('bed',self.bed)):
                self.lease.heat(heater,op['targets'][name])
            self.stable_since=None;self._phase('HEATING',self.heat_timeout)
        else:
            plan=self._plan()
            measured,target=self.hotend.get_temp(self.reactor.monotonic())
            if self.retract and measured>=self.hotend.min_extrude_temp and target>0:
                self.steps.append(('e',-self.retract))
            for pos in plan['park_moves']:self.steps.append(('move',pos))
            self.steps.append(('ended',None));self._phase('END_PARK')

    def _start_home(self):
        token=self.generation
        self._release();self._phase('HOMING',self.heat_timeout)
        self.printer.lookup_object('m300_motion').home()
        self._guard(token)  # Homing yields to cancellation/shutdown.
        self._lease()
        mesh=self.operation['mesh']
        if mesh.upper()=='NONE':
            bedmesh=self.printer.lookup_object('bed_mesh',None)
            if bedmesh is not None:bedmesh.set_mesh(None)
        else:self.printer.lookup_object('bed_mesh').pmgr.load_profile(mesh)
        # Use native G-code moves here: the active bed-mesh transform must
        # compensate purge height. Physical manual_move would bypass it.
        self._release()
        low,high,homed=self._bounds()
        if not set('xyz') <= set(homed):raise self._error('start homing did not establish XYZ')
        x,y=low[0]+5.,low[1]+10.
        if x+self.purge_length>high[0] or y>high[1] or high[2]<5.:
            raise self._error('purge line does not fit native travel')
        self._script('SAVE_GCODE_STATE NAME=M300_START_STATE')
        for line in ('G90','M83','M220 S100','M221 S100','G1 Z5 F300',f'G1 X{x:.5f} Y{y:.5f} F6000',
                     f'G1 Z{self.purge_height:.5f} F300',
                     f'G1 X{x+self.purge_length:.5f} E{self.purge_filament:.5f} F600',
                     'G1 Z5 F300','RESTORE_GCODE_STATE NAME=M300_START_STATE MOVE=0'):
            self._guard(token);self._script(line)
        self._guard(token);self._lease();self.waiting=True
        self.steps.append(('started',None));self._phase('PURGE_DRAIN')

    def _script(self,line):
        self._internal=True
        try:self.gcode.run_script_from_command(line)
        finally:self._internal=False

    def _finish_operation(self,end=False):
        token=self.generation;op=self.operation
        self._guard(token);self._release()
        if end:self._off();self._fan_off()
        self._guard(token)
        resume=op['resume']
        self._drop('end' if end else 'start',off=False)
        if resume:self.sd.do_resume()  # Native worker still owns EOF/completion.

    def _step(self):
        kind,value=self.steps.popleft()
        if kind=='move':
            current=self.toolhead.get_position()
            speed=self.z_speed if all(abs(a-b)<1e-6 for a,b in zip(current[:2],value[:2])) else self.xy_speed
            self._move(value,speed)
        elif kind=='e':self._e(value)
        elif kind=='paused':
            self._release();self.state='PAUSED';self._phase('PAUSED')
            self.context['thermal_since']=self.reactor.monotonic()
            if self._change_pending:self._begin_change()
        elif kind=='resume':
            token=self.generation
            self._guard(token)
            self._release()
            self.base_resume(self._command('RESUME',{'VELOCITY':str(self.context['resume_velocity'])}))
            if token==self.generation:self._drop('resumed',off=False)
        elif kind=='cancelled':self._drop('cancelled',off=False)
        elif kind=='started':self._finish_operation()
        elif kind=='ended':self._finish_operation(end=True)

    def _fail(self,reason):
        self.last_error=str(reason)
        self.steps.clear();self.waiting=False
        self._release();self._off()
        if self.context is not None:self.context['invalid']=self.last_error
        self.state,self.phase='FAILED','FAILED'
        from .m300_error_codes import report
        report(self.printer,reason,source='m300_print_control',fatal=self.printer.is_shutdown())

    def _tick(self,now):
        if not self.ready:return self.reactor.NEVER
        if self.state in ('IDLE','FAILED'):return self.reactor.NEVER
        if self.gcode.get_mutex().test():return now+PERIOD
        token=self.generation
        try:
            with self.gcode.get_mutex():
                if self.state=='PAUSED':self._paused_tick(now)
                else:
                    if self.state!='CANCELLING':self._guard(self.generation)
                    if self.deadline is not None and now > self.deadline:
                        raise self._error('timeout during '+self.phase)
                    if self.waiting:
                        if not self._drained(now):return now+PERIOD
                        self.waiting=False
                    if self.phase=='WAIT_PAUSE':
                        if self.sd.work_timer is not None or not self._drained(now):return now+PERIOD
                        self._park_pause()
                    elif self.phase=='WAIT_CANCEL':
                        if (self.sd.work_timer is not None or self._material_busy()
                                or not self._drained(now)):return now+PERIOD
                        self._cancel_drained()
                    elif self.state=='RESUMING' and self.phase=='HEATING':
                        if self._temperatures_ready(self.context['targets'],now):self._resume_moves()
                    elif self.phase in ('WAIT_START','WAIT_END'):
                        if self.sd.work_timer is not None or not self._drained(now):return now+PERIOD
                        self._operation_drained()
                    elif self.state=='STARTING' and self.phase in ('HEATING','PLATFORM_SOAK'):
                        if self._temperatures_ready(self.operation['targets'],now):
                            if now-self.stable_since >= 2.+self.operation['soak_seconds']:
                                self._start_home()
                            elif self.phase=='HEATING':
                                # Keep the original bounded heating deadline. A
                                # temperature excursion resets continuous soak.
                                self._phase('PLATFORM_SOAK',max(.001,self.deadline-now))
                    elif self.steps:self._step()
        except Exception as exc:
            logging.exception('M300 print control failed')
            if token==self.generation:self._fail(exc)
        return now+PERIOD if self.context is not None or self.busy else self.reactor.NEVER

    def get_status(self,now):
        ctx=self.context
        measured,target=self.hotend.get_temp(now) if hasattr(self,'hotend') else (0.,0.)
        return dict(revision=REVISION,state=self.state,phase=self.phase,busy=self.busy,
            session_token=self.generation,park_xy=list(self.park_xy),last_error=self.last_error,
            notice=self.notice,paused=bool(ctx),targets=copy.deepcopy(ctx['targets']) if ctx else None,
            start=copy.deepcopy({key:self.operation.get(key) for key in
                                ('targets','mesh','requested_mesh','soak_seconds')}) if self.operation else None,
            soak_remaining=(max(0.,2.+self.operation['soak_seconds']-(now-self.stable_since))
                            if self.operation and self.phase=='PLATFORM_SOAK' and self.stable_since is not None else None),
            pause_seconds=max(0.,now-ctx['started']) if ctx else 0.,
            material_change_complete=bool(ctx and ctx['material_success']),
            can_confirm_filament=bool(ctx and ctx['material_success'] and target>0.
                                     and measured>=self.hotend.min_extrude_temp),
            requires_filament_ready=bool(ctx and ctx['change_required'] and not ctx['flow_confirmed']))

    def cmd_status(self,gcmd):
        gcmd.respond_info('M300_PRINT_CONTROL '+json.dumps(self.get_status(self.reactor.monotonic()),sort_keys=True))


def load_config(config):
    return M300PrintControl(config)
