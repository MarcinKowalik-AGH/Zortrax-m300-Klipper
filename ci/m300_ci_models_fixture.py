"""FILEOUTPUT-only harness that starts a prepared file using public commands."""
import json
from pathlib import Path


class ModelsFixture:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.board = self.printer.load_object(config, 'm300_mcu')
        self.sd = self.printer.load_object(config, 'virtual_sdcard')
        self.gcode.register_command('ZORTRAX_CI_RUN_MODEL', self.cmd_run)
        self.printer.register_event_handler('gcode:debuginput_exit', self.report)
        self.replay = config.getboolean('replay', False)
        self.replayed = False
        self.marks = []
        self.gcode.register_command('ZORTRAX_CI_REPLAY_MARK', self.mark)
        self.started = False
        self.resumed = False
        self.mesh=config.getboolean('mesh',False)
        self.soak=config.getboolean('soak',False)
        self.control_phases=[]

    def mark(self, gcmd):
        self.marks.append(gcmd.get('VALUE'))

    def cmd_run(self, gcmd):
        if not self.board.get_mcu().is_fileoutput():
            raise gcmd.error('test fixture requires FILEOUTPUT')
        browser = self.printer.lookup_object('m300_browser')
        models = self.printer.lookup_object('m300_models')
        assert len(browser.catalog.entries) == 1
        if self.replay:
            self.gcode.run_script_from_command('SDCARD_PRINT_FILE FILENAME="Repeat.gcode"')
            assert self.sd.current_file is not None and self.sd.work_timer is not None
            self.started, self.format = True, 'G-code'
            return
        self.gcode.run_script_from_command(
            'ZORTRAX_BROWSER_PREVIEW GENERATION=%d INDEX=0' % browser.catalog.generation)
        assert self.sd.current_file is None and self.sd.work_timer is None
        limit = self.reactor.monotonic() + 10.
        while models.operation is not None and self.reactor.monotonic() < limit:
            self.reactor.pause(self.reactor.monotonic() + .001)
        view = models.get_status(self.reactor.monotonic())
        if view['state'] != 'READY':
            raise gcmd.error('model preparation failed: ' + str(view))
        assert self.sd.current_file is None and self.sd.work_timer is None
        if view['format']=='Z-code' and self.printer.lookup_object('m300_print_control',None) is not None:
            from .m300_ci_print_fixture import prepare, saved_mesh
            prepare(self.printer)
            if self.mesh:saved_mesh(self.printer)
            if self.soak:self.printer.lookup_object('m300_nvm').set_setting('full_platform_preheat',True)
            control=self.printer.lookup_object('m300_print_control')
            previous=control._phase
            def phase(name,seconds=None):
                previous(name,seconds)
                self.control_phases.append(dict(phase=name,start=control.get_status(self.reactor.monotonic())['start']))
            control._phase=phase
        self.gcode.run_script_from_command('ZORTRAX_MODELS_START TOKEN=' + view['token'])
        assert self.sd.current_file is not None and self.sd.work_timer is not None
        self.started = True
        self.format = view['format']

    def report(self):
        if self.sd.work_timer is not None:
            return False
        if self.started:
            control=self.printer.lookup_object('m300_print_control',None)
            if control is not None:
                key=control.state,control.phase
                if key!=getattr(self,'control_debug',None):
                    self.control_debug=key
                    self.gcode.respond_info('M300_CI_PAUSE_PHASE '+str((key,control._drained(self.reactor.monotonic()),self.gcode.get_mutex().test())))
            if control is not None and control.busy:return False
            now = self.reactor.monotonic()
            stats = self.sd.print_stats.get_status(now)
            if stats['state'] == 'paused' and self.format == 'Z-code' and not self.resumed:
                pause = self.printer.lookup_object('pause_resume')
                assert pause.is_paused and self.sd.current_file is not None
                self.resumed = True
                ui = self.printer.lookup_object('m300_print_ui')
                view = ui.view(now)
                assert view[0][1] == 'PAUSED'
                ui._schedule('resume', view[0], lambda: True)
                return False
            if self.replay and not self.replayed:
                ui = self.printer.lookup_object('m300_print_ui')
                toolhead = self.printer.lookup_object('toolhead')
                check_busy = toolhead.check_busy
                queued, _, empty = check_busy(now)
                assert empty and self.marks == ['ORIGINAL']
                # FILEOUTPUT's MCU estimated clock is zero. This fixture has
                # no motion. Model only the estimated clock crossing EOF.
                toolhead.check_busy = lambda eventtime: (queued, queued, True)
                view = ui.view(now)
                assert view[0][1] == 'DONE' and view[1]
                path = Path(self.sd.sdcard_dirname) / 'Repeat.gcode'
                path.write_text('ZORTRAX_CI_REPLAY_MARK VALUE=EDITED\n')
                self.replayed = True
                command = 'ZORTRAX_REPRINT_CONFIRM TOKEN=' + view[1]

                def replay(eventtime):
                    try:
                        self.gcode.run_script(command)
                    finally:
                        toolhead.check_busy = check_busy

                self.reactor.register_callback(replay)
                return False
            self.started = False
            heaters = self.printer.lookup_object('heaters')
            targets = [heaters.lookup_heater(name).get_temp(now)[1]
                       for name in ('extruder', 'heater_bed')]
            toolhead = self.printer.lookup_object('toolhead')
            self.gcode.respond_info('M300_CI_MODELS ' + json.dumps(dict(
                state=stats['state'], filename=stats['filename'], format=self.format,
                file_consumed=self.sd.current_file is None, targets=targets,
                explicit_resume=self.resumed, explicit_reprint=self.replayed,
                control_phases=self.control_phases,
                replay_marks=self.marks,
                position=list(toolhead.get_position()))))
        return True


def load_config(config):
    return ModelsFixture(config)
