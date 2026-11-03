# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared English Settings/Information over existing owners and host NVM.

Rendering reads cached data only. Optional Moonraker history is fetched on
explicit navigation/refresh in a dedicated executor. No printer control,
factory Flash writes or additional sleep/timer policy lives here.
"""
import hashlib
import json
import math
import os
import urllib.request

PROJECT_URL = 'https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper'
HOST_VERSION = 'R16.11'
UPSTREAM = 'ee2c6fb6b00b2b5d097ef70d0868df7d74943b51'
SETTINGS = (
    ('light_mode','Light',(('DYNAMIC','Dynamic'),('WHITE','White'),('DISABLE','Disabled'))),
    ('sound','Buzzer',((True,'Enabled'),(False,'Disabled'))),
    ('sleep_mode','Sleep mode',(('15MIN','Enabled'),('OFF','Disabled'))),
    ('language','Language',(('EN','English'),)),
    ('sort_mode','Models sorting',(('DATE','Date'),('NAME','Name'),
                                  ('NAME_CASE','Case-sensitive name'),('SIZE','File size'))))
CHOICES = {key:values for key,_,values in SETTINGS}
TITLES = {key:title for key,title,_ in SETTINGS}
PARENTS = {'settings':'zortrax','information':'zortrax','help':'information',
           'info_firmware':'information','info_printer':'information',
           **{page:'info_printer' for page in ('info_model','info_hardware','info_serial','info_time')}}
PARENTS.update({'setting_'+key:'settings' for key in CHOICES})
PAGES = frozenset(PARENTS)


def display_text(value, limit=160):
    return ' '.join(str(value or '').replace('|','/').split())[:limit]


def duration(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds < 0:
        return 'Unavailable'
    minutes=int(seconds)//60
    return '%d h %02d min' % (minutes//60,minutes%60)


def history_totals(url):
    request=urllib.request.Request(url.rstrip('/')+'/server/history/totals',
                                   headers={'Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=2.) as response:
        raw=response.read(65537)
    if len(raw)>65536:
        raise ValueError('history response exceeds 64 KiB')
    data=json.loads(raw)
    totals=data['result']['job_totals']
    value=totals['total_print_time']
    if type(value) not in (float,int) or not math.isfinite(value) or not 0. <= value <= 1.e15:
        raise ValueError('invalid history printing time')
    return float(value)


def choice_value(nvm,key):
    if key=='language':return 'EN'
    value=nvm.get_setting(key)
    if key=='sleep_mode':return 'OFF' if value=='OFF' else '15MIN'
    return value


class M300Settings:
    def __init__(self,config):
        self.printer=config.get_printer();self.reactor=self.printer.get_reactor()
        self.gcode=self.printer.lookup_object('gcode')
        self.nvm=self.printer.load_object(config,'m300_nvm')
        self.executors=self.printer.load_object(config,'aio_executor')
        self.executor=None
        self.url=config.get('moonraker_url','http://127.0.0.1:7125')
        self.serial=config.get('serial_number',None)
        if self.serial is not None and (not 1<=len(self.serial)<=64 or not self.serial.strip()
                or any(not 32<=ord(c)<127 or c=='|' for c in self.serial)):
            raise config.error('serial_number must be 1..64 printable ASCII characters')
        self.ready=False;self.reading=False;self.setting_busy=False
        self.epoch=os.urandom(16).hex();self.generation=0;self.fetch_token=0
        self.page='settings';self.consumed=None
        self.history_seconds=None;self.history_error=None;self.history_stamp=None
        self.request_time=None
        self.printer.register_event_handler('klippy:ready',self._ready)
        for event in ('klippy:shutdown','klippy:disconnect','gcode:request_restart'):
            self.printer.register_event_handler(event,self.invalidate)
        for name,callback in (('ZORTRAX_UI_SHOW',self.cmd_show),('ZORTRAX_UI_ACTION',self.cmd_action),
                ('ZORTRAX_UI_SETTING',self.cmd_setting),('ZORTRAX_SETTINGS_STATUS',self.cmd_status),
                ('ZORTRAX_INFO',self.cmd_info),('ZORTRAX_MENU_HELP',self.cmd_help)):
            self.gcode.register_command(name,callback,when_not_ready=name.endswith('STATUS'))

    def _ready(self):self.ready=True

    def invalidate(self,*args):
        self.ready=False;self.fetch_token+=1;self.generation+=1
        self.consumed=None

    def _live(self):
        if not self.ready or self.printer.is_shutdown():
            raise self.printer.command_error('M300 Settings: Klippy is not ready')

    def request_refresh(self):
        self._live()
        now=self.reactor.monotonic()
        if self.reading or self.request_time is not None and now-self.request_time<5.:
            return
        self.reading=True;self.request_time=now;self.fetch_token+=1
        token=self.fetch_token
        if self.executor is None:self.executor=self.executors.allocate_executor('m300-information')
        def fetch(eventtime):
            try:
                if token!=self.fetch_token or not self.ready:return
                value=self.executor.submit(history_totals,self.url)
                error=None
            except Exception as exc:
                value=None;error='Moonraker history unavailable: '+display_text(exc,140)
            finally:
                self.reading=False
            if token!=self.fetch_token or not self.ready or self.printer.is_shutdown():return
            if error is None:self.history_seconds=value
            self.history_error=error
            self.history_stamp=self.reactor.monotonic()
        self.reactor.register_callback(fetch)

    def information(self,now):
        board=self.printer.lookup_object('m300_mcu',None)
        hardware=getattr(board,'hardware',None)
        hw=hardware.get_status() if hardware is not None else {}
        mcu=board.get_mcu() if board is not None else None
        try:version=mcu.get_status(now).get('mcu_version') if mcu is not None else None
        except Exception:version=None
        serial=display_text(self.serial or hw.get('serial_number'),64) or None
        version=display_text(version) or None
        return dict(host_version=HOST_VERSION,mcu_version=version,
            mcu_release=display_text(getattr(board, 'mcu_release', None)) or None, upstream_commit=UPSTREAM,
            oem_reference='1.3.1',printer_model='Zortrax M300 Classic',
            hardware_version=display_text(hw.get('hardware_label')) or None,serial_number=serial,
            serial_source='Configured printer serial' if self.serial else
                          'Factory record' if serial else 'Unavailable in current MCU API',
            total_print_seconds=self.history_seconds,total_printing_time=duration(self.history_seconds),
            time_source=('Moonraker history (cached)' if self.history_error else 'Moonraker history')
                if self.history_seconds is not None else 'Unavailable',
            time_note='Recorded Klipper jobs; factory lifetime is not inferred',
            history_reading=self.reading,history_error=self.history_error,
            history_updated_at=self.history_stamp,project_url=PROJECT_URL)

    def rows(self,page,now):
        if page not in PAGES:
            raise self.printer.command_error('Unknown Settings/Information page')
        back=[('Back',('page',PARENTS[page]))]
        if page=='settings':
            return 'Settings',back+[(title,('setting',key)) for key,title,_ in SETTINGS]
        if page.startswith('setting_'):
            key=page[8:]
            return TITLES[key],back+[(label,('set',key,value)) for value,label in CHOICES[key]]
        if page=='information':
            return 'Information',back+[(title,('page',target)) for title,target in (
                ('Firmware version','info_firmware'),('Printer information','info_printer'),('Help','help'))]
        if page=='info_printer':
            return 'Printer information',back+[(title,('page',target)) for title,target in (
                ('Printer model','info_model'),('Hardware version','info_hardware'),
                ('Serial number','info_serial'),('Total printing time','info_time'))]
        info=self.information(now)
        if page=='info_firmware':
            title='Firmware version'
            lines=['Host '+info['host_version'],'MCU '+str(info['mcu_release'] or info['mcu_version'] or 'Unavailable'),
                   'Klipper '+UPSTREAM[:12],'OEM reference 1.3.1']
        elif page=='info_model':title,lines='Printer model',[info['printer_model']]
        elif page=='info_hardware':title,lines='Hardware version',[info['hardware_version'] or 'Unavailable']
        elif page=='info_serial':title,lines='Serial number',[info['serial_number'] or 'Unavailable',info['serial_source']]
        elif page=='info_time':
            title='Total printing time'
            lines=[info['total_printing_time'],info['time_source']]
            if info['history_reading']:lines.append('Reading history')
            if info['history_error']:lines.append(info['history_error'])
        else:
            title='Help';lines=['github.com/','MarcinKowalik-AGH/','Zortrax-m300-Klipper','Project documentation and issues']
        return title,back+[(line,None) for line in lines]

    def active_rows(self,page):
        if not page.startswith('setting_'):return ()
        key=page[8:];current=choice_value(self.nvm,key)
        return tuple(i+1 for i,(value,_) in enumerate(CHOICES[key]) if value==current)

    def set_option(self,key,value):
        self._live()
        if self.setting_busy or key not in CHOICES or not any(type(value) is type(v) and value==v for v,_ in CHOICES[key]):
            raise self.printer.command_error('Unsupported or busy English Settings choice')
        self.setting_busy=True
        try:
            if key=='sleep_mode' and (value!='OFF')==(self.nvm.get_setting(key)!='OFF'):
                return self.nvm.ui_snapshot()
            return self.nvm.set_setting(key,value)
        finally:self.setting_busy=False

    def _view_id(self):
        revision=self.nvm.ui_snapshot()['revision']
        return hashlib.sha256(('%s:%s:%s:%s'%(self.epoch,self.generation,self.page,revision)).encode()).hexdigest()[:24]

    def show(self,page=None,refresh=False):
        self._live()
        if page is not None:
            if page not in PAGES:raise self.printer.command_error('Unknown Settings/Information page')
            self.page=page
        if refresh:self.request_refresh()
        self.generation+=1;self.consumed=None
        title,rows=self.rows(self.page,self.reactor.monotonic())
        procedure=self.printer.lookup_object('m300_procedures',None)
        if procedure is not None and procedure.get_status(self.reactor.monotonic()).get('busy'):
            self.gcode.respond_info('M300 UI '+json.dumps(dict(title=title,lines=[r[0] for r in rows])))
            return
        def emit(line):self.gcode.respond_raw('// action:'+line)
        emit('prompt_end');emit('prompt_begin ZORTRAX M300 - '+title)
        token=self._view_id()
        active=self.active_rows(self.page)
        for index,(label,action) in enumerate(rows):
            label=label+(' <' if index in active else '')
            if action is None:emit('prompt_text '+label.replace('|','/'))
            else:emit('prompt_button %s|ZORTRAX_UI_ACTION VIEW=%s INDEX=%d|primary'%(label,token,index))
        if self.page == 'help':
            emit('prompt_text ' + PROJECT_URL)
        if self.page == 'info_time':
            emit('prompt_footer_button Refresh|ZORTRAX_UI_SHOW PAGE=info_time REFRESH=1|info')
        emit('prompt_show')

    def action(self,token,index):
        self._live();title,rows=self.rows(self.page,self.reactor.monotonic())
        if (token!=self._view_id() or token==self.consumed or type(index) is not int
                or not 0<=index<len(rows) or rows[index][1] is None):
            raise self.printer.command_error('Expired Settings view; refresh before choosing')
        self.consumed=token
        action=rows[index][1]
        if action[0]=='set':self.set_option(action[1],action[2])
        else:
            page='setting_'+action[1] if action[0]=='setting' else action[1]
            if page not in PAGES:
                self.gcode.respond_raw('// action:prompt_end');return
            self.page=page
        self.show(refresh=self.page=='information')

    def get_status(self,now):
        settings={key:choice_value(self.nvm,key) for key in CHOICES}
        sleep=settings['sleep_mode']!='OFF'
        settings['sleep_mode']='ENABLED' if sleep else 'DISABLED'
        display=self.printer.lookup_object('m300_display',None)
        return dict(revision='0.13.16.8-SETTINGS-INFORMATION',ready=self.ready,state='IDLE',busy=False,
            io_busy=self.reading,settings=settings,
            language='EN',sleep_enabled=sleep,display_timeout_seconds=getattr(display,'timeout',None),
            information=self.information(now),project_url=PROJECT_URL)

    def cmd_status(self,gcmd):
        gcmd.respond_info('M300_SETTINGS '+json.dumps(self.get_status(self.reactor.monotonic()),sort_keys=True))

    def cmd_setting(self,gcmd):
        key=gcmd.get('NAME').lower();raw=gcmd.get('VALUE').upper()
        aliases={'light':'light_mode','buzzer':'sound','sleep':'sleep_mode','sort':'sort_mode'}
        key=aliases.get(key,key)
        if key=='sound':
            if raw not in ('ENABLED','DISABLED'):raise gcmd.error('Use Enabled or Disabled')
            value=raw=='ENABLED'
        elif key=='sleep_mode':
            if raw not in ('ENABLED','DISABLED'):raise gcmd.error('Use Enabled or Disabled')
            value='15MIN' if raw=='ENABLED' else 'OFF'
        else:value='DISABLE' if key=='light_mode' and raw=='DISABLED' else raw
        self.set_option(key,value);self.cmd_status(gcmd)

    def cmd_show(self,gcmd):
        self.show(gcmd.get('PAGE','settings').lower(),bool(gcmd.get_int('REFRESH',0,minval=0,maxval=1)))

    def cmd_action(self,gcmd):self.action(gcmd.get('VIEW'),gcmd.get_int('INDEX',minval=0))

    def cmd_info(self,gcmd):
        if gcmd.get_int('REFRESH',1,minval=0,maxval=1):self.request_refresh()
        gcmd.respond_info('M300_INFORMATION '+json.dumps(self.information(self.reactor.monotonic()),sort_keys=True))

    def cmd_help(self,gcmd):self.show('help')


def load_config(config):return M300Settings(config)
