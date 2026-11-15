# M300 Classic RC10

Klipper automatycznie synchronizuje licznik czasu druku M300 Classic z MCU
1.0.5. Gdy drukarka jest bezczynna i zgromadzi się co najmniej pełna minuta,
Klipper oblicza nową wartość licznika i przekazuje ją do MCU. MCU sprawdza
fabryczny rekord na płycie i warunki zapisu, aktualizuje ID0 we własnej pamięci
Flash i weryfikuje zapis. Klipper odczytuje wynik, uzgadnia dziennik i zachowuje pozostałe sekundy
do kolejnej synchronizacji.

## Aktualizacja działającej instalacji

Poczekaj na stan Ready, zakończ wydruk i procedury oraz wyłącz cele obu grzałek.
Uruchom z konta Klippera:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Jeśli masz już MCU 1.0.5, wystarczy zaktualizować hosta. Pełna paczka RC10
zawiera aplikację MCU w `MCU/M300_SD.zip`. RC10 przyjmuje i ignoruje stary wpis
`factory_counter_backup:`. Synchronizacja działa bez pliku zrzutu Flash i
bez edycji `printer.cfg`. Zachowaj dotychczasowy stan licznika Klippera i
dziennik synchronizacji.

[Pierwsza instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.10/docs/pl/FIRST_INSTALL.md) · [Pełna instrukcja aktualizacji](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.10/docs/pl/INSTALL.md) · [MCU i odczyt stanu licznika](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.10/docs/pl/MCU_FIRMWARE_1.0.5.md)

## Sprawdzenie licznika

W Fluidd użyj `ZORTRAX_HARDWARE_STATUS`, aby sprawdzić synchronizację i banki,
oraz `ZORTRAX_INFO REFRESH=0`, aby odczytać czas fabryczny, oczekujący i łączny.
Po udanej synchronizacji `factory_counter_sync` zwraca `SYNCED`. Jeśli MCU nie udostępnia
poleceń licznika podczas pracy, Klipper dalej zlicza nowy czas druku
lokalnie na hoście.

Testy programowe sprawdzają synchronizację i odzyskiwanie z dziennika.
Automatyczny zapis ID0 i odzyskiwanie po odcięciu zasilania pozostają do
sprawdzenia na fizycznej drukarce M300 Classic. Ilustracje OLED z beta.20
pokazują historyczną kompilację.
[Rejestr odbiorów](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.10/docs/pl/ACCEPTANCE_REGISTER.md).
