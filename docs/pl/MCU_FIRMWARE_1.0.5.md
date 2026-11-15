# M300 Classic MCU 1.0.5

[Pierwsza instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.10/docs/pl/FIRST_INSTALL.md) · [Opis RC10](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.10/docs/pl/RELEASE_v1.0.0-rc.10.md) · [ZIP na kartę SD i sumy SHA-256](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.5)

## Wgraj aplikację z karty SD

Sprawdź `M300_MCU_v1.0.5_SD.zip` według sumy kontrolnej wydania.
Rozpakuj `M300APP.M3B` do głównego katalogu karty i użyj procedury
aktualizacji aplikacji przez bootloader, który jest już w M300 Classic.
Aplikacja zaczyna się pod adresem `0x08008000`. Usuń plik aktualizacji przed
kolejnymi uruchomieniami. Po osiągnięciu Ready sprawdź `mcu_release: 1.0.5`
w `ZORTRAX_MCU_STATUS`.

## Odczyt licznika

Klipper RC10 synchronizuje licznik automatycznie z dotychczasową konfiguracją.
RC9 używał wpisu `factory_counter_backup:` do autoryzacji zapisu. RC10
przyjmuje ten wpis i synchronizuje licznik bez odczytu zrzutu Flash. Zachowaj
dotychczasowy stan licznika i dziennik Klippera. Dla domyślnej ścieżki `[m300_nvm]` dziennik
to `~/printer_data/config/m300_settings.json.runtime-sync`.

MCU odczytuje aktywny rekord ID0, sprawdza poprzednią wartość, zapisuje nową
w drugim banku ustawień i weryfikuje ją. Fabryczny numer seryjny i rewizja
płyty zajmują osobną stronę Flash. MCU wymaga bezczynności osi, wyłączenia
grzałek, aktualnych odczytów ADC i sygnału heartbeat. Nieruchoma oś Z może
pozostać pod napięciem. Od 50 °C na hotendzie MCU wymaga ciągłego chłodzenia
radiatora. Do czasu zapisu Klipper zachowuje oczekujący czas lokalnie.

Wynik `ZORTRAX_HARDWARE_STATUS` zawiera
`factory_counter_runtime_supported`, `factory_counter_sync`,
`factory_counter_banks` i `factory_counter_pending`. `SYNCED` potwierdza
zweryfikowany zapis. `CURRENT` oznacza, że nie ma pełnej minuty do
przekazania, a `AWAITING_IDLE` wskazuje odroczony zapis.
`ZORTRAX_INFO REFRESH=0` pokazuje fabryczny, lokalny i łączny czas druku.
Przy stanie `RECOVERY_REQUIRED` zachowaj dziennik Klippera potrzebny do
uzgodnienia transakcji. Po odzyskaniu sprawdź
`factory_counter_banks: NORMALIZED` i `factory_counter_pending: false`.

Kompilacja 1.0.5 usuwa deweloperskie polecenie pomiaru czasu OLED RLE.
Interfejs licznika oraz warunki ruchu i temperatury przed zapisem zachowują
dotychczasowe działanie. Symulowane przerwania zapisu sprawdzają odzyskiwanie
banków. Próba odcięcia zasilania na drukarce pozostaje do wykonania.
