# SPDX-License-Identifier: GPL-3.0-or-later
"""Session-only native motion/heater ownership for OEM manual services.

No MCU transport or geometry overrides. Idle native command handlers are
restored exactly; each permitted move belongs to the current token/phase.
"""
import math


def native_temperature_ready(measured, target, requested, heater):
    """OEM hotend readiness uses a lower threshold, not a symmetric band."""
    return (type(measured) in (int,float) and math.isfinite(measured)
            and type(requested) in (int,float) and math.isfinite(requested)
            and target == requested
            and max(heater.min_extrude_temp,requested-2.) <= measured <= heater.max_temp)

BLOCKED = ('G0','G1','G28','G90','G91','G92','M18','M84','M82','M83','M204','M220','M221',
           'SAVE_GCODE_STATE','RESTORE_GCODE_STATE','SET_GCODE_OFFSET',
           'SET_KINEMATIC_POSITION','FORCE_MOVE','STEPPER_BUZZ','SET_VELOCITY_LIMIT',
           'PROBE','PROBE_ACCURACY','PROBE_CALIBRATE','BED_MESH_CALIBRATE',
           'BED_MESH_CLEAR','BED_MESH_PROFILE','BED_MESH_OFFSET',
           'SCREWS_TILT_CALCULATE','Z_TILT_ADJUST','QUAD_GANTRY_LEVEL',
           'PID_CALIBRATE','M109','M190','TEMPERATURE_WAIT','SAVE_CONFIG',
           'SET_EXTRUDER_ROTATION_DISTANCE','SYNC_EXTRUDER_MOTION',
           'SET_PRESSURE_ADVANCE','SDCARD_PRINT_FILE','M23','M24','PAUSE','RESUME','CLEAR_PAUSE')


def require_idle_print(printer, now):
    control=printer.lookup_object('m300_print_control',None)
    if control is not None and control.busy:
        raise printer.command_error('M300 print preparation owns motion')
    stats = printer.lookup_object('print_stats', None)
    sd = printer.lookup_object('virtual_sdcard', None)
    if (getattr(sd, 'work_timer', None) is not None
            or stats is not None and stats.get_status(now).get('state') in ('printing', 'paused')):
        raise printer.command_error('OEM service requires an idle native print')
    pad_mesh = printer.lookup_object('m300_pad_mesh', None)
    if pad_mesh is not None and pad_mesh.busy:
        raise printer.command_error('M300 pad mesh owns motion')


def native_service_frame(printer, gcode_move, toolhead, *, paused_extrusion=False):
    transform = gcode_move.move_transform
    if transform in (None, toolhead):
        return True
    pad_mesh = printer.lookup_object('m300_pad_mesh', None)
    bedmesh = printer.lookup_object('bed_mesh',None)
    if bedmesh is None and pad_mesh is not None:bedmesh=pad_mesh.bedmesh
    return (bedmesh is not None and transform is bedmesh
            and (paused_extrusion or transform.get_mesh() is None))


def lock_command(gcode,name,wrapper):
    # The pinned native dispatcher wraps extended command callbacks. Save the
    # installed dispatch function, not the unwrapped callback passed to it.
    # Restoring through register_command would wrap it a second time and an
    # equality check against `wrapper` would retain a permanent stale lock.
    ready=getattr(gcode,'ready_gcode_handlers',None)
    base=getattr(gcode,'base_gcode_handlers',None)
    previous_base=base.get(name) if isinstance(base,dict) else None
    original=gcode.register_command(name,None)
    if original is None:
        return None
    gcode.register_command(name,wrapper)
    installed=ready[name] if isinstance(ready,dict) else wrapper
    return name,original,installed,previous_base


def unlock_command(gcode,record):
    name,original,installed,previous_base=record
    ready=getattr(gcode,'ready_gcode_handlers',None)
    if isinstance(ready,dict):
        if ready.get(name) is not installed:
            return
        ready[name]=original
        base=gcode.base_gcode_handlers
        if previous_base is None:base.pop(name,None)
        else:base[name]=previous_base
        gcode._build_status_commands()
    else:
        current=gcode.register_command(name,None)
        gcode.register_command(name,original if current==installed else current)


class NativeServiceLease:
    def __init__(self, owner, identity, guard_move, cancel):
        self.owner,self.printer,self.gcode=owner,owner.printer,owner.gcode
        self.identity,self.guard_move,self.cancel=identity,guard_move,cancel
        self.methods,self.commands=[],[]
        self.move_permit=self.heat_permit=None

    def _own(self,obj,name,replacement):
        self.methods.append((obj,name,getattr(obj,name),replacement))
        setattr(obj,name,replacement)

    def acquire(self,toolhead,gcode_move,heaters,*,extra_commands=()):
        if self.methods:
            raise self.printer.command_error('OEM native service lease already active')
        self.toolhead,self.gcode_move=toolhead,gcode_move
        self.old_parser=gcode_move.move_with_transform
        original=toolhead.move
        def move(position,speed):
            permit,self.move_permit=self.move_permit,None
            if permit != (self.identity(),list(position),speed):
                raise self.printer.command_error('OEM service owns motion; external move refused')
            self.guard_move()
            return original(position,speed)
        self._own(toolhead,'move',move)
        if self.old_parser == original:
            gcode_move.move_with_transform=move
        self.parser_move=move
        for name in ('drip_move','set_position'):
            def locked(*args,name=name,**kwargs):
                raise self.printer.command_error('OEM service owns position; '+name+' refused')
            self._own(toolhead,name,locked)
        for heater in heaters:
            original_heat=heater.set_temp
            def heat(value,heater=heater,original_heat=original_heat):
                permit,self.heat_permit=self.heat_permit,None
                if not (permit and permit[0] is heater and permit[1:]==(self.identity(),value)):
                    if value != 0.:
                        raise self.printer.command_error('OEM service owns heaters')
                    self.cancel('external heater-off')
                return original_heat(value)
            self._own(heater,'set_temp',heat)
        for name in (*BLOCKED, *extra_commands):
            def locked_command(gcmd,name=name):
                raise self.printer.command_error('OEM service owns resources; '+name+' refused')
            record=lock_command(self.gcode,name,locked_command)
            if record is not None:self.commands.append(record)

    def move(self,position,speed,extruder_only=False):
        self.move_permit=(self.identity(),list(position),speed)
        try:
            if extruder_only:
                return self.toolhead.manual_move([None,None,None,position[3]],speed)
            return self.toolhead.manual_move(list(position),speed)
        finally:
            self.move_permit=None

    def heat(self,heater,target):
        self.heat_permit=(heater,self.identity(),target)
        try:
            return heater.set_temp(target)
        finally:
            self.heat_permit=None

    def release(self):
        for record in reversed(self.commands):
            unlock_command(self.gcode,record)
        self.commands.clear()
        for obj,name,original,wrapper in reversed(self.methods):
            if getattr(obj,name)==wrapper:
                setattr(obj,name,original)
        if self.methods and self.gcode_move.move_with_transform==self.parser_move:
            self.gcode_move.move_with_transform=self.old_parser
        self.methods.clear()
        self.move_permit=self.heat_permit=None
