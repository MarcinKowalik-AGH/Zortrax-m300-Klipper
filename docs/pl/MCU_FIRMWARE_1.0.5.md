# M300 Classic MCU 1.0.5

[Pierwsza instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/pl/FIRST_INSTALL.md) · [Opis RC9](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/pl/RELEASE_v1.0.0-rc.9.md) · [ZIP na kartę SD i sumy SHA-256](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.5)

## Wgraj aplikację z karty SD

Sprawdź `M300_MCU_v1.0.5_SD.zip` według sumy kontrolnej wydania.
Rozpakuj `M300APP.M3B` do głównego katalogu karty i użyj procedury
aktualizacji aplikacji przez bootloader, który jest już w M300 Classic.
Aplikacja zaczyna się pod adresem `0x08008000`. Usuń plik aktualizacji przed
kolejnymi uruchomieniami. Po osiągnięciu Ready sprawdź `mcu_release: 1.0.5`
w `ZORTRAX_MCU_STATUS`.

## Włączenie i odczyt

W istniejącej sekcji `[m300_mcu]` podaj w `factory_counter_backup:` ścieżkę
bezwzględną do sprawdzonej pełnej kopii Flash tej płyty (256 KiB). Klipper
porównuje numer seryjny w kopii z numerem podłączonej płyty. Po dodaniu lub
zmianie wpisu raz uruchom ponownie Klippera. Od tego momentu Klipper
synchronizuje oczekujące pełne minuty automatycznie po spełnieniu warunków
zapisu.

MCU odczytuje aktywny rekord ID0, sprawdza poprzednią wartość, zapisuje nową
w drugim banku ustawień i weryfikuje ją. Fabryczny numer seryjny i rewizja
płyty zajmują osobną stronę Flash. MCU wymaga bezczynności osi, wyłączenia
grzałek, aktualnych odczytów ADC i sygnału heartbeat. Nieruchoma oś Z może
pozostać pod napięciem. Od 50 °C na hotendzie MCU wymaga ciągłego chłodzenia
radiatora. Do czasu zapisu Klipper zachowuje oczekujący czas lokalnie.

Wynik `ZORTRAX_HARDWARE_STATUS` zawiera
`factory_counter_runtime_supported`, `factory_counter_sync`,
`factory_counter_banks` i `factory_counter_pending`. `SYNCED` potwierdza
zweryfikowany wynik, a `AWAITING_IDLE` wskazuje odroczony zapis.
`ZORTRAX_INFO REFRESH=0` pokazuje fabryczny, lokalny i łączny czas druku.
Przy stanie `RECOVERY_REQUIRED` zachowaj dziennik Klippera potrzebny do
uzgodnienia transakcji. Po odzyskaniu sprawdź
`factory_counter_banks: NORMALIZED` i `factory_counter_pending: false`.

Kompilacja 1.0.5 usuwa deweloperskie polecenie pomiaru czasu OLED RLE.
Interfejs licznika oraz warunki ruchu i temperatury przed zapisem zachowują
dotychczasowe działanie. Symulowane przerwania zapisu sprawdzają odzyskiwanie
banków. Próba odcięcia zasilania na drukarce pozostaje do wykonania.
