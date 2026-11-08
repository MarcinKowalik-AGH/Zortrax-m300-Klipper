# SPDX-License-Identifier: GPL-3.0-or-later
"""Recovered Maintenance/Material dialogs; same text for OLED and Fluidd."""
from .m300_leveling_oem import assets, text, LANGUAGES


def describe(owner,status,language='EN'):
    if not status.get('native_control') or owner not in ('m300_filament','m300_maintenance'):
        return None
    language=language if language in LANGUAGES else 'EN'
    state=status.get('state','IDLE')
    operation=status.get('operation')
    if owner=='m300_filament' and operation not in ('LOAD','UNLOAD','CHANGE'):
        return None
    if owner=='m300_maintenance' and operation not in ('HOTEND','BED'):
        return None
    if owner=='m300_maintenance' and operation=='BED' and state in ('HEATING','WAIT_CONFIRM'):
        message=('Heating the platform\nPlease wait' if state=='HEATING' else
                 'Platform heated\nPress the button to finish')
        return dict(text=message,body=message,support=None,diagram=None,language=language,
                    descriptor=None,text_id=None,sprite='activity:heat_bed',state=state,
                    reason=str(status.get('reason') or ''),
                    can_confirm=status.get('can_confirm') is True,
                    can_cancel=status.get('can_cancel') is True)
    descriptor=({'WAIT_CONFIRM':'0x8021d38'} if owner=='m300_maintenance' else
        {'WAIT_INSERT':'0x8021eb8','LOADING':'0x8021ea0',
         'UNLOADING':'0x8021eac','WAIT_UNLOAD':'0x8021ec4'}).get(state)
    if owner=='m300_filament' and state=='COMPLETING':
        descriptor='0x8021eac' if operation=='UNLOAD' else '0x8021ea0'
    record=assets()['descriptors'].get(descriptor)
    if record:
        message=text(record['text_id'],language)
        sprite='0x%08x'%int(record['sprite'],16)
    elif state in ('HEATING','REHEATING'):
        message,sprite=text(123,language),'0x0801c2b8'
    else:
        # Only interruption/completion states are port additions. In normal
        # OEM flows completion returns directly to the invoking submenu.
        pl=language=='PL'
        message=({'COMPLETE':('Zakończono','Complete'),
                  'CANCELLED':('Anulowano','Cancelled'),
                  'CANCELLING':('Zatrzymywanie. Proszę czekać','Stopping. Please wait'),
                  'FAULT':('Błąd procedury','Procedure fault')}.get(state,(state,state)))[not pl]
        if state=='FAULT' and status.get('reason'):
            message+='\n'+str(status['reason'])
        sprite='0x0801be48' if state=='FAULT' else '0x0801fe34'
    return dict(text=message,body=message,support=None,diagram=None,
        language=language,descriptor=descriptor,
        text_id=record['text_id'] if record else 123 if state in ('HEATING','REHEATING') else None,
        sprite=sprite,state=state,reason=str(status.get('reason') or ''),
        can_confirm=status.get('can_confirm') is True,can_cancel=status.get('can_cancel') is True)
