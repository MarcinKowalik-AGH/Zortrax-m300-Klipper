# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure M07 operator view. Actions retain the displayed session and phase."""

def format_view(status, view, language='EN'):
    pl = language == 'PL'
    token, phase = view
    current = (status.get('session_token'), status.get('phase_id')) == tuple(view)
    state = status.get('state')
    point_names = (('Przod prawy', 'Przod lewy', 'Srodek', 'Tyl prawy', 'Tyl lewy')
                   if pl else ('Front right', 'Front left', 'Center', 'Rear right', 'Rear left'))
    phases = {
        'IDLE': ('Gotowy do regulacji', 'Ready for leveling'),
        'WAIT_PREPARE': ('Oczysc dysze i pola kontaktowe. Przygotuj dostep do srub.',
                         'Clean nozzle and contact pads. Prepare access to screws.'),
        'HEATING': ('Nagrzewanie dyszy. Nie dotykaj.', 'Heating nozzle. Do not touch.'),
        'HOMING': ('Bazowanie XYZ przed pomiarem.', 'Homing XYZ before measurement.'),
        'PROBING': ('Pomiar platformy. Nie dotykaj.', 'Measuring platform. Keep clear.'),
        'WAIT_RETRY': ('Rozrzut probek jest za duzy. Sprawdz dysze i pole kontaktowe.',
                       'Samples disagree. Check nozzle and contact pad.'),
        'ADJUST': ('Wyreguluj wskazana srube i potwierdz.', 'Adjust this screw, then confirm.'),
        'REVIEW': ('Pomiar zakonczony. Sprawdz odchylki i zatwierdz zapis.',
                   'Measurement complete. Review deviations and confirm saving.'),
        'COMPLETE': ('Wynik zapisany.', 'Observation saved.'),
        'CANCELLED': ('Anulowano. Nowy wynik nie zostal zapisany.', 'Cancelled. No new result saved.'),
        'FAULT': ('Blad procedury. Nowy wynik nie zostal zatwierdzony.',
                  'Procedure fault. No new result confirmed.')}
    rows = [(phases.get(state, (str(state), str(state)))[0 if pl else 1], None)]
    if not current:
        rows.append(('Etap sie zmienil: odswiez widok.' if pl else 'Phase changed: refresh this view.', None))
    point = status.get('point_id')
    if type(point) is int and 0 <= point < len(point_names):
        rows.append((('Punkt: ' if pl else 'Point: ') + point_names[point], None))
    instruction = status.get('instruction')
    if isinstance(instruction, dict):
        names = {'rear_left': ('Tylna lewa', 'Rear left'),
                 'rear_right': ('Tylna prawa', 'Rear right'), 'front': ('Przednia', 'Front')}
        screw = names.get(instruction.get('screw'), ('?', '?'))[0 if pl else 1]
        action = (('Dokrec' if pl else 'Tighten') if instruction.get('action') == 'TIGHTEN'
                  else ('Poluzuj' if pl else 'Loosen'))
        rows += [(('Sruba: ' if pl else 'Screw: ') + screw, None),
                 ('%s: %.2f %s, %s' % (action, instruction.get('turns', 0.),
                  'obr.' if pl else 'turns', instruction.get('direction', '?')), None),
                 ('CW: zgodnie z zegarem; CCW: przeciwnie.' if pl else
                  'CW: clockwise; CCW: counterclockwise.', None)]
    review = status.get('review')
    if isinstance(review, list) and len(review) == 5:
        rows.append(('Odchylki od referencji [mm]:' if pl else 'Deviations from reference [mm]:', None))
        rows.extend(('%s: %+.4f' % (point_names[p], review[p]), None) for p in range(5))
        if status.get('center_policy') == 'REPORT_ONLY':
            rows.append(('Srodek: wynik do oceny operatora.' if pl else 'Center: result for operator review.', None))
    if status.get('retry_count'):
        rows.append((('Ponowienia probek: ' if pl else 'Sample retries: ') +
                     '%s/%s' % (status['retry_count'], status.get('max_sample_retries')), None))
    if status.get('reason'):
        rows.append((str(status['reason']), None))
    rows.append(('Odswiez etap' if pl else 'Refresh phase', ('cal_refresh',)))
    confirm = {'WAIT_PREPARE': ('Rozpocznij pomiar', 'Start measurement'),
               'ADJUST': ('Regulacja wykonana', 'Adjustment done'),
               'WAIT_RETRY': ('Powtorz ten punkt', 'Repeat this point'),
               'REVIEW': ('Zapisz wynik', 'Save observation')}
    if state in confirm:
        rows.append((confirm[state][0 if pl else 1], ('cal_confirm', token, phase)
                     if current and status.get('can_confirm') is True else None))
    rows.append(('Anuluj' if pl else 'Cancel', ('cal_cancel', token, phase)
                 if current and status.get('can_cancel') is True else None))
    return rows
