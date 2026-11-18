# M300 Classic RC20 z MCU 1.0.7

Marcin Kowalik <mkowalik@agh.edu.pl>

W menu Zortrax → Settings wybierz OLED dim time albo OLED sleep time. Oba paski pokazują liczbę minut od ostatniej obsługi. Pokrętło zmienia wartość aktywnego paska, krótkie naciśnięcie zapisuje ją, a długie wraca. W Fluidd otwórz OLED_TIMERS w grupie Klipper lub ZORTRAX_OLED_TIMERS w grupie ZORTRAX M300, ustaw oba suwaki i wybierz Save. Przykładowe polecenie to `ZORTRAX_OLED_TIMERS DIM=5 SLEEP=15`. Obowiązuje zakres 1–60 minut oraz kolejność DIM ≤ SLEEP. Po osiągnięciu progu SLEEP ekran pokazuje dotychczasową animację wygaszania. W czasie wydruku, pauzy, grzania i procedur serwisowych ekran może się przygasić. Pierwszy gest po uśpieniu budzi ekran. Dotychczasowe Sleep mode → Disabled nadal wyłącza mechanizm.

Nowa konfiguracja ustawia 5 minut do przygaszenia i 15 minut do uśpienia. Aktualizator zachowuje istniejący plik m300_display.cfg. Jeśli ma on tylko timeout, dotychczasowy próg obowiązuje w obu przypadkach do pierwszego zapisu nowych wartości.

Przy gotowej i bezczynnej drukarce zaktualizuj checkout orange-pi. Sprawdź SHA256SUMS. Zainstaluj aplikację z MCU/M300_SD.zip dotychczasowym bootloaderem. Uruchom `python3 install-orange-pi.py`, a dla wersji Fluidd z suwakami `python3 install-orange-pi.py --update-fluidd --port 4480`. Rysunki w starszym podręczniku pochodzą z beta.20.

`ZORTRAX_DISPLAY_STATUS` pokazuje wybraną parę, parę odczytaną z MCU i stan zapisu. PENDING oznacza oczekiwanie na warunki zapisu, SYNCED potwierdza zgodny odczyt MCU. W istniejącej sekcji `[m300_mcu]` ustaw `debug: True` i przeładuj Klipper, aby zapisywać szczegółowe odczyty próbnika Z, cofnięcia i sprzętu. Domyślne `False` zachowuje błędy i komunikaty zabezpieczeń. Zmiana częstotliwości logowania dotyczy dodatków M300. [Zakres audytu i próby na HW05](AUDYT_RC20.md).
