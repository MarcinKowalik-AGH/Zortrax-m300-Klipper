#!/usr/bin/env python3
"""Validate and render a hardware-acceptance ledger without controlling hardware."""
import argparse
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATUSES={'CONFIRMED_UI':'Potwierdzone UI','CONFIGURATION_CONFIRMED':'Uzgodniona konfiguracja',
          'PARTIAL_OBSERVATION':'Obserwacja częściowa','REJECTED_VISUAL':'Odrzucony wygląd',
          'AWAITING_TEST':'Oczekuje na test','CONFIRMED_HARDWARE':'Potwierdzone na sprzęcie',
          'FAILED_HARDWARE':'Błąd na sprzęcie'}


def validate(data):
    assert data['schema']==1 and data['printer']=='M300_CLASSIC'
    ids=set()
    for feature in data['features']:
        assert feature['id'] not in ids;ids.add(feature['id'])
        assert feature['function'] and feature['events']
        for event in feature['events']:
            assert event['status'] in STATUSES
            for key in ('date','version','version_basis','test','result'):
                assert isinstance(event[key],str) and event[key]
            proof=event['evidence']
            if event['status']!='AWAITING_TEST':
                assert proof['kind'] in ('user_message','user_test_log','user_screenshot')
                assert proof.get('quote') or proof.get('artifact')
            else:
                assert proof['kind']=='no_hardware_confirmation'
    return len(ids)


def cell(value):return str(value).replace('|','\\|').replace('\n',' ')


def render(data):
    validate(data)
    text='''# Rejestr odbiorów i problemów M300 Classic

[Instrukcja główna](../../README_PL.md) · [Obsługa druku](PRINT_CONTROL.md) · [Dane źródłowe rejestru](../reports/HARDWARE_ACCEPTANCE.json)

**To jedyna bieżąca lista odbiorów sprzętowych.** Wynik kompilacji ani testu CI
nie wypełnia jej automatycznie jako PASS. Wersje opisane jako kontekst rozmowy
nie są odczytem faktycznie zainstalowanej wersji z drukarki. Puste potwierdzenie
pozostaje oczekujące — nie oznacza braku implementacji. Żadnego nowego ruchu,
grzania, pomiaru ani oględzin nie wykonano przy tworzeniu tego rejestru.

Przy kolejnym teście dopisz zdarzenie do odpowiedniej funkcji w JSON: data,
wersja odczytana z urządzenia, co wykonano, wynik, problem i źródło potwierdzenia.
Nie usuwaj poprzednich wyników. Wcześniejszego „zaakceptowano” nie zamieniaj na
„niezrobione” tylko dlatego, że wydano nową wersję; regresję zapisuj osobno.

| Funkcja | Wersja / podstawa | Test | Ostatni wynik | Problem / granica |
|---|---|---|---|---|
'''
    for f in data['features']:
        e=f['events'][-1]
        text+='| '+' | '.join(cell(x) for x in (f['function'],e['version'],e['test'],
                 STATUSES[e['status']]+': '+e['result'],e.get('problem') or '—'))+' |\n'
    text+='\n## Historia i źródła potwierdzeń\n'
    for f in data['features']:
        text+='\n### '+f['id']+' — '+f['function']+'\n'
        for e in f['events']:
            text+=f"\n**{e['date']} · {e['version']} · {STATUSES[e['status']]}**\n\n{e['result']}\n"
            if e['evidence'].get('quote'):
                text+='\nZapis użytkownika / treść przesłanego zrzutu: „'+e['evidence']['quote']+'”.\n'
            text+='\nPodstawa wersji: `'+e['version_basis']+'`.\n'
    text+='''
## Jak aktualizować

```bash
python3 ci/acceptance_register.py --write
python3 ci/acceptance_register.py --check
```

Plik Markdown jest generowany z JSON; test sprawdza zgodność obu. Nie zmienia
stanu drukarki ani nie publikuje sam wyników. Dla prób ruchu i grzania wymagany
jest nadzór fizyczny; sama lista nie jest instrukcją odłączania czujników ani
omijania zabezpieczeń. Nowy zgłoszony problem zawsze otrzymuje osobne zdarzenie.
'''
    return text


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write',action='store_true');p.add_argument('--check',action='store_true')
    args=p.parse_args()
    source=ROOT/'docs/reports/HARDWARE_ACCEPTANCE.json'
    dest=ROOT/'docs/pl/ACCEPTANCE_REGISTER.md'
    data=json.loads(source.read_text());text=render(data)
    if args.write:dest.write_text(text)
    if args.check:assert dest.read_text()==text,'Regenerate acceptance register from JSON'
    print(json.dumps(dict(status='PASS_ACCEPTANCE_REGISTER',features=len(data['features']),
                          physical_tests_executed=False)))

if __name__=='__main__':main()
