# SPDX-License-Identifier: GPL-3.0-or-later
"""M11 optional classic M300 menu/translation/encoder display policy.

The existing m300_oled is the sole MCU, SPI2, encoder and ACK owner. M11
manages only page history, status, visible labels and stock catalog navigation.
All physical actions still execute through M300Menu's existing owners.
"""
import json
import math
import os

from .m300_ui_m11_state import MenuHistory, LANGS, atlas_summary, require_rows, clean_label
from .m300_oem_graphics import OEMGraphics, choose_icon
from .m300_ui_labels import english_label


class M300MenuUI:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        if hasattr(config, 'has_section') and not config.has_section('m300_menu'):
            raise config.error('M11 requires [m300_menu]')
        self.menu = self.printer.load_object(config, 'm300_menu')
        self.oled = self.printer.load_object(config, 'm300_oled')
        self.nvm = self.printer.load_object(config, 'm300_nvm')
        self.procedures = self.printer.load_object(config, 'm300_procedures')
        self.fans = self.printer.load_object(config, 'm300_fans')
        self.menu_max_depth = config.getint('history_depth', 10, minval=1, maxval=16)
        self.scroll_delay = config.getfloat('scroll_delay', 1.25, minval=.25,maxval=10.)
        self.scroll_interval = config.getfloat('scroll_interval', .20,minval=.10,maxval=2.)
        self.row_pixels = config.getint('row_pixels', 216,minval=60,maxval=228)
        self.oem_graphics_enabled = config.getboolean('oem_graphics', True)
        self.oem_sprites = OEMGraphics() if self.oem_graphics_enabled else None
        self.last_sprite = None
        self.history = MenuHistory(self.menu_max_depth)
        path = os.path.join(os.path.dirname(__file__), 'm300_m11_stock_atlas.json')
        with open(path,encoding='utf-8') as stream:
            self.atlas = json.load(stream)['stock_structures']
        self.parity = atlas_summary(self.atlas)
        self.index = {entry['ram_address']:entry for entry in self.atlas}
        self.last_audit = {'row_count':0, 'actionable':0,
                           'informational_or_disabled':0,'all_actions_known':True}
        self._present_generation = None
        self._status_cached = None
        for event in ('klippy:shutdown','klippy:disconnect','gcode:request_restart'):
            self.printer.register_event_handler(event, self.invalidate)
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('ZORTRAX_UI_STATUS',self.cmd_status,when_not_ready=True)
        gcode.register_command('ZORTRAX_UI_HOME',self.cmd_home)

    def invalidate(self, *args):
        self.history.clear()
        self._present_generation = None

    def entered(self, old, new, remember=True):
        self.history.entered(old, new, remember)

    def parent(self, current):
        return self.history.parent(current)

    def language(self):
        value = str(self.nvm.get_setting('language', 'EN')).upper()
        return value if value in LANGS else 'EN'

    def translate(self, name):
        return self.history.translate(name,self.language(),self.menu._labels)

    def _present_labels(self, title, rows, selected, now, page, generation, row_pixels):
        labels = [clean_label(label) for label, _ in rows]
        if self.language() == 'EN':
            labels = [english_label(label) for label in labels]
            if labels and labels[0] == 'Up':
                labels[0] = 'Back'
        width = self.row_pixels if row_pixels is None else min(self.row_pixels, row_pixels)
        return clean_label(title), self.history.present(
            page,generation,selected,now,labels,width,self.scroll_interval,self.scroll_delay)

    def present(self, title, rows, selected, now, page, generation, row_pixels=None):
        self.last_audit = self.history.check(rows)
        return self._present_labels(title,rows,selected,now,page,generation,row_pixels)

    def present_panel(self, title, rows, selected, now, page, row_pixels=None):
        # Panel actions remain private to m300_oled. No translation changes an
        # action, token, phase or index; the same bounded marquee is shared.
        return self._present_labels(title,rows,selected,now,'panel:'+page,0,row_pixels)

    def get_oem_sprite(self, panel_page, rows, selected, now):
        if self.oem_sprites is None:
            self.last_sprite = None
            return None
        menu_page = self.menu.page if panel_page in ('home','m04') else ''
        if menu_page == 'procedure':
            owner = self.procedures.view(now)['owner']
            if owner == 'm300_calibration':
                menu_page = 'calibration'
            elif owner == 'm300_filament':
                panel_page = 'filament'
            elif owner == 'm300_job':
                panel_page = 'job'
        def snapshot(name):
            service = self.printer.lookup_object(name, None)
            if service is None:
                return {}
            try:
                result = service.get_status(now)
                return result if isinstance(result, dict) else {}
            except Exception:
                return {}  # Drawing never attempts owner recovery.
        self.last_sprite = choose_icon(menu_page=menu_page, panel_page=panel_page,
            rows=rows, selected=selected,
            calibration=snapshot('m300_calibration') if menu_page=='calibration' else {},
            filament=snapshot('m300_filament') if (panel_page.startswith('filament')
                or menu_page=='material_status') else {},
            job=snapshot('m300_job') if panel_page.startswith('job') else {})
        return self.oem_sprites.get(self.last_sprite, now)

    def list_atlas(self):
        return [(self.translate(entry['source_en']) or '(unnamed)',
                 ('atlas_item',entry['ram_address'])) for entry in self.atlas]

    def item(self, address):
        return self.index.get(address)

    def get_status(self, now):
        return {'stage':'M11','model':'M300_CLASSIC','installed':True,
                'hardware_qualified':False,
                'languages':list(LANGS),'language':self.language(),
                'history_depth':len(self.history.stack),
                'history_limit':self.menu_max_depth,
                'stock_structure_count':len(self.atlas),
                'stock_structure_classifications':dict(self.parity),
                'menu_generation':self.menu.generation,
                'presentation':dict(self.last_audit),
                'oled_spi_owner':'m300_oled',
                'encoder_owner':'m300_oled',
                'action_owner':'m300_menu_and_existing_services',
                'host_ui_revision':'0.13.16-M300-NORMAL-UI',
                'operation_groups':['Klipper', 'Zortrax M300', 'Service / Tests'],
                'menu_wrap':False,
                'menu_reverse':self.oled.menu_reverse,
                'procedure_view':'m300_procedures',
                'oem_graphics_enabled':self.oem_graphics_enabled,
                'oem_sprite_count':len(self.oem_sprites.frames) if self.oem_sprites else 0,
                'oem_frame_cache':len(self.oem_sprites.cache) if self.oem_sprites else 0,
                'oem_descriptor':self.last_sprite}

    def cmd_status(self,gcmd):
        gcmd.respond_info('ZORTRAX_UI '+json.dumps(self.get_status(self.reactor.monotonic()),sort_keys=True))

    def cmd_home(self,gcmd):
        self.menu.home()
        self.oled.page,self.oled.selection,self.oled.render_at='m04',0,0.


def load_config(config):
    return M300MenuUI(config)
