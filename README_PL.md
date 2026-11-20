# Zortrax M300 Classic — Klipper 1.0.0-rc.33

[![Test przepływu na M300 Classic w zakładce Device OrcaSlicera. Fluidd pokazuje temperatury i podgląd OLED drukarki.](docs/img/m300-orcaslicer-fluidd-printing.png)](docs/img/m300-orcaslicer-fluidd-printing.png?raw=true)

*Wydruk na M300 Classic, 20 listopada 2026 r. W konsoli oraz na podglądzie OLED widać aktywną siatkę `m300_pads`. Kliknij obraz, aby otworzyć oryginał.*

[English](README.md) · [Podręcznik obsługi](docs/pl/USER_GUIDE.md) · [Pobierz RC33](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.0-rc.33)

Port wykorzystuje oryginalny sterownik **Zortrax M300 Classic**, jego OLED, pokrętło i płytę kontaktową. Bieżąca para to host **1.0.0-rc.33** i MCU **1.0.8**. Fluidd działa na porcie **4480**. Po zmianie koloru RC33 proponuje dogrzanie dyszy, gdy grzałka przeszła w tryb czuwania. Ręczne cofnięcie po sprawdzeniu wypływu wymaga ponownego potwierdzenia przed wznowieniem.

## Instalacja i obsługa

| Co chcesz zrobić | Instrukcja |
|---|---|
| Przygotować nowy Orange Pi lub Raspberry Pi | [Pierwsza instalacja, UART, pełny ZIP i pierwsze uruchomienie](docs/pl/FIRST_INSTALL.md) |
| Zaktualizować działającą drukarkę lub naprawić pustą stronę | [Aktualizacja hosta, naprawa Fluidd i przywrócenie poprzedniej instalacji](docs/pl/INSTALL.md) |
| Wgrać MCU przez posiadany bootloader | [Aplikacja na SD i kontrola wersji](docs/pl/MCU_FIRMWARE_1.0.8.md) · [Paczka MCU](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.8) |
| Przygotować płytę i wydruk z OrcaSlicera | [Poziomowanie i mesh](docs/pl/BED_MESH_AND_LEVELING.md) · [Komendy START i END](docs/pl/PRINT_CONTROL.md) · [Profile OrcaSlicera](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Orca-Slicer) |
| Zrobić pauzę, zmienić kolor i wznowić | [Podręcznik operatora](docs/pl/USER_GUIDE.md) · [Filament i przepłukiwanie dyszy](docs/pl/MAINTENANCE_MATERIAL.md) |
| Obsługiwać OLED i makra we Fluidd | [Sterowanie](docs/pl/RC1_UI.md) · [Katalog makr](docs/pl/MACRO_REFERENCE.md) · [65 ilustrowanych ekranów](docs/pl/OLED_FUNCTIONS.md) |
| Sprawdzić parametry, błędy i stan odbioru | [Parametry techniczne](docs/pl/TECHNICAL_REFERENCE.md) · [Diagnostyka](docs/pl/USER_GUIDE.md#9-rozpoznawanie-problemów) · [Rejestr prób sprzętowych](docs/pl/ACCEPTANCE_REGISTER.md) |

## Aktualizacja działającego Orange Pi

Zakończ wydruk lub procedurę, poczekaj na stan Ready i wyłącz cele obu grzałek. Wykonaj poniższe polecenia w swoim klonie gałęzi `orange-pi`. W przykładzie podano katalog domyślny.

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

W konsoli Fluidd wpisz `ZORTRAX_INFO REFRESH=0`, aby odczytać wersję hosta oraz MCU. Polecenie instalatora aktualizuje hosta. Osobne ścieżki dla pierwszego klonowania, uszkodzonego repozytorium i naprawy strony na porcie 4480 podaje instrukcja aktualizacji.

## Stan przed wydaniem finalnym

RC33 jest kandydatem do wydania. Operator potwierdził ukończenie Benchy, opuszczenie stołu i parkowanie po zakończeniu wydruku oraz obsługę filamentu z OLED i Fluidd. Rejestr podaje zakres każdej obserwacji. Do odbioru na maszynie pozostają m.in. powtarzalność kontaktowego Z, pierwsza warstwa na całej płycie oraz ręczne przepłukanie i wznowienie na RC33.

[Opis RC33](docs/pl/RELEASE_v1.0.0-rc.33.md) · [Wyniki kompilacji i testów](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/actions/workflows/build-m300.yml) · [Rejestr odbiorów](docs/pl/ACCEPTANCE_REGISTER.md) · [Źródła i licencje](THIRD_PARTY_NOTICES.md)
