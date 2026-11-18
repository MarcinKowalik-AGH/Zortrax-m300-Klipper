# M300 Classic RC18

W RC13–RC17 oczekująca transakcja licznika mogła zostać ponowiona podczas identyfikacji zablokowanej płyty. MCU przyjmuje w tym stanie polecenia odczytu. Polecenie zapisu nie zwraca odpowiedzi. RC18 odczytuje profil Z podczas identyfikacji i wznawia transakcję dopiero po sprawdzeniu blokady przez Klippera, przed wysłaniem konfiguracji do MCU. Zachowaj dotychczasowy dziennik licznika. Kwotę zapisu i numer banku host potwierdza odczytem z płyty.

## Po wycofaniu instalacji

Przed resetem zachowaj klippy.log oraz wyniki `ZORTRAX_LINK_STATUS` i `ZORTRAX_MCU_STATUS`. Gdy poprzednia wersja zwraca `RECOVERY_REQUIRED` i brak odpowiedzi `m300_factory_counter_result` przed identyfikacją MCU, otwórz katalog pakietu RC18 na Orange Pi i wykonaj:

```bash
python3 install-orange-pi.py --recover-counter-startup
```

Instalator sprawdza ten konkretny stan, uruchamia poprawionego hosta i wymaga Ready. Jeżeli MCU zgłasza usterkę sprzętową, sprawdź pole `previous_guard` we wpisie `M300_HOST_START_GUARD` w klippy.log. Zwykłą aktualizację opisuje [instrukcja](INSTALL.md). Po Ready odczytaj `ZORTRAX_HARDWARE_STATUS` oraz `ZORTRAX_INFO REFRESH=0`. Trwałość zapisu potwierdź kolejnym odczytem po normalnym wyłączeniu i włączeniu drukarki.

Wersja MCU to 1.0.5. Pakiet pierwszej instalacji zawiera `MCU/M300_SD.zip`. Naprawa strony ma osobną opcję `--update-fluidd --port 4480`. Ilustracje OLED pochodzą z beta.20.
