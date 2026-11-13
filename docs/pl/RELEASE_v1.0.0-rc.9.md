# M300 Classic RC9

RC9 poprawia instalator Orange Pi i automatyczną synchronizację czasu druku.
Przed ponowieniem zapisu Flash Klipper upewnia się, że oczekująca transakcja
jest trwale zapisana. Po zatwierdzeniu przez MCU odczytuje ID0 i uzgadnia
dziennik lokalny. Chwilowy błąd synchronizacji katalogu dziennika podczas
uzgadniania nie ukrywa już łącznego czasu druku. Sekundy z niepełnej minuty
pozostają na hoście do następnej synchronizacji.

MCU 1.0.5 ogranicza pracę przy sprawdzaniu powtórzonej transakcji i zachowuje
weryfikację obu etapów przełączenia banku oraz zapisanej wartości. Usunięto
deweloperskie polecenie pomiaru czasu OLED RLE z hosta i MCU. Podgląd OLED
korzysta z tej samej kompresji RLE.
[Szczegóły MCU 1.0.5](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/pl/MCU_FIRMWARE_1.0.5.md).

## Instalacja i aktualizacja

Na nowym hoście użyj [instrukcji pierwszej instalacji](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/pl/FIRST_INSTALL.md).
Do aktualizacji istniejącego klonu poczekaj na stan Ready, zakończ druk,
ruchy i procedury oraz wyłącz oba cele grzania:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Instalator sprawdza istniejący Fluidd na 4480. Jeśli zaktualizowany host nie
uruchomi się lub nie osiągnie Ready, instalator przywraca poprzednie pliki
hosta. [Instrukcja aktualizacji](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/pl/INSTALL.md)
opisuje także pierwsze klonowanie gałęzi i sprawdzenie instalacji.

Aplikację MCU 1.0.5 wgraj osobno z `MCU/M300_SD.zip` przez posiadany
bootloader SD. Dotychczasowy wpis `factory_counter_backup:` nadal obowiązuje.
Przy pierwszym włączeniu skorzystaj z instrukcji MCU. Stan synchronizacji
sprawdzisz przez `ZORTRAX_HARDWARE_STATUS`, a czas druku odczytasz przez
`ZORTRAX_INFO REFRESH=0`.

## Weryfikacja

Testy programowe obejmują aktualizację działającej instalacji, wycofanie zmian
po błędzie pierwszej instalacji, uzgadnianie licznika oraz symulowane przerwania
zapisu MCU. Automatyczny zapis ID0 i zachowanie po przerwaniu zapisu Flash
pozostają do sprawdzenia na rzeczywistej płycie. Ilustracje OLED z beta.20
przedstawiają historyczną kompilację.
[Rejestr odbiorów](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/pl/ACCEPTANCE_REGISTER.md).
