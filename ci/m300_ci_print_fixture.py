"""Real native SD/parser/planner integration, strictly FILEOUTPUT only.

No physical thermal/drain proof: heater readings and the estimated MCU clock
are modeled explicitly. Native homing, transforms, leases, SD worker, pause
state and the existing material state machine run in the actual Klippy process.
"""
import json
from pathlib import Path


def prepare(printer):
    board=printer.lookup_object('m300_mcu')
    if not board.get_mcu().is_fileoutput():
        raise printer.command_error('CI print fixture requires FILEOUTPUT')
    board.require_motion=lambda:None
    board.require_heating=lambda:None
    toolhead=printer.lookup_object('toolhead')
    oled=printer.lookup_object('m300_oled',None)
    if oled is not None:oled._stop('disabled','FILEOUTPUT has no physical OLED ACKs')
    check_busy=toolhead.check_busy
    def drained(now):
        toolhead.get_last_move_time()  # Flush native lookahead into FILEOUTPUT.
        queued,_,empty=check_busy(now)
        return queued,queued,empty
    toolhead.check_busy=drained
    heaters=printer.lookup_object('heaters')
    for name in ('extruder','heater_bed'):
        heater=heaters.lookup_heater(name)
        heater.get_temp=lambda now,h=heater:(h.target_temp if h.target_temp else 25.,h.target_temp)
        heater.can_extrude=True
    # There is no physical native ADC sample in FILEOUTPUT. Keep this
    # modeled temperature boundary inside the explicitly gated fixture.
    printer.lookup_object('m300_job')._temperature=lambda name,heater,now:heater.get_temp(now)


class PrintFixture:
    def __init__(self,config):
        self.printer=config.get_printer();self.reactor=self.printer.get_reactor()
        self.gcode=self.printer.lookup_object('gcode')
        self.mode=config.get('mode','lifecycle')
        self.running=False;self.marks=[];self.actions=[];self.flow=False
        self.timer=self.reactor.register_timer(self.tick)
        self.gcode.register_command('ZORTRAX_CI_PRINT_RUN',self.run)
        self.gcode.register_command('ZORTRAX_CI_PRINT_MARK',self.mark)
        self.printer.register_event_handler('gcode:debuginput_exit',self.report)

    def mark(self,gcmd):self.marks.append(gcmd.get('VALUE'))

    def run(self,gcmd):
        prepare(self.printer)
        self.control=self.printer.lookup_object('m300_print_control')
        self.sd=self.printer.lookup_object('virtual_sdcard')
        self.filament=self.printer.lookup_object('m300_filament')
        # An actual native saved profile, with nonzero compensation at purge.
        mesh=self.printer.lookup_object('bed_mesh')
        mesh.pmgr.profiles['m300_pads']=dict(points=[[.10,.12,.14],[.12,.14,.16],[.14,.16,.18]],
            mesh_params=dict(min_x=0.,max_x=300.,min_y=0.,max_y=305.,x_count=3,y_count=3,
                mesh_x_pps=2,mesh_y_pps=2,algo='lagrange',tension=.2))
        path=Path(self.sd.sdcard_dirname)/'Print lifecycle.gcode'
        script=('START_PRINT EXTRUDER_TEMP=220 BED_TEMP=60\n'
                'G90\nG1 X100 Y100 Z10 F6000\n'
                'ZORTRAX_CI_PRINT_MARK VALUE=STARTED\nPAUSE\n'
                'ZORTRAX_CI_PRINT_MARK VALUE=RESUMED\n'
                'M600\nZORTRAX_CI_PRINT_MARK VALUE=CHANGED\n'
                'G1 X120 Y120 F6000\nEND_PRINT\n'
                'ZORTRAX_CI_PRINT_MARK VALUE=ENDED\n')
        path.write_text(script)
        self.running=True;self.pending=None
        self.gcode.run_script_from_command('SDCARD_PRINT_FILE FILENAME="Print lifecycle.gcode"')
        self.reactor.update_timer(self.timer,self.reactor.NOW)

    def _submit(self,script):
        if self.pending:return
        self.pending=script
        def run(now):
            try:
                self.actions.append(script);self.gcode.run_script(script)
            finally:self.pending=None
        self.reactor.register_callback(run)

    def tick(self,now):
        if not self.running:return self.reactor.NEVER
        c=self.control
        key=(c.state,c.phase,self.filament.machine.state)
        if key!=getattr(self,'last_phase',None):
            self.last_phase=key
            self.gcode.respond_info('M300_CI_PRINT_PHASE '+str(key))
        if self.mode=='cancel' and c.state=='PAUSED':
            self._submit('CANCEL_PRINT')
        elif c.state=='PAUSED' and not self.filament.is_busy():
            ctx=c.context
            if ctx['change_required']:
                if ctx['material_success']:
                    if not self.flow:
                        self.flow=True;self._submit('FILAMENT_READY')
                    else:self._submit('RESUME')
            else:self._submit('RESUME')
        elif self.filament.is_busy():
            status=self.filament.get_status(now)
            if status.get('can_confirm'):
                self._submit('FILAMENT_CONFIRM TOKEN=%d PHASE=%d' %
                             (status['session_token'],status['phase_id']))
        return now+.05

    def report(self):
        if not self.running:return True
        if self.sd.work_timer is not None or self.control.busy or self.filament.is_busy():return False
        stats=self.sd.print_stats.get_status(self.reactor.monotonic())
        if stats['state']=='paused':return False
        self.running=False;self.reactor.update_timer(self.timer,self.reactor.NEVER)
        heaters=self.printer.lookup_object('heaters')
        result=dict(mode=self.mode,state=stats['state'],marks=self.marks,actions=self.actions,
            position=self.printer.lookup_object('toolhead').get_position(),
            targets=[heaters.lookup_heater(n).target_temp for n in ('extruder','heater_bed')],
            control=self.control.get_status(self.reactor.monotonic()),
            file_consumed=self.sd.current_file is None,physical_hardware=False)
        self.gcode.respond_info('M300_CI_PRINT '+json.dumps(result))
        return True


def load_config(config):return PrintFixture(config)
