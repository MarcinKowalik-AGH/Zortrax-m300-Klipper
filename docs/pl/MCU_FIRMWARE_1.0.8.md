# M300 Classic MCU 1.0.8

MCU zapamiętuje wybrany DIM i aktualny SLEEP również wtedy, gdy DIM jest dłuższy. Po synchronizacji sprawdź w `ZORTRAX_DISPLAY_STATUS` wartości `oled_preferred_dim_minutes`, `oled_mcu_preferred_dim_minutes` oraz parę rzeczywistych progów `oled_timer_mcu_minutes`.

Nowe ustawienia OLED używają dwóch stron aplikacji pod adresami 0x08019000 i 0x08019800. Fabryczny licznik ma osobne banki. Po zmianie czasów sprawdź `oled_timer_storage` i `oled_timer_mcu_minutes` w `ZORTRAX_DISPLAY_STATUS`.

[Pierwsza instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.23/docs/pl/FIRST_INSTALL.md) · [Opis RC23](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.23/docs/pl/RELEASE_v1.0.0-rc.23.md) · [ZIP na kartę SD i sumy SHA-256](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.8)

## Wgraj aplikację z karty SD

Sprawdź `M300_MCU_v1.0.8_SD.zip` według sumy kontrolnej wydania.
Rozpakuj `M300APP.M3B` do głównego katalogu karty i użyj procedury
aktualizacji aplikacji przez bootloader, który jest już w M300 Classic.
Aplikacja zaczyna się pod adresem `0x08008000`. Usuń plik aktualizacji przed
kolejnymi uruchomieniami. Po osiągnięciu Ready sprawdź `mcu_release: 1.0.8`
w `ZORTRAX_MCU_STATUS`.

## Odczyt licznika

Od RC10 Klipper synchronizuje licznik automatycznie z dotychczasową konfiguracją.
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

MCU 1.0.8 przed przyjęciem transakcji sprawdza sygnaturę 256 KiB Flash, identyfikator rdzenia Cortex-M3 i fabryczny rekord rewizji płyty. Każdy transfer wymaga zgodności numeru seryjnego, banku i sumy CRC ustawień oraz spełnienia warunków bezczynności. Przy pracy bez debuggera STM32 może zwrócić zero z DBGMCU_IDCODE. Obcy niezerowy identyfikator lub zero przy aktywnym debuggerze blokuje zapis. [Errata ST ES0340 §2.2.2](https://www.st.com/resource/en/errata_sheet/cd00197763-stm32f101xcde-and-stm32f103xcde-highdensity-device-limitations-stmicroelectronics.pdf).

RC20 udostępnia odczyty MCU w `factory_counter_target`. Sprawdź `flash_kib` i `supported`. Przy `AWAITING_IDLE` pole `factory_counter_wait_reason` podaje warunek hosta albo `mcu_write_window`, gdy zapis odroczyła płyta. Przy `UNSUPPORTED_MCU_TARGET` host zachowuje zaległy czas. Po dwóch zapisach aktywny może być ponownie wyjściowy bank. Porównaj liczbę minut i potwierdzenie hosta, a po normalnym wyłączeniu i włączeniu powtórz odczyt. Odbiór na drukarce pozostaje otwarty.

### Gdy host nie może rozstrzygnąć historii licznika

`RECONCILIATION_REQUIRED` wstrzymuje automatyczne dopisywanie minut. Drukowanie jest dostępne. W RC17 host zapisuje również drugie potwierdzenie obok pliku `.runtime-sync`. Zachowaj oba razem z ustawieniami. Gdy jedna kopia z bieżącej instalacji zaginie albo będzie starsza, synchronizator porówna dostępne potwierdzenia przed zapisem w MCU.

Odczytaj `ZORTRAX_HARDWARE_STATUS`. Jeżeli zapis pozostaje wstrzymany, polecenie poniżej służy do jednorazowego uzgodnienia na podstawie znanego wcześniejszego rozliczenia. Podstaw bieżący numer seryjny, wartość `factory_counter_observed_minutes` oraz liczbę pełnych minut Klippera, które zostały już dopisane do ID0. Wartość 0 jest poprawna tylko wtedy, gdy wiadomo, że żadnej minuty z zachowanej historii hosta wcześniej nie przeniesiono. Pojedynczy dawny status `DISABLED` nie mówi, co mogło zostać zapisane później. Przy nieznanej historii zachowaj stan do wyjaśnienia.

```text
ZORTRAX_COUNTER_RECONCILE SERIAL=<numer> MCU_MINUTES=<odczyt_ID0> COMMITTED_MINUTES=<potwierdzone_minuty_Klippera>
```

Polecenie ustala podstawę rozliczenia. Właściwy zapis przez MCU następuje w bezczynności. Po nim sprawdź przyrost ID0, `NORMALIZED`, `pending=false` i trwałość po normalnym ponownym włączeniu drukarki.
