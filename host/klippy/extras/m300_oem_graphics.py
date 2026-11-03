# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only Classic M300 v1.3.1 original sprite selection and decoding.

No GPIO, MCU, heater, G-code or motor imports. OEM icon data is verified against
SHA-256 of the decrypted OEM application and every recovered frame.
Only menu/procedure artwork is selected here. The native Klipper status screen
has its own unchanged renderer. Hardware qualification is independent.
"""
import base64
import hashlib
import json
import math
from pathlib import Path
import zlib

STOCK_SHA256 = '11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75'
MAIN = {'models':'0x0801c690','maintenance':'0x0801c958',
        'material':'0x0801cdd8','settings':'0x0801d3bc',
        'information':'0x0801dc08'}
PAGES = {'models':'0x0801c690','browser':'0x0801c690',
         'preview':'0x0801c690','confirm_print':'0x0801c690',
         'maintenance':'0x0801c958','material':'0x0801cdd8',
         'material_status':'0x0801cdd8','settings':'0x0801d3bc',
         'information':'0x0801dc08','help':'0x0801de00',
         'setting_light_mode':'0x0801d55c','setting_sound':'0x0801d72c',
         'setting_sleep_mode':'0x0801d908','setting_language':'0x0801dab4',
         'setting_sort_mode':'0x0801c4f4',
         'info_firmware':'0x0801dc08','info_printer':'0x0801dfdc',
         'info_model':'0x0801dfdc','info_hardware':'0x0801dfdc',
         'info_serial':'0x0801dfdc','info_time':'0x0801dfdc',
         'calibration':'0x0801ca28','motion_jog':'0x0801cb24',
         'motion_status':'0x0801c958',
         'stock_atlas':'0x0801dc08','stock_detail':'0x0801dc08'}
ACTION_ICONS={'cal_start':'0x0801ca28',
              'motion_jog':'0x0801cb24',
              'motion_home':'0x0801c958',
              'wake':'0x0801d908'}
SCREW_LOW={'rear_left':'0x0801e90c','rear_right':'0x0801ed14',
           'front':'0x0801f0cc'}
SCREW_HIGH={'rear_left':'0x0801f4c0','rear_right':'0x0801f8b4',
            'front':'0x0801fc6c'}

class OEMGraphics:
    def __init__(self, path=None):
        if path is None:
            path=Path(__file__).with_name('m300_oem_sprites_131.json')
        with open(path, encoding='utf-8') as fp:
            self.spec=json.load(fp)
        if self.spec['source_sha256'] != STOCK_SHA256:
            raise ValueError('OEM sprites do not match M300 Classic 1.3.1 source')
        self.frames=self.spec['frames']
        if len(self.frames) != 37:
            raise ValueError('Expected the 37 audited OEM descriptors')
        for desc in self.frames.values():
            if (desc['width'], desc['height']) != (50, 50) or not 1 <= len(desc['frames']) <= 9:
                raise ValueError('Invalid OEM descriptor geometry')
        self.cache={}

    def get(self, addr, now=0.):
        addr=str(addr).lower()
        desc=self.frames.get(addr)
        if desc is None:
            return None
        fs=desc['frames']
        period=desc['period_ticks']
        # OEM SysTick is nominally 1 kHz at the expected 72 MHz MCU clock.
        # The visual frame cadence is not a hardware-timing assertion.
        now = float(now)
        if not math.isfinite(now):
            now = 0.
        index=int(max(0.,now)*1000 // period)%len(fs) if period else 0
        cache_key=(addr,index)
        if cache_key not in self.cache:
            record=fs[index]
            raw=zlib.decompress(base64.b64decode(record['zlib_b64'], validate=True))
            if len(raw)!=(desc['width']*desc['height']+1)//2:
                raise ValueError('Invalid OEM 4bpp frame size')
            if hashlib.sha256(raw).hexdigest()!=record['sha256']:
                raise ValueError('Invalid OEM icon SHA256')
            self.cache[cache_key]=(desc['width'],desc['height'],raw)
        return self.cache[cache_key]


def choose_icon(*, menu_page='main', panel_page='m04', rows=(), selected=0,
                calibration=None, filament=None, job=None):
    """Return OEM image DESCRIPTOR, never actions. All inputs are read-only snapshots."""
    if (menu_page in ('settings', 'information', 'help') or
            menu_page.startswith(('setting_', 'info_'))):
        return PAGES.get(menu_page)
    calibration=calibration or {}
    filament=filament or {}
    job=job or {}
    if menu_page == 'calibration':
        state=calibration.get('state','')
        if state=='ADJUST':
            instr=calibration.get('instruction') or {}
            screw=instr.get('screw')
            return ((SCREW_HIGH if instr.get('action')=='TIGHTEN' else SCREW_LOW)
                    .get(screw,'0x0801ca28'))
        if state in ('WAIT_PREPARE', 'WAIT_WARNING'): return '0x0801c434'
        if state=='WAIT_TIGHTEN': return '0x0801fe50'
        if state=='HEATING': return '0x0801c2b8'
        if state=='HOMING': return '0x0801c2b8'
        if state=='PROBING':
            return '0x0801c2b8' if calibration.get('measurement_stage', 'initial')=='initial' else '0x0801ca28'
        if state in ('COMPLETE','REVIEW'):return '0x0801c024'
        if state in ('FAULT','CANCELLED'):return '0x0801fe34'
        return '0x0801ca28'
    if panel_page in ('filament','filament_cancel') or menu_page == 'material_status':
        mode=filament.get('operation','LOAD')
        state=filament.get('state','')
        if not filament or filament.get('available') is False:
            return MAIN['material']
        if state == 'FAULT': return '0x0801be48'
        if state == 'COMPLETE': return '0x0801c024'
        if state in ('CANCELLED', 'CANCELLING'): return '0x0801fe34'
        if state == 'IDLE': return MAIN['material']
        if state == 'WAIT_PAUSE': return '0x0801e178'
        if state in ('HEATING','REHEATING'):return '0x0801c2b8'
        return '0x0801cfb0' if (state=='UNLOADING' or
             mode=='UNLOAD' or state=='WAIT_UNLOAD') else '0x0801d0b8'
    if panel_page in ('job','job_cancel'):
        state=job.get('state','')
        if not job or job.get('available') is False:
            return '0x0801be48'
        if state in ('IDLE', 'PREFLIGHT'): return MAIN['models']
        if state in ('CANCELLED', 'CANCELLING'): return '0x0801fe34'
        if state == 'HEATING': return '0x0801c2b8'
        if state == 'HOMING': return MAIN['maintenance']
        if state in ('PAUSING','PAUSED'): return '0x0801e178'
        if state in ('RESUMING', 'RETURNING'):
            phase=job.get('resume_phase')
            if phase=='HEAT': return '0x0801c2b8'
            if phase=='PURGE': return '0x0801d0b8'
            return '0x0801e524'
        if state in ('COMPLETE',):return '0x0801c024'
        if state in ('FAULT','FILE_ERROR'):return '0x0801be48'
        return '0x08020fb8' if state in ('PRINTING', 'COMPLETING') else '0x0801be48'
    if menu_page in ('main','zortrax') and rows and 0<=selected<len(rows):
        action=rows[selected][1]
        if action in ('status', ('oled','status')):
            return None  # There is no audited OEM Back pictogram.
        if isinstance(action,tuple) and len(action)>1 and action[0]=='page':
            return MAIN.get(action[1], '0x0801dc08')
    if rows and 0<=selected<len(rows):
        action=rows[selected][1]
        if isinstance(action,tuple) and len(action)>0:
            if action[0] in ('ui_back','page') and (action[0]=='ui_back' or action[1] in ('main','zortrax')):
                return None
            if action[0]=='platform_hold':
                return '0x0801cb24' if action[1]<0 else '0x0801cc24'
            if action[0]=='native_gcode':
                icon={'ZORTRAX_LEVEL':'0x0801ca28','ZORTRAX_HEAT':'0x0801c2b8',
                      'ZORTRAX_UNLOAD':'0x0801cfb0','ZORTRAX_LOAD':'0x0801d0b8'}.get(action[1])
                if icon:return icon
            if action[0]=='page' and len(action)>1:
                return PAGES.get(action[1], PAGES.get(menu_page,'0x0801dc08'))
            icon=ACTION_ICONS.get(action[0])
            if icon: return icon
            if action[0]=='material' and len(action)>1:
                return '0x0801cfb0' if action[1]=='UNLOAD' else '0x0801d0b8'
            if action[0]=='oled' and len(action)>1 and action[1]=='job':
                return MAIN['models']
            if action[0]=='temperatures' or (action[0]=='service' and len(action)>1
                                            and action[1] in ('HOTEND','BED')):
                return '0x0801c2b8'
    if menu_page=='material':return '0x0801cdd8'
    return PAGES.get(menu_page, '0x0801dc08')
