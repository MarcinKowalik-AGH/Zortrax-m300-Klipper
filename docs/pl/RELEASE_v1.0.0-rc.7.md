# M300 RC7 — licznik czasu druku

RC7 rejestruje fazę drukowania modelu w zadaniach ukończonych, anulowanych i przerwanych. Standardowa sekwencja M300 pomija nagrzewanie, linie czyszczące, pauzy i parkowanie. Podczas druku licznik zawiesza pomiar przy oczekiwaniu na temperaturę w `M109`, `M190` i `TEMPERATURE_WAIT`, po wykonaniu ruchów z kolejki. W niestandardowym G-code zegar startuje przy pierwszym poleceniu ruchu z ekstruzją, więc linia czyszcząca dodana przez slicer może uruchomić pomiar wcześniej, a postój wewnątrz fazy druku wlicza się do czasu. `Information` pokazuje fabryczny numer seryjny i czas łączny, w którym minuty zapisane w MCU są liczone raz. `ZORTRAX_INFO` dodatkowo zwraca czas druku Klippera i czas oczekujący na synchronizację. Nagłe odcięcie zasilania może spowodować utratę czasu od ostatniego zapisu na Orange Pi, planowanego co 15 sekund podczas druku.

Opcjonalna synchronizacja z MCU 1.0.3 zapisuje pełne minuty do fabrycznego rekordu ID0 przy starcie, przed konfiguracją drukarki. Reszta sekund zostaje na Orange Pi. Host zapisuje transakcję powiązaną z numerem seryjnym przed wysłaniem polecenia zapisu. Po ponownym połączeniu może potwierdzić albo ponowić tę samą transakcję. Firmware używa naprzemiennie banków `0x0803E800` i `0x0803F000`. Buduje i odczytuje nowy bank z zachowaniem pozostałych ustawień fabrycznych. Po sprawdzeniu aktywacji usuwa poprzedni bank. Numer seryjny i dane wersji sprzętu są na osobnej stronie `0x0803F800`.

## Aktualizacja i włączenie zapisu

Zaktualizuj Orange Pi, gdy drukarka jest bezczynna i ma stan Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Licznik na Orange Pi działa z dotychczasową wersją MCU. Przed włączeniem synchronizacji wykonaj zgodnie z procedurą dwa niezależne odczyty pełnego Flash płyty od `0x08000000` do `0x0803FFFF`. Każdy surowy plik powinien mieć 262144 bajty. Porównaj odczyty poleceniem `cmp` i zachowaj kopię z SHA-256 poza drukarką. Host sprawdza rozmiar, wektory startowe, fabryczny numer seryjny i stan banków zapisanych w kopii. [Procedura kopii Flash](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Boot-Loader/blob/156daf4d1d5f14d2f0e553a64b352397be397745/docs/en/v1.4/original-backup.md).

Wgraj aplikację MCU 1.0.3 z `MCU/M300_SD.zip`, korzystając z [instrukcji aktualizacji MCU](MCU_FIRMWARE_1.0.3.md). W istniejącej sekcji konfiguracji drukarki na Orange Pi dodaj ścieżkę:

```ini
[m300_mcu]
factory_counter_backup: /pełna/ścieżka/do/m300-full-flash.bin
```

W bezczynności wykonaj `FIRMWARE_RESTART`, aby zsynchronizować zgromadzony czas. Stan zapisu pokazuje `ZORTRAX_HARDWARE_STATUS`. Zachowaj kopię i pliki licznika Orange Pi razem z konfiguracją. Ilustracje OLED z beta.20 są materiałem historycznym.

## Powrót do firmware’u fabrycznego

Przed uruchomieniem wersji 1.3.1 dokończ ewentualny zapis w RC7 na Orange Pi i MCU. W `ZORTRAX_HARDWARE_STATUS` sprawdź `factory_counter_banks: NORMALIZED` i `factory_counter_pending: false`. Jeżeli zasilanie zaniknie podczas aktywacji lub kasowania, firmware fabryczny może skasować oba banki po wykryciu dwóch aktywnych albo określonych nieprawidłowych nagłówków. Jeśli RC7 nie przywróci prawidłowego układu banków, zweryfikuj i odtwórz banki NVM z kopii zgodnie z procedurą serwisową, przed uruchomieniem aplikacji fabrycznej. Samo przywrócenie aplikacji pozostawia strony ustawień w zastanym stanie. Próba zaniku zasilania i powrotu do wersji fabrycznej na fizycznej płycie pozostają do wykonania.

[Audyt NVM na Google Drive](https://drive.google.com/file/d/171nuuE6n2x6FsBrVq8lLBb6I_-sS_4p8/view) · [Powrót przez Bootloader 1.4](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Boot-Loader/blob/156daf4d1d5f14d2f0e553a64b352397be397745/docs/en/v1.4/installation.md#restore-app-before-normal-use)
