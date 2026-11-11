# Rejestr odbiorów i problemów M300 Classic

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
| Synchronizacja zaznaczenia OLED–Fluidd | beta.16–20 | Ocena użytkownika po przyspieszeniu kanału nawigacji | Potwierdzone UI: Odświeżanie zostało zaakceptowane; brak pomiaru opóźnienia w ms. | — |
| Skala ×1/×2/×3, centrowanie, kolor i przyciski pod HIDE | beta.20 | Ocena wyglądu przez użytkownika po zmianie układu | Potwierdzone UI: Efekt zaakceptowany w kontekście beta.20; nie oznacza odbioru całej drukarki. | — |
| Stały port interfejsu Fluidd | konfiguracja użytkownika | Deklaracja po przeniesieniu interfejsu na port 4480 | Uzgodniona konfiguracja: 4480 jest portem obowiązującym; to nie wynik testu nowego instalatora. | — |
| Ostre ikony OEM i aktywności | beta.22 | Oględziny fizycznego OLED po instalacji SHARP-HOST-1 | Oczekuje na test: Wersja opublikowana, brak potwierdzenia wyglądu. | — |
| Tune → przygotowanie / All / Calibrate / kolejność grafik | beta.18+ | Osobne wejście suwakiem, All bez mesh, Calibrate z mesh | Oczekuje na test: Poprawka istnieje; brak osobnego potwierdzenia całej sekwencji. | — |
| Pomiar pól i pokazanie profilu m300_pads | 0.13.16.38 / test 11.11.2026 | Odczyt m300_pads i GET_POSITION przy X3/Y10 | Obserwacja częściowa: Notatka: siatka 61×61, min=-0,4497, max=0,0965; lokalna korekcja -0,369086 mm. | Nie jest to nowy pomiar w CI ani odbiór pierwszej warstwy. |
| Powtarzalność kontaktowego Z | beta.22 / konfiguracja egzemplarza | Powtarzane bazowanie na rozgrzanym egzemplarzu | Oczekuje na test: Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano. | — |
| Zapis, restart i aktywacja mesh | beta.22 / konfiguracja egzemplarza | Pomiar → SAVE_CONFIG → restart → START z profilem | Oczekuje na test: Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano. | — |
| Pierwsza warstwa na większej części stołu | beta.22 / konfiguracja egzemplarza | Środek oraz okolice narożników | Oczekuje na test: Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano. | — |
| START i cztery linie 2Y+2X | 0.13.16.38 / test 11.11.2026 | Ponowny start po korekcie -0,5 / 6,5 | Obserwacja częściowa: Użytkownik potwierdził nagrzanie, homing i rozpoczęcie druku. | Nie potwierdza ukończenia Benchy, jakości pierwszej warstwy ani osobnej obserwacji wszystkich czterech linii. |
| PAUSE i parkowanie | beta.22 / konfiguracja egzemplarza | Próba z OLED oraz przycisku Fluidd | Oczekuje na test: Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano. | — |
| RESUME | beta.22 / konfiguracja egzemplarza | Dogrzanie i bezkolizyjny powrót do tego samego pliku | Oczekuje na test: Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano. | — |
| CANCEL w druku, przygotowaniu i pauzie | 0.13.16.38 / test 11.11.2026 | CANCEL_PRINT po nieudanym starcie | Obserwacja częściowa: Głowica zaparkowała; STATUS Ready, PRINT_CONTROL_STATUS IDLE i busy=false. | Pozostałe fazy anulowania i RESUME wymagają osobnego testu. |
| END i ponowne zadanie | beta.22 / konfiguracja egzemplarza | Normalne ukończenie i uruchomienie kolejnego pliku | Oczekuje na test: Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano. | — |
| Zmiana filamentu w pauzie | beta.22 / konfiguracja egzemplarza | Wycofanie, ładowanie, wypływ, osobne RESUME | Oczekuje na test: Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano. | — |
| Stabilność dłuższego wydruku | beta.22 / konfiguracja egzemplarza | Ruch, grzanie, OLED, Fluidd i kontrola logów łącza | Oczekuje na test: Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano. | — |
| Przepływ i profile Orca | beta.22 / konfiguracja egzemplarza | Pomiary dla konkretnego materiału, dyszy i temperatury | Oczekuje na test: Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano. | — |
| Rzeczywista karta SD i pliki Z-Suite M300 | beta.22 / konfiguracja egzemplarza | Import i nadzorowany druk reprezentatywnych plików | Oczekuje na test: Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano. | — |
| Nowy instalator i zapamiętanie portu | beta.23 | Aktualizacja → odczyt FLUIDD_ENDPOINT_SELECTED → ponowne wywołanie | Oczekuje na test: Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano. | — |
| Kwalifikowany wariant Z pierwszego wydruku | 0.13.16.38 / test 11.11.2026 | Nastawy istniejącego egzemplarza | Uzgodniona konfiguracja: position_min=-0,5; safe_z=5; approach_distance=6,5; probe_search_margin=1. | Nie jest globalnym standardem dla innych egzemplarzy. |
| Rzeczywiste odsunięcie PC7 2 mm w homingu | 0.13.16.38 / test 11.11.2026 | Deklarowane zmniejszenie odsunięcia PC7 | Obserwacja częściowa: Użytkownik podał wystarczające odsunięcie 2 mm. Kod beta.24 usuwa wymuszony próg 5 mm. | Odbiór nowego kodu, powtarzalności i pełnego M07 jeszcze oczekuje. |

## Historia i źródła potwierdzeń

### OLED_NAV — Synchronizacja zaznaczenia OLED–Fluidd

**2026-11-10 · beta.16–20 · Potwierdzone UI**

Odświeżanie zostało zaakceptowane; brak pomiaru opóźnienia w ms.

Zapis użytkownika / treść przesłanego zrzutu: „ok teraz jest ok z odświeraniem w kliperze .”.

Podstawa wersji: `conversation_context_not_device_report`.

### OLED_LAYOUT — Skala ×1/×2/×3, centrowanie, kolor i przyciski pod HIDE

**2026-11-10 · beta.20 · Potwierdzone UI**

Efekt zaakceptowany w kontekście beta.20; nie oznacza odbioru całej drukarki.

Zapis użytkownika / treść przesłanego zrzutu: „jest ok . zaktualizuj github i manuale oraz instrukcje w kontekście dzisiejszych poprawke.”.

Podstawa wersji: `conversation_context_not_device_report`.

### FLUIDD_PORT — Stały port interfejsu Fluidd

**2026-11-10 · konfiguracja użytkownika · Uzgodniona konfiguracja**

4480 jest portem obowiązującym; to nie wynik testu nowego instalatora.

Zapis użytkownika / treść przesłanego zrzutu: „tak od teraz ten port będzie obowiązywał”.

Podstawa wersji: `explicit_user_setting`.

### OLED_SHARP — Ostre ikony OEM i aktywności

**2026-11-10 · beta.21 · Odrzucony wygląd**

Cieniowanie odrzucone jako rozmazane.

Zapis użytkownika / treść przesłanego zrzutu: „nie nie wyszło to najlepiej i ikony sa rozmazane.”.

Podstawa wersji: `conversation_context_not_device_report`.

**2026-11-10 · beta.22 · Oczekuje na test**

Wersja opublikowana, brak potwierdzenia wyglądu.

Podstawa wersji: `conversation_context_not_device_report`.

### TUNE — Tune → przygotowanie / All / Calibrate / kolejność grafik

**2026-11-10 · beta.18+ · Oczekuje na test**

Poprawka istnieje; brak osobnego potwierdzenia całej sekwencji.

Podstawa wersji: `conversation_context_not_device_report`.

### MESH_MEASURE — Pomiar pól i pokazanie profilu m300_pads

**2026-11-10 · wersja z chwili zrzutu niepotwierdzona · Obserwacja częściowa**

Widoczny wynik pomiaru i utworzony nieaktywny profil.

Zapis użytkownika / treść przesłanego zrzutu: „Profile m300_pads created. Compensation remains inactive until loaded.”.

Podstawa wersji: `user_screenshot_version_unknown`.

**2026-11-11 · 0.13.16.38 / test 11.11.2026 · Obserwacja częściowa**

Notatka: siatka 61×61, min=-0,4497, max=0,0965; lokalna korekcja -0,369086 mm.

Materiał źródłowy: `docs/evidence/M300_FIRST_PRINT_USER_REPORT_2026-11-11.md`.

Podstawa wersji: `user_note_controller_revision_not_release_readback`.

### Z_REPEAT — Powtarzalność kontaktowego Z

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

### MESH_PERSIST — Zapis, restart i aktywacja mesh

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

### FIRST_LAYER — Pierwsza warstwa na większej części stołu

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

### PRINT_START — START i cztery linie 2Y+2X

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

**2026-11-11 · 0.13.16.38 / test 11.11.2026 · Błąd na sprzęcie**

Ruch purge X3/Y10/Z0,28 odrzucony: po korekcji Z=-0,089086 przy position_min=0.

Zapis użytkownika / treść przesłanego zrzutu: „Move out of range: 3.000 10.000 -0.089 [0.000]”.

Materiał źródłowy: `docs/evidence/M300_FIRST_PRINT_USER_REPORT_2026-11-11.md`.

Podstawa wersji: `user_note_controller_revision_not_release_readback`.

**2026-11-11 · 0.13.16.38 / test 11.11.2026 · Obserwacja częściowa**

Użytkownik potwierdził nagrzanie, homing i rozpoczęcie druku.

Zapis użytkownika / treść przesłanego zrzutu: „po zapisaniu tych nastaw drukarka rozpoczęła druk”.

Materiał źródłowy: `docs/evidence/M300_FIRST_PRINT_USER_REPORT_2026-11-11.md`.

Podstawa wersji: `user_note_controller_revision_not_release_readback`.

### PRINT_PAUSE — PAUSE i parkowanie

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

### PRINT_RESUME — RESUME

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

### PRINT_CANCEL — CANCEL w druku, przygotowaniu i pauzie

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

**2026-11-11 · 0.13.16.38 / test 11.11.2026 · Obserwacja częściowa**

Głowica zaparkowała; STATUS Ready, PRINT_CONTROL_STATUS IDLE i busy=false.

Zapis użytkownika / treść przesłanego zrzutu: „CANCEL_PRINT zadziałał: głowica zaparkowała”.

Materiał źródłowy: `docs/evidence/M300_FIRST_PRINT_USER_REPORT_2026-11-11.md`.

Podstawa wersji: `user_note_controller_revision_not_release_readback`.

### PRINT_END — END i ponowne zadanie

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

### FILAMENT_CHANGE — Zmiana filamentu w pauzie

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

### LONG_PRINT — Stabilność dłuższego wydruku

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

### FLOW_PROFILE — Przepływ i profile Orca

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

### SD_ZCODE — Rzeczywista karta SD i pliki Z-Suite M300

**2026-11-10 · beta.22 / konfiguracja egzemplarza · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

### UPDATE23 — Nowy instalator i zapamiętanie portu

**2026-11-10 · beta.23 · Oczekuje na test**

Brak jawnego wyniku sprzętowego w dostępnej rozmowie; nie oznacza, że funkcji nie zaimplementowano.

Podstawa wersji: `conversation_context_not_device_report`.

### FIRST_PRINT_Z_PROFILE — Kwalifikowany wariant Z pierwszego wydruku

**2026-11-11 · 0.13.16.38 / test 11.11.2026 · Uzgodniona konfiguracja**

position_min=-0,5; safe_z=5; approach_distance=6,5; probe_search_margin=1.

Materiał źródłowy: `docs/evidence/M300_FIRST_PRINT_USER_REPORT_2026-11-11.md`.

Podstawa wersji: `user_note_controller_revision_not_release_readback`.

### PC7_CLEARANCE_2 — Rzeczywiste odsunięcie PC7 2 mm w homingu

**2026-11-11 · 0.13.16.38 / test 11.11.2026 · Obserwacja częściowa**

Użytkownik podał wystarczające odsunięcie 2 mm. Kod beta.24 usuwa wymuszony próg 5 mm.

Zapis użytkownika / treść przesłanego zrzutu: „zmniejszyłem też przy homingu odsunięcie stołu żeby rozłaczyć kontakt z 5 na 2 bo to wystarcza”.

Materiał źródłowy: `docs/evidence/M300_FIRST_PRINT_USER_REPORT_2026-11-11.md`.

Podstawa wersji: `explicit_user_message_after_attached_note`.

## Jak aktualizować

```bash
python3 ci/acceptance_register.py --write
python3 ci/acceptance_register.py --check
```

Plik Markdown jest generowany z JSON; test sprawdza zgodność obu. Nie zmienia
stanu drukarki ani nie publikuje sam wyników. Dla prób ruchu i grzania wymagany
jest nadzór fizyczny; sama lista nie jest instrukcją odłączania czujników ani
omijania zabezpieczeń. Nowy zgłoszony problem zawsze otrzymuje osobne zdarzenie.
