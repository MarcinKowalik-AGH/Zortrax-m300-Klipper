# SPDX-License-Identifier: GPL-3.0-or-later
"""M07 rows use the same recovered text as the modal OLED and Fluidd."""
from .m300_leveling_oem import describe


def format_view(status, view, language='EN'):
    token, phase = view
    current = (status.get('session_token'), status.get('phase_id')) == tuple(view)
    screen = describe(status, language)
    rows = [(line, None) for line in screen['text'].split('\n')]
    if screen['diagram'] is not None:
        rows.extend(('%s: %.1f mm' % (p, screen['diagram'][p]), None) for p in (4, 3, 2, 1, 0))
    pl = language == 'PL'
    rows.append(('Odśwież' if pl else 'Refresh', ('cal_refresh',)))
    if screen['can_confirm']:
        rows.append(('Kontynuuj' if pl else 'Continue',
                     ('cal_confirm', token, phase) if current else None))
    if screen['can_cancel']:
        rows.append(('Anuluj' if pl else 'Cancel',
                     ('cal_cancel', token, phase) if current else None))
    return rows
