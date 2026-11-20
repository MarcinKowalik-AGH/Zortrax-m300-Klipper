# Marcin Kowalik <mkowalik@agh.edu.pl>
# m300_ci_print_fixture.py - Dostarcza kontrolowane warunki do prób startu, pauzy i zakończenia wydruku.
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


def saved_mesh(printer):
    mesh=printer.lookup_object('bed_mesh')
    mesh.pmgr.profiles['m300_pads']=dict(points=[[.10,.12,.14],[.12,.14,.16],[.14,.16,.18]],
        mesh_params=dict(min_x=0.,max_x=300.,min_y=0.,max_y=305.,x_count=3,y_count=3,
            mesh_x_pps=2,mesh_y_pps=2,algo='lagrange',tension=.2))


class PrintFixture:
    def __init__(self,config):
        self.printer=config.get_printer();self.reactor=self.printer.get_reactor()
        self.gcode=self.printer.lookup_object('gcode')
        self.mode=config.get('mode','lifecycle')
        self.running=False;self.marks=[];self.actions=[]
        self.refusals = []
        self.jogged = set()
        self.flow_steps = iter([
            (False, 'FILAMENT_READY'), (True, -30), (False, 'RESUME'),
            (False, 30), (False, 'FILAMENT_READY'), (True, 'RESUME'),
        ])
        self.second_job = False
        self.mark_positions = {}
        self.pause_positions = {}
        self.timer=self.reactor.register_timer(self.tick)
        self.gcode.register_command('ZORTRAX_CI_PRINT_RUN',self.run)
        self.gcode.register_command('ZORTRAX_CI_PRINT_PREPARE',lambda gcmd:prepare(self.printer))
        self.gcode.register_command('ZORTRAX_CI_PRINT_MARK',self.mark)
        self.printer.register_event_handler('gcode:debuginput_exit',self.report)

    def mark(self,gcmd):
        name = gcmd.get('VALUE')
        self.marks.append(name)
        self.mark_positions[name] = self.printer.lookup_object('toolhead').get_position()[:3]

        if self.mode == 'file_guards' and name == 'MODEL':
            assert self.printer.lookup_object('m300_models').runtime_deposited
            self.reactor.register_callback(self.external_guards)
        if self.mode == 'file_guards' and name == 'TRAILER':
            assert self.sd.is_cmd_from_sd()
            for command in ('G0 X80', 'G1 X80'):
                self.expect_refusal(self.gcode.run_script_from_command, command, 'follows END_PRINT')

    def expect_refusal(self, dispatch, command, reason):
        toolhead = self.printer.lookup_object('toolhead')
        heaters = self.printer.lookup_object('heaters')
        def snapshot():
            return (self.sd.current_file, self.sd.file_position, self.control.state,
                    tuple(toolhead.get_position()), tuple(heaters.lookup_heater(name).target_temp
                                                          for name in ('extruder','heater_bed')))
        before = snapshot()
        # Debug-input mode otherwise exits Klippy on every rejected command.
        # Use live-console error reporting only for this expected rejection.
        fileinput = self.gcode.is_fileinput
        self.gcode.is_fileinput = False
        try:
            dispatch(command)
        except self.printer.command_error as exc:
            assert reason in str(exc), (command, exc)
        else:
            raise AssertionError(f'Unexpectedly accepted {command}')
        finally:
            self.gcode.is_fileinput = fileinput
        assert snapshot() == before, command
        self.refusals.append(command.split()[0])

    def external_guards(self, now):
        assert self.sd.is_active() and not self.sd.is_cmd_from_sd()
        for command in ('G28', 'ZORTRAX_HOME', 'START_PRINT EXTRUDER_TEMP=220 BED_TEMP=60', 'END_PRINT'):
            self.expect_refusal(self.gcode.run_script, command, 'must come from the active print file')

    def run(self,gcmd):
        prepare(self.printer)
        self.control=self.printer.lookup_object('m300_print_control')
        self.sd=self.printer.lookup_object('virtual_sdcard')
        self.filament=self.printer.lookup_object('m300_filament')
        # An actual native saved profile, with nonzero compensation at purge.
        saved_mesh(self.printer)
        if self.mode=='cancel_soak':
            self.printer.lookup_object('m300_nvm').set_setting('full_platform_preheat',True)
        path=Path(self.sd.sdcard_dirname)/'Print lifecycle.gcode'
        script=('START_PRINT EXTRUDER_TEMP=220 BED_TEMP=60\n'
                'G90\nG1 X100 Y100 Z10 F6000\n'
                'ZORTRAX_CI_PRINT_MARK VALUE=STARTED\nPAUSE\n'
                'ZORTRAX_CI_PRINT_MARK VALUE=RESUMED\n'
                'M600\nZORTRAX_CI_PRINT_MARK VALUE=CHANGED\n'
                'G1 X120 Y120 F6000\nEND_PRINT\n'
                'ZORTRAX_CI_PRINT_MARK VALUE=ENDED\n')
        if self.mode in ('file_guards', 'high_m600'):
            height = 298 if self.mode == 'high_m600' else 10
            script = (f'START_PRINT EXTRUDER_TEMP=220 BED_TEMP=60\nG90\nG1 X100 Y100 Z{height} F6000\n'
                      'M83\nG1 X101 E0.2 F600\nG1 X100 F600\nZORTRAX_CI_PRINT_MARK VALUE=MODEL\n')
            if self.mode == 'file_guards':
                # Crossing a native SD read block yields to a genuine external command.
                script += '; allow the native file reader to yield\n' * 600
                (path.parent/'Next.gcode').write_text(
                    'START_PRINT EXTRUDER_TEMP=220 BED_TEMP=60\nG1 X130 Y120 F6000\n'
                    'ZORTRAX_CI_PRINT_MARK VALUE=NEXT\nEND_PRINT\n')
            else:
                script += 'M600\nZORTRAX_CI_PRINT_MARK VALUE=RESUMED\n'
            script += 'END_PRINT\nZORTRAX_CI_PRINT_MARK VALUE=TRAILER\n'
        path.write_text(script)
        self.running=True;self.pending=None
        self.gcode.run_script_from_command('SDCARD_PRINT_FILE FILENAME="Print lifecycle.gcode"')
        self.reactor.update_timer(self.timer,self.reactor.NOW)

    def _submit(self,script,*,manual_e=None):
        if self.pending:return
        self.pending=script
        def run(now):
            try:
                if manual_e is not None:
                    toolhead = self.printer.lookup_object('toolhead')
                    move = self.printer.lookup_object('gcode_move')
                    xyz_e = toolhead.get_position()[:]
                    logical_e = move.get_status(now)['gcode_position'].e
                self.actions.append(script);self.gcode.run_script(script)
                if manual_e is not None:
                    end = toolhead.get_position()
                    assert xyz_e[:3] == end[:3] and abs(end[3]-xyz_e[3]-manual_e)<1.e-6
                    assert abs(move.get_status(now)['gcode_position'].e-logical_e)<1.e-6
                    assert self.control.state == 'PAUSED' and self.sd.work_timer is None
            finally:self.pending=None
        self.reactor.register_callback(run)

    def _jog(self, distance):
        self._submit('SAVE_GCODE_STATE NAME=_ui_retract\nM83\nG1 E%d F240\n'
                     'RESTORE_GCODE_STATE NAME=_ui_retract' % distance, manual_e=distance)

    def tick(self,now):
        if not self.running:return self.reactor.NEVER
        c=self.control
        key=(c.state,c.phase,self.filament.machine.state)
        if key!=getattr(self,'last_phase',None):
            self.last_phase=key
            self.gcode.respond_info('M300_CI_PRINT_PHASE '+str(key))
            if c.state == 'PAUSED' and c.phase == 'PAUSED' and self.marks:
                position = self.printer.lookup_object('toolhead').get_position()[:3]
                self.pause_positions.setdefault(self.marks[-1], position)
                if self.mode == 'high_m600':
                    assert c.context and not c.context['invalid'] and not c.context['change_required']
                    assert 'Resume remains available' in c.notice and not self.filament.is_busy()
                    heaters = self.printer.lookup_object('heaters')
                    assert [heaters.lookup_heater(n).target_temp for n in ('extruder','heater_bed')] == [220.,60.]
                    assert self.printer.lookup_object('m300_maintenance').status_led_rgb(now) == (1,0,1)
        if self.mode=='cancel_soak' and c.phase=='PLATFORM_SOAK':
            self._submit('CANCEL_PRINT')
        elif self.mode=='cancel' and c.state=='PAUSED':
            self._submit('CANCEL_PRINT')
        elif c.state=='PAUSED' and not self.filament.is_busy():
            ctx=c.context
            stage = 'change' if ctx['change_required'] else 'pause'
            if self.pending:
                return now+.05
            if (self.mode == 'lifecycle' and stage not in self.jogged
                    and (stage == 'pause' or ctx['material_success'])):
                self.jogged.add(stage)
                self._jog(30 if stage == 'change' else -30)
            elif ctx['change_required']:
                if ctx['material_success']:
                    confirmed, action = next(self.flow_steps)
                    assert ctx['flow_confirmed'] == confirmed and self.sd.work_timer is None
                    if isinstance(action, int):
                        self._jog(action)
                    else:
                        self._submit(action)
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
        if self.mode == 'file_guards' and stats['state'] == 'complete' and 'NEXT' not in self.marks:
            if not self.second_job:
                self.second_job = True
                self._submit('SDCARD_PRINT_FILE FILENAME="Next.gcode"')
            return False
        self.running=False;self.reactor.update_timer(self.timer,self.reactor.NEVER)
        heaters=self.printer.lookup_object('heaters')
        result=dict(mode=self.mode,refusals=self.refusals,state=stats['state'],marks=self.marks,actions=self.actions,
            mark_positions=self.mark_positions,pause_positions=self.pause_positions,
            position=self.printer.lookup_object('toolhead').get_position(),
            targets=[heaters.lookup_heater(n).target_temp for n in ('extruder','heater_bed')],
            control=self.control.get_status(self.reactor.monotonic()),
            file_consumed=self.sd.current_file is None,physical_hardware=False)
        self.gcode.respond_info('M300_CI_PRINT '+json.dumps(result))
        return True


def load_config(config):return PrintFixture(config)
