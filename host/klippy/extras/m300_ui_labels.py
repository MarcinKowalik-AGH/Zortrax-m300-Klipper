# SPDX-License-Identifier: GPL-3.0-or-later
"""English presentation of legacy panel labels; actions and data stay intact.

This deliberately does not split arbitrary strings at '/': file paths, numeric
ratios and identifiers are data. Only the known bilingual UI labels are mapped.
"""

from .m300_release import VERSION


EXACT = {
    'Adjust this screw, then confirm.': 'Adjust screw; then confirm.',
    'Measuring platform. Keep clear.': 'Probing platform. Keep clear.',
    'Long press: return to menu': 'Long press: status screen',
    'M09: material controls': 'Material controls',
    'Stock menu atlas / M11': 'Original menu reference',
    'OLED link / M10': 'OLED link',
    'M300_CLASSIC / M11': 'Zortrax M300 Classic',
    '0.11.0-LAB / 2026-10-26': 'Host '+VERSION,
    'Etap: P01 LAB': 'Host '+VERSION,
    'M300 Klipper / M03 LAB': 'M300 Classic / Klipper',
    'M10 OLED link': 'OLED link',
    'LAB: hardware still unqualified': 'Hardware acceptance pending',
    'select an explicit HOTEND temperature first': 'Select a nozzle temperature first.',
    'select an explicit BED temperature first': 'Select a bed temperature first.',
    'm300_calibration is not configured': 'Platform leveling unavailable. Module not configured.',
    'm300_motion is not configured': 'Motion unavailable. Module not configured.',
    'm300_filament is not configured': 'Filament unavailable. Module not configured.',
    'm300_sd is not configured': 'SD card unavailable. Module not configured.',
    'Job / Zadanie': 'Job', 'Diagnostics / Diagnostyka': 'Diagnostics',
    'Nozzle clean: confirm / Dysza czysta': 'Confirm nozzle clean',
    'Confirm / Potwierdz': 'Confirm', 'Purge / Wyczysc': 'Purge',
    'Cancel / Anuluj': 'Cancel', 'Refresh / Odswiez': 'Refresh',
    'Home XYZ / Bazowanie': 'Home XYZ', 'Move Z / Ruch Z z enkodera': 'Move Z',
    'Motion status / Stan ruchu': 'Motion status',
    'Refresh phase / Odswiez etap': 'Refresh phase', 'Board / Płyta': 'Board',
    'Release, then hold + rotate': 'Release, then hold + turn',
    'Zwolnij, przytrzymaj i obracaj': 'Hold and turn to move Z',
    'Puszczenie: stop i koniec ruchu': 'Release to stop Z',
    'BRAK MODUŁU': 'NOT INSTALLED', 'BRAK STATUSU': 'STATUS UNAVAILABLE',
    'Panel nie obsługuje tej akcji': 'Action unavailable on this panel',
    'Brak poprawnego statusu zadania': 'Job status unavailable',
    'Brak poprawnego statusu usługi filamentu': 'Filament status unavailable',
    'Moduł m300_job nie jest skonfigurowany': 'Job module not configured',
    'Moduł m300_filament nie jest skonfigurowany': 'Filament module not configured',
    'Sesja zmieniła się. Otwórz Zadanie ponownie.': 'Session changed. Reopen Job.',
    'Sesja zmieniła się. Otwórz Filament ponownie.': 'Session changed. Reopen Filament.',
    'Panel nie jest gotowy. Poczekaj na pełną inicjalizację.': 'Panel not ready. Wait for initialization.',
    'Brak poprawnego statusu usługi filamentu; wznowienie zablokowane':
        'Filament status unavailable; resume blocked',
    'Etap zmienił się. Wybierz Odśwież etap przed kolejną akcją.':
        'Phase changed. Select Refresh phase before the next action.',
    'Żądanie nie zostało przyjęte': 'Request rejected',
    'Brak poprawnego identyfikatora etapu filamentu': 'Filament phase ID unavailable',
    'Nie, wróć': 'Back', 'Tak, anuluj': 'Confirm cancel',
    'Anulować zadanie?': 'Cancel job?', 'Anulować usługę filamentu?': 'Cancel filament?',
    'Anulowanie kończy tę sesję': 'Cancellation ends this session',
    'Anulowanie kończy tę usługę': 'Cancellation ends this operation',
    'Stan i dostępność akcji według m300_job': 'Actions follow the current job state',
    'Stan i dostępność akcji według m300_filament': 'Actions follow the current filament state',
    'UWAGA: gorąca głowica. Nie dotykaj dyszy.': 'Hot nozzle. Do not touch.',
    'Pauza': 'Pause', 'Wznów': 'Resume', 'Anuluj...': 'Cancel...',
    'Potwierdź': 'Confirm', 'Przepchnij': 'Purge', 'Anuluj usługę...': 'Cancel operation...',
    'Odśwież etap': 'Refresh phase', 'Diagnostyka M300': 'M300 diagnostics',
    'Stan płyty': 'Board status', 'Temperatury': 'Temperatures',
    'Wejścia / pokrętło': 'Inputs / encoder', 'Informacje': 'Information',
    'Zadanie': 'Job', 'Odczyt temperatur': 'Temperatures', 'Wejścia M300': 'M300 inputs',
    'Diagnostyka, zadanie, filament': 'Diagnostics, job, filament',
    'Bez prób fizycznych': 'Hardware not yet qualified',
    'Obrót: wybór; klik: wejście': 'Turn: select; click: open',
    'Przytrzymanie: menu główne': 'Hold: status screen',
}

PREFIXES = {
    'Stan / State: ': 'State: ', 'State / Stan: ': 'State: ',
    'Axes / Osie: ': 'Axes: ', 'Odmowa: ': 'Rejected: ',
    'Niedostępne w fazie ': 'Unavailable in phase ',
    'Najpierw zakończ usługę filamentu: ': 'Finish filament operation first: ',
    'Brak aktywnej usługi filamentu (': 'No active filament operation (',
    'Postęp: ': 'Progress: ', 'Faza: ': 'State: ', 'Plik: ': 'File: ',
    'Sesja: ': 'Session: ', 'Cel dyszy: ': 'Nozzle target: ',
    'Cel stołu: ': 'Bed target: ', 'Czas fazy: ': 'Phase time: ',
    'Zadanie: ': 'Job: ', 'Operacja: ': 'Operation: ',
    'Etap: ': 'Phase: ', 'Dysza: ': 'Nozzle: ', 'Stół: ': 'Bed: ',
    'Uzbrojona: ': 'Armed: ', 'Błąd: ': 'Fault: ',
    'Enkoder: ': 'Encoder: ', 'Błędy przejść: ': 'Invalid transitions: ',
}


def english_label(value):
    value = ' '.join(str(value or '').split())[:240]
    if value.startswith('M300 menu: '):
        value = value[11:]
    blocked = False
    for suffix in (' [blokada]', ' [unavailable]'):
        if value.endswith(suffix):
            blocked = True
            value = value[:-len(suffix)]
            break
    if value in EXACT:
        value = EXACT[value]
    elif value.startswith('Przyjęto ') and value.endswith('; oczekiwanie na zmianę fazy'):
        value = 'Accepted ' + value[9:].split(';', 1)[0] + '; waiting for phase change'
    else:
        for old, new in PREFIXES.items():
            if value.startswith(old):
                # The suffix is a filename, state, number or owner reason.
                value = new + value[len(old):]
                break
    # These substitutions apply only to fixed diagnostic rows, not filenames.
    if value.startswith('PC5: '):
        value = value.replace('BRAK ODCZYTU', 'NO SAMPLE').replace('wciśnięty', 'pressed').replace('zwolniony', 'released')
    if value in ('Nozzle: brak czujnika', 'Bed: brak czujnika'):
        value = value.replace('brak czujnika', 'sensor missing')
    if value in ('File: brak', 'Operation: brak'):
        value = value.replace('brak', 'none')
    if value.startswith(('State: ', 'Job: ', 'Filament: ')):
        value = value.replace('BRAK MODUŁU', 'NOT INSTALLED').replace('BRAK STATUSU', 'STATUS UNAVAILABLE')
    return value + (' [unavailable]' if blocked else '')
