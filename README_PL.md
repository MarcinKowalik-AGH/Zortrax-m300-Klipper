# Zortrax M300 Classic — Klipper 1.0.0-rc.9

**RC9** aktualizuje instalator Orange Pi i synchronizację czasu druku z MCU. [Opis wydania](docs/pl/RELEASE_v1.0.0-rc.9.md) · [Animacje menu z RC6](docs/pl/RELEASE_v1.0.0-rc.6.md).

**MCU 1.0.5:** [zapis licznika, zgodność i zakres testów](docs/pl/MCU_FIRMWARE_1.0.5.md). [Osobny ZIP aplikacji](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.5).

**Dziewiąty kandydat do wydania dla klasycznego M300**, z oryginalną płytą,
wyświetlaczem OLED, pokrętłem, czujnikami i stołem kontaktowym. To nie jest port
dla M300 Plus, M300 Dual ani Inventure. Język interfejsu: angielski. [English](README.md).

[Wydanie RC9](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.0-rc.9) · [Pierwsza instalacja](docs/pl/FIRST_INSTALL.md) · [Aktualizacja działającej instalacji](docs/pl/INSTALL.md) · [OLED i makra](docs/pl/RC1_UI.md) · [Instrukcja z 65 ekranami](docs/pl/OLED_FUNCTIONS.md)

## Funkcje

Natywny ruch Klippera, bazowanie kontaktowe Z, autokalibracja platformy, zapisane
profile mesh, mapy temperatur odzyskane z firmware, wspólne START/PAUSE/RESUME/
CANCEL/END, obsługa filamentu i wentylatorów z niezależnym chłodzeniem ochronnym.
START aktywuje wybraną siatkę po homingu i wykonuje 2 linie Y oraz 2 linie X.
Menu korzysta z oryginalnych grafik i wspólnie cieniowanych ikon. Podgląd OLED we Fluidd
zachowuje szybki kanał nawigacji i kwadratowe piksele przy skali ×1/×2/×3.

Ustawienia OLED i makra Fluidd prowadzą do tych samych funkcji. Dodano
bezpośrednie skróty jasności OLED i LED. Usunięto laboratoryjne menu Service /
Tests i zbędne przyciski testowe. Rzeczywisty test wentylatorów OEM, PID i odczyt
diagnostyki pozostają. [Katalog makr](docs/pl/MACRO_REFERENCE.md) · [Procedury druku](docs/pl/PRINT_CONTROL.md).

**Zachowane grafiki RC3:** jednolity raster 24 dodatkowych ikon dla hosta, MCU i Fluidd, bez rozmycia i bez progowania. Oryginalne bitmapy OEM zachowują fabryczne odcienie. [Rendery, instrukcja i testy](docs/pl/RELEASE_v1.0.0-rc.3.md).

## Aktualizacja Orange Pi

Jeśli masz już klon gałęzi w `~/m300-orange-pi`, poczekaj na stan Ready,
zakończ wydruk lub procedurę i wyłącz cele grzania:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Instalator sprawdza działający Fluidd na porcie 4480 i zachowuje
konfigurację UART, mesh, PID i ustawienia osi Z. Po aktualizacji
odśwież Fluidd z pominięciem pamięci podręcznej.
[Pełna instrukcja aktualizacji i pierwszego klonowania](docs/pl/INSTALL.md) ·
[Aktualizacja MCU 1.0.5 i odczyt licznika](docs/pl/MCU_FIRMWARE_1.0.5.md).

## Stan odbioru

Pierwsza próba użytkownika potwierdza nagrzanie, homing i rozpoczęcie druku.
[Rejestr odbiorów](docs/pl/ACCEPTANCE_REGISTER.md) zawiera potwierdzenia oraz
pozostałe próby pełnego wydruku i pauzy/wznowienia. Wariant Z=-0,5,
M07 5/6,5/1 i odsunięcie kontaktu 2 mm pozostaje świadomą konfiguracją
sprawdzonego egzemplarza, nie ustawieniem narzucanym innym drukarkom.

[Parametry i planer](docs/pl/PRINT_LIMITS_AND_PLANNER.md) · [Mesh i poziomowanie](docs/pl/BED_MESH_AND_LEVELING.md) · [Instalator i retry CI](docs/pl/INSTALLATION_AND_CI.md) · [Przegląd kodu RC1](docs/pl/CODE_REVIEW_RC1.md)

Publikację poprzedzają regresje hosta, natywny Klippy, kompilacja ARM, testy
Fluidd i przeglądarek, migracja/rollback oraz sprawdzenie sum. Błędy testów nie
są maskowane ponowieniami. Dane źródłowe firmware, wcześniejsze wydania i
65 ilustracji beta.20 zachowano z oznaczeniem pochodzenia. Nie dodano
niezweryfikowanego czyszczenia w strefie Y315 ani ruchów z FORCE_MOVE.
