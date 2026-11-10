#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render documentation from production menu rows, OEM font, icons and frame code.
Only in-memory demonstration state is used. Never constructs an MCU or issues G-code.
Run: python docs/tools/render_oled_manual.py --klipper .ci/pristine
Requires Pillow and Jinja2 (the existing Klippy test dependencies).
"""
import argparse
import configparser
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--klipper', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.klipper.resolve() / 'klippy'))
    import extras
    extras.__path__.insert(0, str(ROOT / 'host/klippy/extras'))
    from extras.m300_menu import M300Menu
    from extras.m300_settings import M300Settings, PAGES
    from extras.m300_settings_ui import menu_frame, brightness_frame, notice_frame
    from extras.m300_oled_render import Frame
    from extras.m300_oled_preview import encoded_png
    from extras.m300_oem_graphics import OEMGraphics, choose_icon
    from extras.m300_activity_graphics import menu_symbol
    from extras.m300_leveling_oem import describe, render
    from extras.m300_print_ui import frame_for, PAUSE_ROWS, STOP_ROWS
    from extras.m300_display_oem import sleep_wire, load_moon
    from extras.m300_fans import M300Fans
    from PIL import Image
    import io

    out = ROOT / 'docs/img/oled'
    out.mkdir(parents=True, exist_ok=True)
    graphics = OEMGraphics()
    records = []
    def save(name, wire, title, state):
        if len(wire) != 8192:
            raise ValueError(name + ': not a complete 256x64 4bpp frame')
        raw = encoded_png(wire)
        (out / (name + '.png')).write_bytes(raw)
        image = Image.open(io.BytesIO(raw)).convert('RGB')
        image.resize((768, 192), Image.Resampling.NEAREST).save(out / (name + '@3x.png'), optimize=True)
        records.append(dict(id=name, title=title, example_state=state,
                            native_dimensions=[256, 64], preview_dimensions=[768, 192],
                            wire_sha256=hashlib.sha256(wire).hexdigest(),
                            png_sha256=hashlib.sha256(raw).hexdigest()))

    m = M300Menu.__new__(M300Menu)
    m.generation, m.page, m.reason, m._busy = 1, 'main', '', False
    m._labels, m._temperature = {}, {'HOTEND': 200., 'BED': 60.}
    m._procedure_return, m.cycle = None, None
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(ROOT / 'host/config/m300_classic_base.cfg')
    m.job = NS(board=NS(native_control=True),
        hotend=NS(min_temp=cp.getfloat('extruder','min_temp'),max_temp=cp.getfloat('extruder','max_temp')),
        bed=NS(min_temp=cp.getfloat('heater_bed','min_temp'),max_temp=cp.getfloat('heater_bed','max_temp')))
    m._return_page = 'klipper'
    m.maintenance = NS(get_status=lambda now: {'sleep': False})
    m.t = lambda text: text
    settings = M300Settings.__new__(M300Settings)
    settings.information = lambda now: dict(host_version='R16.12',mcu_release='0.13.14.18',
        mcu_version='test',printer_model='Zortrax M300 Classic',hardware_version='HW05',
        serial_number='DEMO-NOT-A-SERIAL',total_printing_time='12 h 34 min')
    objects = {'m300_settings': settings,
               'm300_models': NS(), 'm300_sd': NS(qualified=True),
               'm300_pad_mesh': NS(get_status=lambda now: dict(state='IDLE',phase='IDLE',busy=False)),
               'print_stats': NS(get_status=lambda now: dict(state='standby', filename='', print_duration=0)),
               'm300_fans': NS(rows=lambda now: ('Fans',[('Back',None),('Upper: cooling auto',None),('Print fan: 0%',None)]))}
    m.printer = settings.printer = NS(lookup_object=lambda name, default=None: objects.get(name,default),
                                      command_error=RuntimeError)
    pages = [
        ('main', 1, 'main_klipper'), ('main', 2, 'main_zortrax'),
        ('zortrax', 2, 'zortrax_menu'), ('klipper', 6, 'klipper_home'),
        ('klipper', 11, 'klipper_mesh'), ('klipper', 14, 'klipper_pid'),
        ('maintenance', 1, 'maintenance_level'), ('maintenance', 4, 'maintenance_home_z'),
        ('maintenance', 7, 'maintenance_heat'), ('maintenance', 9, 'maintenance_platform'),
        ('material', 2, 'material_load'), ('settings', 1, 'settings'),
        ('settings', 6, 'settings_preheat'), ('setting_light_mode',1,'setting_light'),
        ('setting_sound',1,'setting_buzzer'), ('setting_sleep_mode',1,'setting_sleep'),
        ('setting_language',1,'setting_language'), ('setting_sort_mode',1,'setting_sort'),
        ('setting_full_platform_preheat',1,'setting_preheat'),
        ('information',2,'information'), ('info_firmware',0,'firmware'),
        ('info_printer',0,'printer_information'), ('help',0,'help'),
        ('native_moves',1,'move_axes'), ('native_move_x',4,'move_x'),
        ('native_move_z',4,'move_z'), ('native_pid',1,'pid'),
        ('models',1,'models'), ('bed_mesh',2,'bed_mesh'), ('tests',1,'service_tests')]
    # Extra beta.20 manual views use the same production menu paths, not sketches.
    pages.extend([
        ('klipper',1,'klipper_temp_hotend'), ('klipper',2,'klipper_temp_bed'),
        ('klipper',3,'klipper_heat_hotend'), ('klipper',4,'klipper_heat_bed'),
        ('klipper',5,'klipper_heaters_off'), ('klipper',7,'klipper_home_y'),
        ('klipper',8,'klipper_home_z'), ('klipper',9,'klipper_home_xy'),
        ('klipper',10,'klipper_home_xyz'), ('klipper',13,'klipper_fans'),
        ('native_job',0,'print_details'), ('maintenance',8,'maintenance_heat_bed'),
        ('maintenance',10,'maintenance_platform_down'), ('maintenance',11,'maintenance_fan_test'),
        ('material',1,'material_unload'), ('native_move_y',4,'move_y'),
        ('native_pid',2,'pid_bed'), ('native_pid',3,'pid_save'),
        ('models',2,'models_host'), ('temperature_HOTEND',4,'temperature_hotend'),
        ('temperature_BED',3,'temperature_bed'), ('fans',9,'fan_controls')])
    fans = M300Fans.__new__(M300Fans)
    fans.board, fans.ready, fans.test, fans.reason = m.job.board, True, None, ''
    fans.get_status = lambda now: dict(state='READY', forced_cooling=False,
        mcu_status_fresh=True, can_cancel=False, channels={
            'print':dict(pin='PE13',effective_duty=0.,requested=0.),
            'hotend':dict(pin='PE14',effective_duty=0.,requested=0.)})
    objects['m300_fans'] = fans
    objects['m300_print_ui'] = NS()  # native detail page is read-only with this owner
    menu_rows = {}
    for page, selection, name in pages:
        m.page=page
        title, rows=m.rows(0.)
        if page=='main': rows=[('Back',('oled','status'))]+rows
        menu_rows[page]=[dict(label=label, action=list(action) if isinstance(action,tuple) else action) for label,action in rows]
        choice=menu_symbol(page,'m04',rows,selection)
        icon=choice.key if choice else choose_icon(menu_page=page,panel_page='m04',rows=rows,selected=selection)
        sprite=graphics.get(icon,0.) if icon else None
        wire=menu_frame(tuple(label for label,_ in rows),(),selection,Frame,sprite)
        save(name,wire,title,dict(page=page,selected=selection,sprite=icon))
    for key, title in [('oled_brightness','OLED brightness'),('led_brightness','LED brightness')]:
        rows=[('Back',None)]
        choice=menu_symbol('setting_'+key,'m04',rows,1)
        sprite=graphics.get(choice.key,0.) if choice else None
        save(key,brightness_frame(title,12,False,Frame,sprite),title,dict(level=12,demonstration=True))
    for name,state in [('level_prepare',dict(state='WAIT_PREPARE',can_confirm=True)),
                       ('level_tighten',dict(state='WAIT_TIGHTEN',can_confirm=True)),
                       ('level_heating',dict(state='HEATING')),
                       ('level_adjust',dict(state='ADJUST',instruction=dict(screw='rear_left',action='LOOSEN',delta_mm=-.25,turns=.5))),
                       ('level_result',dict(state='REVIEW',review=[-.05,0.,.02,-.03,.01]))]:
        save(name,render(describe(state,'EN'),graphics,Frame,0.),'Autocalibration',state)
    save('pause',frame_for(Frame,'PAUSE MENU',tuple(x[0] for x in PAUSE_ROWS),0,graphics.get('0x0801dc08',0.)),
         'PAUSE MENU',dict(state='PAUSED',demonstration=True))
    save('cancel_confirmation',frame_for(Frame,'STOP THE PRINT?',tuple(x[0] for x in STOP_ROWS),0,graphics.get('0x0801fe34',0.)),
         'STOP THE PRINT?',dict(state='STOP_CONFIRM',demonstration=True))
    save('no_models',notice_frame('Notice #101','No models on SD card',Frame,graphics.get('0x0801be48',0.)),
         'Notice #101',dict(state='illustrative_notice',demonstration=True))
    save('sleep',sleep_wire(Frame,load_moon()),'Entering sleep mode',dict(state='ENTERING_SLEEP'))

    # Execute the actual pinned Klipper template group and M300 memory LCD renderer.
    # Prevent hardware modules from being imported or used in a docs-only renderer.
    import types
    bus = types.ModuleType('extras.bus')
    def forbidden(*args, **kwargs):
        raise RuntimeError('Documentation renderer cannot access MCU/SPI/I2C')
    bus.MCU_SPI_from_config = bus.MCU_I2C_from_config = forbidden
    sys.modules['extras.bus'] = bus
    from extras.gcode_macro import TemplateWrapper
    from extras.m300_klipper_status import KlipperStatus
    import jinja2
    state = dict(extruder=dict(temperature=20.2,target=0),heater_bed=dict(temperature=20.4,target=0),
                 fan=dict(speed=0), toolhead=dict(extruder='extruder',estimated_print_time=0.,position=NS(x=0,y=0,z=0)),
                 idle_timeout=dict(printing_time=0),gcode_move=dict(speed_factor=1),
                 display_status=dict(progress=0,message='Ready'))
    objects_native={}
    class Config:
        error=ValueError
        def __init__(self, cp, section=''): self.cp,self.section=cp,section
        def get_printer(self):return printer
        def get_name(self):return self.section
        def get(self,key,default=None):return self.cp.get(self.section,key,fallback=default)
        def getint(self,key,default=None,**kwargs):return int(self.get(key,default))
        def get_prefix_options(self,prefix):return [k for k in self.cp[self.section] if k.startswith(prefix)]
        def get_prefix_sections(self,prefix):return [Config(self.cp,s) for s in self.cp.sections() if s.startswith(prefix)]
    def read_config(path):
        cp=configparser.RawConfigParser(strict=False,inline_comment_prefixes=('#',';'))
        cp.read(path)
        return Config(cp)
    env=jinja2.Environment('{%','%}','{','}')
    macro=NS(create_template_context=lambda eventtime=None:dict(printer=state))
    macro.load_template=lambda config,option:TemplateWrapper(printer,env,config.get_name(),config.get(option))
    printer=NS(lookup_object=lambda name,default=None:objects_native.get(name,default),
               add_object=lambda name,obj:objects_native.update({name:obj}),
               load_object=lambda config,name:objects_native[name], config_error=ValueError,command_error=ValueError)
    objects_native.update(gcode=NS(error=ValueError),gcode_macro=macro,configfile=NS(read_config=read_config))
    lcd=KlipperStatus(Config(configparser.RawConfigParser()))
    save('status_ready',lcd.render(0.),'Klipper Ready',dict(temperatures=[20.2,20.4],targets=[0,0],demonstration=True))
    state['extruder'].update(temperature=200.,target=200.)
    state['heater_bed'].update(temperature=60.,target=60.)
    state['idle_timeout']['printing_time']=1234.
    state['display_status'].update(progress=.42,message='Printing')
    save('status_printing',lcd.render(1.),'Klipper Printing',dict(progress=.42,demonstration=True))

    report=ROOT/'docs/reports/OLED_RENDER_MANIFEST.json'
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(dict(source_release='v1.0.0-beta.20',source_commit='4828a9da9d5fd8b0b93eb2ac267732ee7e49d506',
        method='Production menu rows, bitmap font, sprite selectors and pure renderers; illustrative in-memory state only',
        physical_printer=False, screens=records, menu_rows=menu_rows),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status='PASS',screens=len(records),png_files=len(records)*2)))

if __name__=='__main__':main()
