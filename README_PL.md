# Zortrax M300 Classic — Klipper 1.0.3

[![Test przepływu na M300 Classic w zakładce Device OrcaSlicera. Fluidd pokazuje temperatury i podgląd OLED drukarki.](docs/img/m300-orcaslicer-fluidd-printing.png)](docs/img/m300-orcaslicer-fluidd-printing.png?raw=true)

*Wydruk na M300 Classic, 20 listopada 2026 r. W konsoli oraz na podglądzie OLED widać aktywną siatkę `m300_pads`. Kliknij obraz, aby otworzyć oryginał.*

[English](README.md) · [Podręcznik obsługi](docs/pl/USER_GUIDE.md) · [Pobierz 1.0.3](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.3)

Port wykorzystuje oryginalny sterownik **Zortrax M300 Classic**, jego OLED, pokrętło i płytę kontaktową. Bieżąca para to host **1.0.3** i MCU **1.0.9**. Fluidd działa na porcie **4480**. W 1.0.3 nazwy 36 makr operatorskich zaczynają się od `M300_`. Zapisane pliki G-code nadal mogą wywoływać poprzednie nazwy `ZORTRAX_`.

[Opcjonalna temperatura hosta](docs/pl/HOST_TEMPERATURE.md): niezależne include i wykresy Host oraz MCU; pozostałe strefy Orange Pi odczytywane na żądanie.

## Instalacja i obsługa

Na **nowym hoście z KIAUH** pobierz repozytorium i uruchom instalator poniżej
jako użytkownik użyty do KIAUH. Wdraża pełnego Klippera, konfigurację M300,
makra i gotowe Fluidd. Stare Pi ani prywatna kopia konfiguracji nie są potrzebne.
Ta ścieżka obsługuje Debian 13 Trixie z Pythonem 3.13.
Przykład dotyczy UART2 w Orange Pi Zero 4; dla innej płytki wybierz jej włączony
UART oraz baud zgodny z bootloaderem/MCU drukarki.

```bash
git clone --branch orange-pi --single-branch https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper.git "$HOME/m300-src" &&
cd "$HOME/m300-src" &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-new-host.py --serial /dev/ttyS2 --baud 750000 --apply
```

KIAUH musi wcześniej przygotować po jednej instancji Klippera, Moonrakera i
Fluidd. Instalator używa ostatniej sprawdzonej publikacji `orange-pi`, weryfikuje
rdzeń, sprawdza pełną konfigurację offline i zachowuje kopię zastępowanego
szablonu. Pełna instrukcja poniżej opisuje wgranie MCU i kalibrację drukarki.

| Co chcesz zrobić | Instrukcja |
|---|---|
| Przygotować nowy Orange Pi lub Raspberry Pi | [Pierwsza instalacja, UART, pełny ZIP i pierwsze uruchomienie](docs/pl/FIRST_INSTALL.md) |
| Zaktualizować działającą drukarkę lub naprawić pustą stronę | [Aktualizacja hosta, naprawa Fluidd i przywrócenie poprzedniej instalacji](docs/pl/INSTALL.md) |
| Wgrać MCU przez posiadany bootloader | [Aplikacja na SD i kontrola wersji](docs/pl/MCU_FIRMWARE_1.0.9.md) · [Paczka MCU](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.9) |
| Przygotować płytę i wydruk z OrcaSlicera | [Poziomowanie i mesh](docs/pl/BED_MESH_AND_LEVELING.md) · [Komendy START i END](docs/pl/PRINT_CONTROL.md) · [Profile OrcaSlicera](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Orca-Slicer) |
| Zrobić pauzę, zmienić kolor i wznowić | [Podręcznik operatora](docs/pl/USER_GUIDE.md) · [Filament i przepłukiwanie dyszy](docs/pl/MAINTENANCE_MATERIAL.md) |
| Obsługiwać OLED i makra we Fluidd | [Sterowanie](docs/pl/RC1_UI.md) · [Katalog makr](docs/pl/MACRO_REFERENCE.md) · [65 ilustrowanych ekranów](docs/pl/OLED_FUNCTIONS.md) |
| Dodać opcjonalną kamerę USB | [Włączenie, wyłączenie i konfiguracja kamery w Fluidd](docs/pl/CAMERA.md) |
| Sprawdzić parametry, błędy i stan odbioru | [Parametry techniczne](docs/pl/TECHNICAL_REFERENCE.md) · [Diagnostyka](docs/pl/USER_GUIDE.md#9-rozpoznawanie-problemów) · [Rejestr prób sprzętowych](docs/pl/ACCEPTANCE_REGISTER.md) |

## Opcjonalne temperatury

Instalator nowego hosta instaluje moduły diagnostyczne oraz oba pliki konfiguracji.
Domyślnie są wyłączone. Nie trzeba kopiować dodatku z osobnego ZIP.
Przed włączeniem temperatury STM32 wgraj dołączony `MCU/M300APP.M3B` przez
posiadany bootloader SD. W `printer.cfg` odkomentuj wybrane opcje:

```ini
[include m300_host_temperature.cfg]
[include m300_mcu_temperature.cfg]
```

W konsoli Fluidd wykonaj `FIRMWARE_RESTART`. Każdy aktywny include dodaje
wykres **Host** lub **MCU**. Temperaturę STM32 odczytasz też poleceniem `M300_MCU_TEMPERATURE`,
a pozostałe strefy Orange Pi przez SSH: `python3 read-host-temperatures.py`
z katalogu klonu. Wyłączenie: ponownie zakomentuj odpowiedni include.
[Instrukcja temperatur](docs/pl/HOST_TEMPERATURE.md) opisuje ścieżki i korektę pomiaru.
MCU 1.0.9 przeszedł weryfikację programową; odczyt na drukarce wymaga próby sprzętowej.

## Aktualizacja działającego Orange Pi

Zakończ wydruk lub procedurę, poczekaj na stan Ready i wyłącz cele obu grzałek. Wykonaj poniższe polecenia w swoim klonie gałęzi `orange-pi`. W przykładzie podano katalog domyślny.

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

W konsoli Fluidd wpisz `ZORTRAX_INFO REFRESH=0`, aby odczytać wersję hosta oraz MCU. Polecenie instalatora aktualizuje hosta. Osobne ścieżki dla pierwszego klonowania, uszkodzonego repozytorium i naprawy strony na porcie 4480 podaje instrukcja aktualizacji.

## Wydanie finalne z 24.11.2026

1.0.3 zawiera poprawki restartu po meshu i anulowania procedur z 24.11.2026. Walidacja tej zmiany jest programowa; próby sprzętowe wcześniejszych wersji nie stanowią odbioru 1.0.3. Na drukarce pozostaje sprawdzenie sekwencji mesh → SAVE_CONFIG → Ready oraz Cancel → parkowanie → nowy plik, a także przyczyny osobnego błędu grzania ekstrudera z dostarczonego logu.

[Audyt końcowy](docs/pl/AUDYT_FINAL_2026-11-21.md) · [Opis 1.0.3](docs/pl/RELEASE_v1.0.3.md) · [Wyniki kompilacji i testów](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/actions/workflows/build-m300.yml) · [Rejestr odbiorów](docs/pl/ACCEPTANCE_REGISTER.md) · [Źródła i licencje](THIRD_PARTY_NOTICES.md)
