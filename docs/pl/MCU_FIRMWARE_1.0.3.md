# M300 Classic MCU 1.0.3

[Instalacja](FIRST_INSTALL.md) · [Opis RC7](RELEASE_v1.0.0-rc.7.md) · [Wydanie MCU i ZIP na SD](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.3)

MCU 1.0.3 dodaje wersjonowane polecenie zapisu całkowitego czasu druku na
oryginalnej płycie STM32F103 klasycznego M300. Fabryczny numer seryjny i rewizję
płyty można nadal odczytać. Host RC7 zlicza czas również ze starszą zgodną
aplikacją MCU i zachowuje lokalnie czas oczekujący na zapis.

## Weryfikacja przed włączeniem zapisu

Zachowaj pełną kopię 256 KiB pamięci Flash konkretnej płyty. Sprawdź, czy plik
daje się odczytać i zawiera właściwy numer seryjny. Host RC7 wymaga pełnego
obrazu pod ścieżką bezwzględną podaną w `factory_counter_backup:` w sekcji
`[m300_mcu]`, zanim zleci zapis. Taki wpis włącza funkcję dla tej drukarki.
`ZORTRAX_HARDWARE_STATUS` pokazuje stan synchronizacji. Zachowaj kopię do
ewentualnego odtworzenia.

Zapis może nastąpić przed konfiguracją MCU. Host zgłasza oczekujący czas po
uruchomieniu nieskonfigurowanego MCU, również po wydaniu
`FIRMWARE_RESTART` przy bezczynnej drukarce. Drugi blok jest zapisywany
i sprawdzany przed aktywacją. Testy programowe symulują awarie zapisu
i obejmują kompilację dla ARM. Odczyt po zapisie na rzeczywistej płycie
i kontrolowane odcięcie zasilania pozostają próbami sprzętowymi tego wydania.

## Pakiet aplikacji na kartę SD

ZIP zawiera plik `M300APP.M3B`. Sprawdź sumę kontrolną wydania i użyj
procedury aktualizacji aplikacji posiadanego zgodnego bootloadera M300.
Aplikacja zaczyna się pod adresem `0x08008000`. Działającą instalację
aktualizuj przy bezczynnej i ostudzonej drukarce. Po wgraniu sprawdź wersję
`1.0.3` w `ZORTRAX_MCU_STATUS` oraz numer seryjny i licznik w
`ZORTRAX_INFO REFRESH=0`.
