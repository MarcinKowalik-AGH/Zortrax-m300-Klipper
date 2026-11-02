# SPDX-License-Identifier: GPL-3.0-or-later
"""M09 operator/menu facade. Delegates *all* physical work to M03.

Can be omitted from legacy printer.cfg; no changes to original M03 behavior.
"""
import json
from .m300_material_ui_state import view_from_status, check_operator_action, MaterialUiError

class M300MaterialUI:
    def __init__(self,config):
        self.printer=config.get_printer()
        self.gcode=self.printer.lookup_object('gcode')
        self.filament=self.printer.load_object(config,'m300_filament')
        self.reactor=self.printer.get_reactor()
        self.gcode.register_command('ZORTRAX_MATERIAL_STATUS',self.cmd_status,when_not_ready=True)
        self.gcode.register_command('ZORTRAX_MATERIAL_START',self.cmd_start)
        self.gcode.register_command('ZORTRAX_MATERIAL_CONFIRM',self.cmd_confirm)
        self.gcode.register_command('ZORTRAX_MATERIAL_PURGE',self.cmd_purge)
        self.gcode.register_command('ZORTRAX_MATERIAL_CANCEL',self.cmd_cancel)
    def view(self):
        return view_from_status(self.filament.get_status(self.reactor.monotonic()))
    def start(self,operation,temperature=None):
        if operation not in ('LOAD','UNLOAD','CHANGE'):
            raise self.printer.command_error('M09: unknown material procedure')
        self.filament.start(operation,temperature=temperature)
        return self.view()
    def act(self,action,token,phase):
        view=self.view()
        try: check_operator_action(view,action,token,phase)
        except MaterialUiError as exc: raise self.printer.command_error('M09: '+str(exc))
        # M03 verifies the token, phase, guards and thermal ownership again.
        if action=='CONFIRM': self.filament.confirm(token,phase)
        elif action=='PURGE': self.filament.purge(token,phase)
        else: self.filament.cancel('M09 operator cancel',token=token)
        return self.view()
    def get_status(self, now):
        # A malformed M03 snapshot never crashes Klippy's global status API
        # or advertises a permitted button.
        try:
            view = self.view()
        except Exception as exc:
            return {'model': 'M300_CLASSIC', 'stage': 'M09', 'installed': True,
                    'ready': False, 'busy': None, 'actions': (),
                    'state': 'UNAVAILABLE', 'reason': str(exc)[:160]}
        return dict(view, model='M300_CLASSIC', stage='M09', installed=True)

    def cmd_status(self,gcmd):
        gcmd.respond_info('M300_M09 '+json.dumps(self.view(),sort_keys=True))
    def cmd_start(self,gcmd):
        self.start(gcmd.get('OPERATION'),gcmd.get_float('TEMP',None))
    def _act(self,gcmd,action):
        self.act(action,gcmd.get_int('TOKEN',minval=0),gcmd.get_int('PHASE',minval=0))
    def cmd_confirm(self,gcmd): self._act(gcmd,'CONFIRM')
    def cmd_purge(self,gcmd): self._act(gcmd,'PURGE')
    def cmd_cancel(self,gcmd): self._act(gcmd,'CANCEL')

def load_config(config): return M300MaterialUI(config)
