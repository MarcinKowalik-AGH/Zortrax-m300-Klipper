"""FILEOUTPUT-only harness that starts a prepared file using public commands."""
import json


class ModelsFixture:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.board = self.printer.load_object(config, 'm300_mcu')
        self.sd = self.printer.load_object(config, 'virtual_sdcard')
        self.gcode.register_command('ZORTRAX_CI_RUN_MODEL', self.cmd_run)
        self.printer.register_event_handler('gcode:debuginput_exit', self.report)
        self.started = False
        self.resumed = False

    def cmd_run(self, gcmd):
        if not self.board.get_mcu().is_fileoutput():
            raise gcmd.error('test fixture requires FILEOUTPUT')
        browser = self.printer.lookup_object('m300_browser')
        models = self.printer.lookup_object('m300_models')
        assert len(browser.catalog.entries) == 1
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
        self.gcode.run_script_from_command('ZORTRAX_MODELS_START TOKEN=' + view['token'])
        assert self.sd.current_file is not None and self.sd.work_timer is not None
        self.started = True
        self.format = view['format']

    def report(self):
        if self.sd.work_timer is not None:
            return False
        if self.started:
            now = self.reactor.monotonic()
            stats = self.sd.print_stats.get_status(now)
            if stats['state'] == 'paused' and self.format == 'Z-code' and not self.resumed:
                pause = self.printer.lookup_object('pause_resume')
                assert pause.is_paused and self.sd.current_file is not None
                self.resumed = True
                self.reactor.register_callback(lambda eventtime: self.gcode.run_script('RESUME'))
                return False
            self.started = False
            heaters = self.printer.lookup_object('heaters')
            targets = [heaters.lookup_heater(name).get_temp(now)[1]
                       for name in ('extruder', 'heater_bed')]
            toolhead = self.printer.lookup_object('toolhead')
            self.gcode.respond_info('M300_CI_MODELS ' + json.dumps(dict(
                state=stats['state'], filename=stats['filename'], format=self.format,
                file_consumed=self.sd.current_file is None, targets=targets,
                explicit_resume=self.resumed,
                position=list(toolhead.get_position()))))
        return True


def load_config(config):
    return ModelsFixture(config)
