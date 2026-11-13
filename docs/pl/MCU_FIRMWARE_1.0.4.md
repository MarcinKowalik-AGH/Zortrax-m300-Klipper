# M300 Classic MCU 1.0.4

[Instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.8/docs/pl/FIRST_INSTALL.md) · [Opis RC8](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.8/docs/pl/RELEASE_v1.0.0-rc.8.md) · [Wydanie MCU i ZIP na SD](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.4)

MCU 1.0.4 udostępnia procedury licznika po konfiguracji, w bezczynności. `m300_factory_counter_query_runtime` zwraca numer seryjny, aktywny bank i wartość ID0. `m300_factory_counter_commit_runtime` sprawdza poprzednią wartość, aktualizuje ID0 w drugim banku i weryfikuje zapis. Klipper wywołuje te procedury automatycznie po włączeniu synchronizacji. Fabryczny numer seryjny i rewizja płyty znajdują się na osobnej stronie Flash.

## Włączenie i odczyt

W istniejącej sekcji `[m300_mcu]` wpisz w `factory_counter_backup:` ścieżkę bezwzględną do sprawdzonej kopii pełnego Flash tej płyty (256 KiB). Klipper porównuje numer seryjny zapisany w kopii z numerem podłączonej płyty. Przed zapisem MCU sprawdza bezczynność osi, wyłączenie grzałek, aktualność odczytów ADC i sygnału heartbeat. Nieruchoma oś Z może pozostać pod napięciem. Przy temperaturze hotendu od 50 °C MCU wymaga ciągłego chłodzenia radiatora. Do czasu zapisu Klipper zachowuje oczekujące minuty lokalnie.

W `ZORTRAX_HARDWARE_STATUS` pole `factory_counter_runtime_supported` potwierdza dostępność procedur licznika na podłączonym MCU. `factory_counter_sync` przyjmuje `SYNCED` po zweryfikowanym zapisie lub `AWAITING_IDLE`, gdy zapis jest odroczony. `ZORTRAX_INFO REFRESH=0` pokazuje bieżący czas łączny. Gdy stan synchronizacji to `RECOVERY_REQUIRED`, zachowaj dziennik Klippera potrzebny do uzgodnienia przerwanej transakcji. Po przerwanym zapisie przed uruchomieniem fabrycznej aplikacji sprawdź `factory_counter_banks: NORMALIZED` i `factory_counter_pending: false`. Użytkownik potwierdził zwykłe uruchomienie fabrycznej aplikacji przez posiadany bootloader. Zapis Flash RC8 i zachowanie po odcięciu zasilania pozostają do sprawdzenia na płycie.

## Pakiet aplikacji na kartę SD

ZIP zawiera `M300APP.M3B`. Sprawdź sumę kontrolną wydania i wgraj aplikację procedurą posiadanego bootloadera M300. Aplikacja zaczyna się pod adresem `0x08008000`. Po instalacji sprawdź wersję `1.0.4` w `ZORTRAX_MCU_STATUS`.

Obszar linkowania aplikacji Classic ma 68 KiB, aby pomieścić kod synchronizacji licznika. Mieści się w istniejącym obszarze aplikacji bootloadera poniżej `0x0803A000`. Linker korzysta z dotychczasowego limitu 20 KiB SRAM.
