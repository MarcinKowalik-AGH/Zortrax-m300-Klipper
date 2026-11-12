# Zortrax M300 Classic — Klipper 1.0.0-rc.3

**Trzeci kandydat do wydania dla klasycznego M300**, z oryginalną płytą,
wyświetlaczem OLED, pokrętłem, czujnikami i stołem kontaktowym. To nie jest port
dla M300 Plus, M300 Dual ani Inventure. Język interfejsu: angielski. [English](README.md).

[Wydanie RC3](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.0-rc.3) · [Pierwsza instalacja](docs/pl/FIRST_INSTALL.md) · [OLED i makra RC1](docs/pl/RC1_UI.md) · [Instrukcja z 65 ekranami](docs/pl/OLED_FUNCTIONS.md)

## Funkcje

Natywny ruch Klippera, bazowanie kontaktowe Z, autokalibracja platformy, zapisane
profile mesh, mapy temperatur odzyskane z firmware, wspólne START/PAUSE/RESUME/
CANCEL/END, obsługa filamentu i wentylatorów z niezależnym chłodzeniem ochronnym.
START aktywuje wybraną siatkę po homingu i wykonuje 2 linie Y oraz 2 linie X.
Menu korzysta z oryginalnych grafik i wspólnie cieniowanych ikon. Podgląd OLED we Fluidd
zachowuje szybki kanał nawigacji i kwadratowe piksele przy skali ×1/×2/×3.

W RC1 ustawienia OLED i makra Fluidd prowadzą do tych samych funkcji. Dodano
bezpośrednie skróty jasności OLED i LED. Usunięto laboratoryjne menu Service /
Tests i zbędne przyciski testowe. Rzeczywisty test wentylatorów OEM, PID i odczyt
diagnostyki pozostają. [Katalog makr](docs/pl/MACRO_REFERENCE.md) · [Procedury druku](docs/pl/PRINT_CONTROL.md).

**RC3:** jednolity raster 24 dodatkowych ikon dla hosta, MCU i Fluidd, bez rozmycia i bez progowania. Oryginalne bitmapy OEM zachowują fabryczne odcienie. [Rendery, instrukcja i testy](docs/pl/RELEASE_v1.0.0-rc.3.md).

## Aktualizacja Orange Pi

Wyłącznie przy bezczynnej drukarce Ready, bez aktywnego ani wstrzymanego wydruku:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Instalator sprawdza i zapamiętuje istniejący port Fluidd. Zachowuje mesh, PID,
UART, własną konfigurację oraz zapisane ustawienia kwalifikowanego Z. Nie omijaj
odmowy nadpisania nieznanego kodu ani SHA256SUMS. Po instalacji odśwież Fluidd
przez Cmd+Shift+R. Pakiet używa nazw M300_HOST, M300_FLUIDD.zip i MCU/M300_SD.zip.
Do pełnego ujednolicenia ikon należy osobno wgrać [MCU 1.0.1](docs/pl/MCU_FIRMWARE_1.0.1.md) z [ZIP-a](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.1). Instalator hosta nie flashuje MCU. Wcześniejsze aplikacje są nadal zgodne protokołowo, ale zachowują starsze grafiki autonomiczne. Information pokazuje krótkie wersje; diagnostyka zachowuje identyfikatory ABI.

## Stan odbioru

RC1 jest kandydatem do wydania, a nie deklaracją ukończenia wszystkich prób
sprzętowych. Notatka użytkownika potwierdza nagrzanie, homing i rozpoczęcie druku,
nie cały Benchy ani pełny odbiór pierwszej warstwy. [Rejestr odbiorów](docs/pl/ACCEPTANCE_REGISTER.md)
zachowuje osobno potwierdzenia, problemy i testy oczekujące. Wariant Z=-0,5,
M07 5/6,5/1 i odsunięcie kontaktu 2 mm pozostaje świadomą konfiguracją
sprawdzonego egzemplarza, nie ustawieniem narzucanym innym drukarkom.

[Parametry i planer](docs/pl/PRINT_LIMITS_AND_PLANNER.md) · [Mesh i poziomowanie](docs/pl/BED_MESH_AND_LEVELING.md) · [Instalator i retry CI](docs/pl/INSTALLATION_AND_CI.md) · [Przegląd kodu RC1](docs/pl/CODE_REVIEW_RC1.md)

Publikację poprzedzają regresje hosta, natywny Klippy, kompilacja ARM, testy
Fluidd i przeglądarek, migracja/rollback oraz sprawdzenie sum. Błędy testów nie
są maskowane ponowieniami. Dane źródłowe firmware, wcześniejsze wydania i
65 ilustracji beta.20 zachowano z oznaczeniem pochodzenia. Nie dodano
niezweryfikowanego czyszczenia w strefie Y315 ani ruchów z FORCE_MOVE.
