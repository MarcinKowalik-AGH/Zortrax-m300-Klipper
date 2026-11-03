# SPDX-License-Identifier: GPL-3.0-or-later
"""English OEM fan menu and manual platform presentation; no hardware access."""
from functools import lru_cache

from .m300_leveling_oem import draw_text

FAN_LABELS = ('Back', 'Toggle upper fan', 'Toggle lower fan')
PLATFORM_LABELS = {'PLATFORM_UP': 'Move the platform up',
                   'PLATFORM_DOWN': 'Move the platform down'}


def describe(owner, status):
    if not status.get('native_control'):
        return None
    if owner == 'm300_fans' and status.get('operation') == 'FAN_TEST':
        state = status.get('state')
        if state in ('FAULT','COMPLETE','CANCELLED','IDLE'):
            title = 'Fan test failed' if state == 'FAULT' else 'Fan test ended'
            reason = str(status.get('reason') or '')
            return dict(kind='fan_result',title='Fan test',text=title+('\n'+reason if reason else ''))
        upper = '(Cooling)' if status.get('upper_cooling') else (
            '(Enabled)' if status.get('upper_enabled') else '(Disabled)')
        lower = '(Enabled)' if status.get('lower_enabled') else '(Disabled)'
        labels = (FAN_LABELS[0], FAN_LABELS[1]+' '+upper, FAN_LABELS[2]+' '+lower)
        note = 'Automatic upper-fan cooling' if status.get('upper_cooling') else ''
        return dict(kind='fan_menu', title='Fan test', labels=labels,
                    text='\n'.join((*labels, note) if note else labels),
                    upper=upper, lower=lower, note=note)
    operation = status.get('operation')
    if owner == 'm300_maintenance' and operation in PLATFORM_LABELS:
        message=PLATFORM_LABELS[operation]
        if status.get('state')=='FAULT':
            message+='\n'+str(status.get('reason') or 'Platform movement failed')
        return dict(kind='platform', title='Maintenance', text=message)
    return None


@lru_cache(maxsize=24)
def fan_frame(upper, lower, note, selected, frame_type):
    """0x08018c4c + 0x0801846c layout, verified against all 12 cold frames."""
    frame = frame_type()
    for x, y, label in ((16, 0, FAN_LABELS[0]), (20, 12, FAN_LABELS[1]),
                        (20, 24, FAN_LABELS[2]), (190, 12, upper), (190, 24, lower)):
        draw_text(frame, x, y, label)
    center = 12*selected+7
    for y in range(64):
        if abs(y-center) > 2:
            frame.pixel(8, y)
    for dy in range(-2, 3):
        frame.pixel(8+(-1 if selected == 0 else 1)*(3-abs(dy)), center+dy)
    if note:
        draw_text(frame, 16, 48, note)
    return frame.wire_bytes()
