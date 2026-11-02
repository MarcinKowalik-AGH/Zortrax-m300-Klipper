# SPDX-License-Identifier: GPL-3.0-or-later
"""M12 optional classic M300 file-listing and safe snapshot-preview service.

No physical SD SPI implementation, thermal targets, motion or print-start commands.
M04 menu remains owner of operator confirmation. M02 remains sole selector.
"""
import json
from .m300_browser_state import Catalog, BrowserError, SORTS
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
        self.ready = False
        self.last_error = None
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command('ZORTRAX_BROWSER_STATUS', self.cmd_status, when_not_ready=True)
        self.gcode.register_command('ZORTRAX_BROWSER_LIST', self.cmd_list)
        self.gcode.register_command('ZORTRAX_BROWSER_PREVIEW', self.cmd_preview)
        self.printer.register_event_handler('klippy:ready', self._ready)
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, self.invalidate)

    def _ready(self):
        self.ready = True
        self.catalog.invalidate()
        self.preview = None

    def invalidate(self, *args):
        self.ready = False
        self.catalog.invalidate()
        self.preview = None

    def _ensure_ready(self):
        if not self.ready or self.printer.is_shutdown():
            raise BrowserError('M12 host is not ready')

    def _sorted_mode(self):
        mode = self.nvm.get_setting('sort_mode', 'NAME')
        if mode not in SORTS:
            raise BrowserError('unsupported sort mode')
        return mode

    def _entries(self, source, directory):
        self._ensure_ready()
        from .m300_browser_state import directory_parts
        directory_parts(directory)
        if source == 'host':
            return host_entries(self.sd.root, directory, self._sorted_mode())
        if source == 'sd':
            card = self.printer.lookup_object('m300_sd', None)
            if card is None:
                raise BrowserError('physical SD provider not configured')
            return card_entries(card.list_files('/' + directory), self._sorted_mode())
        raise BrowserError('unknown source')

    def list_files(self, source='host', directory=''):
        self._ensure_ready()
        entries = self._entries(source, directory)
        generation = self.catalog.publish(source, directory, entries)
        self.preview = None
        return {'generation': generation, 'source':source, 'directory':directory,
                'files':[dict(name=e.name, path=e.path, directory=e.is_dir,
                              size=e.size, modified=e.mtime) for e in self.catalog.entries]}

    def preview_file(self, generation, index):
        self._ensure_ready()
        source, directory = self.catalog.source, self.catalog.directory
        path = self.catalog.selected(generation, index, self._entries(source, directory))
        # M02 rereads, hashes, validates all commands and owns the immutable fd.
        prepared = self.sd.select(path)
        self.preview = {'filename': prepared.filename, 'identity': prepared.identity,
                        'sha256': prepared.sha256, 'size': prepared.size,
                        'targets': dict(prepared.targets),
                        'binary': bool(getattr(prepared, 'binary_source', False))}
        return dict(self.preview)

    def get_status(self, now):
        return {'stage':'M12', 'model':'M300_CLASSIC','ready':self.ready,
                'catalog_generation':self.catalog.generation,
                'source':self.catalog.source, 'directory':self.catalog.directory,
                'count':len(self.catalog.entries), 'preview':dict(self.preview or {}),
                'owns_motion':False, 'owns_sd_spi':False, 'print_started':False}

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
            result=self.preview_file(gcmd.get_int('GENERATION'),gcmd.get_int('INDEX'))
        except (BrowserError, ValueError, OSError) as exc:
            raise gcmd.error('M12: '+str(exc))
        gcmd.respond_info('ZORTRAX_BROWSER_PREVIEW '+json.dumps(result,sort_keys=True))


def load_config(config):
    return M300Browser(config)
