# SPDX-License-Identifier: GPL-3.0-or-later
"""TEST01 marker; default diagnostics or explicit supervised heating test.

Default mode requires all gates False. heating_test_mode permits only the two
heating permission flags and requires m300_thermal supervision; motion and all
workflow qualification flags remain False. No new hardware owner is created.
"""
import json

GATES = {
    'm300_mcu': ('allow_actuators', 'allow_motion', 'allow_heating'),
    'm300_job': ('workflow_qualified', 'contact_homing_qualified', 'binary_zcode_qualified'),
    'm300_filament': ('filament_qualified',),
    'm300_sd': ('sd_qualified',),
    'm300_maintenance': ('qualified',),
    'm300_calibration': ('qualified',),
    'm300_motion': ('qualified', 'unknown_z_qualified', 'initial_xy_clearance_qualified', 'jog_qualified'),
    'm300_cycle': ('qualified',),
}

class M300Test01:
    def __init__(self, config):
        self.printer=config.get_printer()
        self.reactor=self.printer.get_reactor()
        self.heating_test_mode=config.getboolean('heating_test_mode',False)
        if self.heating_test_mode and not config.has_section('m300_thermal'):
            raise config.error('TEST01 heating_test_mode requires [m300_thermal] supervision')
        self.gates={}
        for name, options in GATES.items():
            if not config.has_section(name):
                raise config.error('TEST01 requires explicit [' + name + ']')
            section=config.getsection(name)
            for option in options:
                value=section.getboolean(option)  # explicit value required
                self.gates[name+'.'+option]=value
                heating_permission=(self.heating_test_mode and name=='m300_mcu'
                                    and option in ('allow_actuators','allow_heating'))
                if value and not heating_permission:
                    raise config.error('TEST01 forbids enabled qualification: ' + name+'.'+option)
        if self.heating_test_mode and not all(self.gates['m300_mcu.'+name]
                                              for name in ('allow_actuators','allow_heating')):
            raise config.error('TEST01 heating test requires both explicit heating permissions')
        self.ready=False
        self.printer.register_event_handler('klippy:ready',self._ready)
        for event in ('klippy:shutdown','klippy:disconnect','gcode:request_restart'):
            self.printer.register_event_handler(event,self._stop)

    def _ready(self):
        self.ready=True

    def _stop(self,*args):
        self.ready=False

    def get_status(self,eventtime):
        return {'profile':'M300_TEST01','release':'0.13.1-LAB_TEST01',
                'ready':self.ready,'diagnostics_only':not self.heating_test_mode,
                'heating_test_mode':self.heating_test_mode,'motion_enabled':False,
                'qualification_gates':dict(self.gates),'physical_qualification':False,
                'requires_manual_next_stage':True}


def load_config(config):
    return M300Test01(config)
