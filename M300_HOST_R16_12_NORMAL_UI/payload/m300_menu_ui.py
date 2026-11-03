# SPDX-License-Identifier: GPL-3.0-or-later
"""M11 optional classic M300 menu/translation/encoder display policy.

The existing m300_oled is the sole MCU, SPI2, encoder and ACK owner. M11
manages only page history, status, visible labels and stock catalog navigation.
All physical actions still execute through M300Menu's existing owners.
"""
import json
import math
import os
from collections import deque

from .m300_ui_m11_state import MenuHistory, LANGS, atlas_summary, require_rows, clean_label
from .m300_oem_graphics import OEMGraphics, choose_icon
from .m300_ui_labels import english_label
from .m300_leveling_oem import render as render_leveling
from .m300_maintenance_ui import FAN_LABELS, fan_frame
from .m300_settings import PAGES as SETTINGS_PAGES
from .m300_settings_ui import menu_frame


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
        self._leveling_frames = deque(maxlen=16)
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
        self._leveling_frames.clear()

    def entered(self, old, new, remember=True):
        self.history.entered(old, new, remember)

    def parent(self, current):
        return self.history.parent(current)

    def language(self):
        return 'EN'

    def translate(self, name):
        return self.history.translate(name,self.language(),self.menu._labels)

    def _present_labels(self, title, rows, selected, now, page, generation, row_pixels):
        labels = [clean_label(label) for label, _ in rows]
        if self.language() == 'EN':
            labels = [english_label(label) for label in labels]
            if labels and labels[0] == 'Up':
                labels[0] = 'Back'
        width = self.row_pixels if row_pixels is None else min(self.row_pixels, row_pixels)
        return clean_label(english_label(title)), self.history.present(
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

    def leveling_frame(self, panel_page, now, frame_type):
        if panel_page != 'm04' or self.menu.page != 'procedure':
            self._leveling_frames.clear()
            return None
        view = self.procedures.view(now)
        if not view.get('leveling_screen'):
            self._leveling_frames.clear()
            return None
        screen = view['leveling_screen']
        self.last_sprite = screen['sprite']
        wire = render_leveling(screen, self.oem_sprites, frame_type, now)
        # Keep all recent animation frames of this phase. An acknowledged
        # frame, not a render request, establishes the visible action identity.
        if self._leveling_frames and self._leveling_frames[-1][0] != view['view_id']:
            self._leveling_frames.clear()
        self._leveling_frames.append((view['view_id'], wire))
        return wire

    def leveling_receipt(self, stream):
        if not stream.enabled or not stream.ready:
            return None
        previous = getattr(stream, 'previous', None)
        return next((view for view, frame in reversed(self._leveling_frames)
                     if frame == previous), None)

    def maintenance_frame(self, panel_page, rows, selected, frame_type, labels=None, sprite=None):
        if panel_page != 'm04':
            return None
        if self.menu.page in SETTINGS_PAGES:
            settings = self.printer.lookup_object('m300_settings', None)
            if settings is not None:
                return menu_frame(tuple(labels or [r[0] for r in rows]),
                    settings.active_rows(self.menu.page), selected, frame_type, sprite)
        if self.menu.page != 'fan_test' or len(rows) != 3:return None
        upper=rows[1][0][len(FAN_LABELS[1])+1:]
        lower=rows[2][0][len(FAN_LABELS[2])+1:]
        note='Automatic upper-fan cooling' if upper=='(Cooling)' else ''
        return fan_frame(upper,lower,note,selected,frame_type)

    def leveling_panel(self, events, received_view, now):
        if self.oled.page != 'm04' or self.menu.page != 'procedure':
            return False
        view = self.procedures.view(now)
        if not view.get('leveling_screen'):
            return False
        # Consume rotation and stale/coalesced clicks in this modal dialog.
        # The short press confirms precisely the phase visible at receipt.
        if received_view == view['view_id']:
            if events['longs'] and 'CANCEL' in view['actions']:
                self.procedures.action(received_view, 'CANCEL')
            elif events['shorts']:
                if 'CONFIRM' in view['actions']:
                    self.procedures.action(received_view, 'CONFIRM')
                elif view['state'] in ('COMPLETE', 'CANCELLED', 'FAULT'):
                    self.menu.return_from_procedure(
                        view['owner'], view['snapshots'][view['owner']].get('operation'))
                    self.oled.page, self.oled.selection = 'm04', 0
        self.oled.render_at = 0.
        return True

    def _platform_context(self):
        o=self.oled
        if o.message or o.page not in ('home','m04') or self.menu.page!='maintenance':
            return None
        actions=o._presented_actions
        if (o._presented_context!=o._input_context() or not actions
                or not 0<=o.selection<len(actions)):
            return None
        action=actions[o.selection]
        if not action or action[0]!='platform_hold':
            return None
        return (o._input_context(),o.selection,action[1])

    def _platform_visible(self):
        stream=self.oled.stream
        if not stream.enabled or not stream.ready:
            return False
        display=self.printer.lookup_object('m300_display',None)
        return not (display is not None and
            (display._consume_gesture or display.phase=='ENTERING_SLEEP'
             or display._presentation_wait
             or getattr(stream,'display_mode',None)=='OFF'
             or getattr(stream,'requested_mode',None)=='OFF'))

    def platform_receipt(self,stream):
        return (self._platform_context(), self._platform_visible()
                and stream.previous==self.oled._render_wire)

    def platform_panel(self,snapshot,received_at,receipt,events,now):
        service=self.menu.maintenance
        if not getattr(service,'lease',None):
            return False
        context,acknowledged=receipt or (None,False)
        visible=(context is not None and context==self._platform_context()
                 and self._platform_visible())
        fresh=(type(received_at) in (int,float) and math.isfinite(received_at)
               and 0.<=now-received_at<=.75 and events is not None)
        pressed=snapshot.get('pressed') in (1,True)
        was_held=service.state=='PLATFORM_HOLD'
        consume=getattr(self,'_platform_gesture',False)
        if was_held:
            same_press = pressed and fresh and not events['releases']
            service.refresh_hold(context, received_at, same_press, visible and fresh)
        if not fresh or not visible:
            self._platform_released=False
            if not pressed:
                self._platform_gesture=False
            return was_held or consume
        if not pressed:
            self._platform_released=True
            self._platform_gesture=False
            return was_held or consume
        if not was_held and not consume and events.get('presses'):
            may_start=(acknowledged and getattr(self,'_platform_released',False)
                       and not events.get('delta'))
            self._platform_released=False
            self._platform_gesture=True
            if may_start:
                try:
                    service.hold(context[2],context,received_at,
                        lambda:context==self._platform_context() and self._platform_visible(),
                        snapshot['presses'])
                except Exception as exc:
                    self.menu.reason=str(exc)
            self.oled.render_at=0.
            return True
        return was_held or consume

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
                'host_ui_revision':'0.13.16.10-NATIVE-PRINT-CONTEXT',
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
