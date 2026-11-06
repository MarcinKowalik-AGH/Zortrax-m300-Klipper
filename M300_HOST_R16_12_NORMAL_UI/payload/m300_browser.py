# SPDX-License-Identifier: GPL-3.0-or-later
"""M12 optional classic M300 file-listing and safe snapshot-preview service.

No physical SD SPI implementation, thermal targets, motion or print-start commands.
M04 menu remains owner of operator confirmation. M02 remains sole selector.
"""
import json
from .m300_browser_state import Catalog, BrowserError, SORTS, directory_parts
from .m300_menu import host_entries, card_entries

class M300Browser:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        if hasattr(config, 'has_section') and not config.has_section('m300_menu'):
            raise config.error('M12 requires [m300_menu]')
        self.menu = self.printer.load_object(config, 'm300_menu')
        self.job = self.printer.load_object(config, 'm300_job')
        self.sd = self.job.sd
        self.nvm = self.printer.load_object(config, 'm300_nvm')
        self.catalog = Catalog(config.getint('max_entries', 50, minval=1, maxval=50))
        self.preview = None
        self.card_cid = None
        self.ready = False
        self.io_busy = False
        self.session = 0
        self.preview_index = self.preview_generation = None
        self.last_error = None
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command('ZORTRAX_BROWSER_STATUS', self.cmd_status, when_not_ready=True)
        self.gcode.register_command('ZORTRAX_BROWSER_LIST', self.cmd_list)
        self.gcode.register_command('ZORTRAX_BROWSER_PREVIEW', self.cmd_preview)
        self.printer.register_event_handler('klippy:ready', self._ready)
        self.printer.register_event_handler('m300:setting_changed',self._setting_changed)
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self.invalidate)

    def _ready(self):
        self.session += 1
        self.ready = True
        self.catalog.invalidate()
        self.preview = None

    def invalidate(self, *args):
        self.session += 1
        self.ready = False
        self.catalog.invalidate()
        self.preview = None

    def _setting_changed(self,name,value):
        if name=='sort_mode':
            self.catalog.invalidate()
            self.preview=None

    def _ensure_ready(self):
        if not self.ready or self.printer.is_shutdown():
            raise BrowserError('M12 host is not ready')

    def _sorted_mode(self):
        mode = self.nvm.get_setting('sort_mode', 'NAME')
        if mode not in SORTS:
            raise BrowserError('unsupported sort mode')
        return mode

    def _entries(self, source, directory, checkpoint=None):
        self._ensure_ready()
        directory_parts(directory)
        mode=self._sorted_mode()
        if checkpoint is not None:checkpoint()
        if source == 'host':
            entries=self.sd.v_sd.executor.submit(host_entries,self.sd.root,directory,mode)
        elif source == 'sd':
            card = self.printer.lookup_object('m300_sd', None)
            if card is None:
                raise BrowserError('physical SD provider not configured')
            entries = card_entries(card.list_files('/' + directory, checkpoint=checkpoint), mode)
            if not directory:
                entries = [entry for entry in entries if not (
                    entry['is_dir'] and entry['name'].casefold() == 'system volume information')]
        else:raise BrowserError('unknown source')
        self._ensure_ready()
        if mode!=self._sorted_mode():raise BrowserError('sorting changed; refresh the directory')
        if checkpoint is not None:checkpoint()
        return entries

    def list_files(self, source='host', directory='', checkpoint=None):
        self._ensure_ready()
        if self.io_busy:raise BrowserError('browser I/O already in progress')
        self.io_busy=True;session=self.session
        try:
            entries=self._entries(source,directory,checkpoint)
            if session!=self.session:raise BrowserError('browser session changed during listing')
            generation=self.catalog.publish(source,directory,entries)
            card = self.printer.lookup_object('m300_sd', None) if source == 'sd' else None
            self.card_cid = (getattr(card, 'info', None) or {}).get('cid')
            self.preview=None
            if source == 'sd' and not entries:
                from .m300_error_codes import report
                report(self.printer, 'No models on SD card', source='m300_browser', code=101)
            return {'generation': generation, 'source':source, 'directory':directory,
                    'files':[dict(name=e.name, path=e.path, directory=e.is_dir,
                                  size=e.size, modified=e.mtime) for e in self.catalog.entries]}
        finally:self.io_busy=False

    def preview_file(self, generation, index, checkpoint=None):
        self._ensure_ready()
        if self.io_busy:raise BrowserError('browser I/O already in progress')
        self.io_busy=True;session=self.session;prepared=None
        try:
            self.catalog.file_entry(generation, index)
            source,directory=self.catalog.source,self.catalog.directory
            path=self.catalog.selected(generation,index,self._entries(source,directory,checkpoint))
            # Existing M02 preflight owns its immutable checked snapshot, never a print here.
            prepared=self.sd.select(path)
            self._ensure_ready()
            if checkpoint is not None:checkpoint()
            if session!=self.session or generation!=self.catalog.generation:
                raise BrowserError('browser session changed during preview')
            self.preview_index,self.preview_generation=index,generation
            self.preview={'filename':prepared.filename,'identity':prepared.identity,
                'sha256':prepared.sha256,'size':prepared.size,'targets':dict(prepared.targets),
                'binary':bool(getattr(prepared,'binary_source',False))}
            return dict(self.preview)
        except Exception:
            if prepared is not None and self.sd.selected is prepared:self.sd.cancel()
            self.preview=None
            raise
        finally:self.io_busy=False

    def validate_preview(self, prepared):
        self._ensure_ready()
        if (self.io_busy or self.preview is None or prepared is not self.sd.selected
                or prepared.closed or prepared.identity!=self.preview['identity']
                or self.preview_generation!=self.catalog.generation):
            raise BrowserError('preview lease expired; select the file again')
        self.io_busy=True;session=self.session
        try:
            self.catalog.selected(self.preview_generation,self.preview_index,
                self._entries(self.catalog.source,self.catalog.directory))
            if session!=self.session:raise BrowserError('browser session ended during validation')
        finally:self.io_busy=False
        return True

    def get_status(self, now):
        return {'stage':'M12', 'model':'M300_CLASSIC','ready':self.ready,
                'state':'BROWSING' if self.io_busy else 'IDLE','busy':self.io_busy,
                'catalog_generation':self.catalog.generation,
                'source':self.catalog.source, 'directory':self.catalog.directory,
                'count':len(self.catalog.entries), 'preview':dict(self.preview or {}),
                'owns_motion':False, 'owns_sd_spi':False, 'print_started':False}

    def native_preview(self, generation, index):
        self._ensure_ready()
        models = self.printer.lookup_object('m300_models')
        entry = self.catalog.file_entry(generation, index)
        source, cid = self.catalog.source, self.card_cid

        def checkpoint():
            self._ensure_ready()
            self.catalog.file_entry(generation, index)

        return models.prepare(source, entry, cid, checkpoint)

    def cmd_status(self, gcmd):
        gcmd.respond_info('ZORTRAX_BROWSER ' + json.dumps(self.get_status(self.reactor.monotonic()), sort_keys=True))

    def cmd_list(self, gcmd):
        try:
            result=self.list_files(gcmd.get('SOURCE','host').lower(),gcmd.get('PATH',''))
        except (BrowserError, ValueError, OSError) as exc:
            raise gcmd.error('M12: '+str(exc))
        gcmd.respond_info('ZORTRAX_BROWSER '+json.dumps(result,sort_keys=True))

    def cmd_preview(self, gcmd):
        try:
            generation, index = gcmd.get_int('GENERATION'), gcmd.get_int('INDEX')
            models = self.printer.lookup_object('m300_models', None)
            if models is None:
                result = self.preview_file(generation, index)
            else:
                result = self.native_preview(generation, index)
        except (BrowserError, ValueError, OSError) as exc:
            raise gcmd.error('M12: '+str(exc))
        gcmd.respond_info('ZORTRAX_BROWSER_PREVIEW '+json.dumps(result,sort_keys=True))


def load_config(config):
    return M300Browser(config)
