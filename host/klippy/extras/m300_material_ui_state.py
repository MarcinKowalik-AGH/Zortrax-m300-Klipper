# SPDX-License-Identifier: GPL-3.0-or-later
"""M09 pure presentation contract for M03 material-session snapshots.

No hardware, reactor, motion, heater, NVM or G-code imports. M03 remains
sole owner of transport, deadlines and operator-confirmation tokens.
"""
from dataclasses import dataclass

PHASES = frozenset({'IDLE','WAIT_PAUSE','HEATING','REHEATING','WAIT_INSERT',
    'LOADING','WAIT_UNLOAD','WAIT_REMOVE','UNLOADING','WAIT_PURGE','PURGING',
    'COMPLETING','COMPLETE','CANCELLING','CANCELLED','FAULT'})
OPERATIONS = frozenset({'LOAD','UNLOAD','CHANGE'})
MESSAGES = {
 'IDLE':'Choose material operation', 'WAIT_PAUSE':'Pausing print safely',
 'HEATING':'Heating nozzle', 'REHEATING':'Reheating nozzle',
 'WAIT_INSERT':'Insert filament, then confirm', 'WAIT_UNLOAD':'Remove filament, then confirm',
 'WAIT_REMOVE':'Retraction finished; remove filament, then confirm',
 'WAIT_PURGE':'Inspect extrusion: confirm finish or purge',
 'LOADING':'Feeding filament in bounded steps', 'UNLOADING':'Retracting filament in bounded steps',
 'PURGING':'Purging bounded amount', 'COMPLETING':'Completing material operation',
 'COMPLETE':'Material operation completed', 'CANCELLING':'Stopping material operation',
 'CANCELLED':'Material operation cancelled', 'FAULT':'Material fault — manual inspection required',
}
class MaterialUiError(ValueError): pass


def view_from_status(status):
    if not isinstance(status,dict) or status.get('state') not in PHASES:
        raise MaterialUiError('missing or invalid M03 material state')
    state=status['state']
    op=status.get('operation')
    if op is not None and op not in OPERATIONS:
        raise MaterialUiError('invalid material operation')
    token=status.get('session_token'); phase=status.get('phase_id')
    if type(token) is not int or type(phase) is not int or token<0 or phase<0:
        raise MaterialUiError('invalid material token or phase')
    if type(status.get('busy')) is not bool or type(status.get('ready')) is not bool:
        raise MaterialUiError('incomplete M03 ownership status')
    if any(type(status.get(k)) is not bool for k in ('can_confirm','can_purge','can_cancel')):
        raise MaterialUiError('incomplete M03 operator permissions')
    if state!='WAIT_PURGE' and status['can_purge']:
        raise MaterialUiError('purge permission in invalid phase')
    if state not in ('WAIT_INSERT','WAIT_UNLOAD','WAIT_REMOVE','WAIT_PURGE') and status['can_confirm']:
        raise MaterialUiError('confirmation permission in invalid phase')
    return {'state':state,'operation':op,'message':MESSAGES[state],
        'token':token,'phase':phase,'busy':status['busy'],'ready':status['ready'],
        'actions': tuple(a for a,ok in (
           ('CONFIRM',status['can_confirm']),('PURGE',status['can_purge']),
           ('CANCEL',status['can_cancel'])) if ok),
        'remaining_mm':status.get('remaining_budget_mm'),
        'reason':status.get('reason','')}


def check_operator_action(view, action, token, phase):
    if action not in ('CONFIRM','PURGE','CANCEL'):
        raise MaterialUiError('invalid M09 operator action')
    if type(token) is not int or type(phase) is not int:
        raise MaterialUiError('invalid confirmation identity')
    if view['token'] != token or view['phase'] != phase:
        raise MaterialUiError('stale material confirmation')
    if action not in view['actions']:
        raise MaterialUiError('operator action not currently permitted')
    return action
