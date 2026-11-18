# M300 Classic RC25 · Lewy pasek Fluidd w OrcaSlicerze

Ikony Konsola, Historia i Ustawienia otwierają widoki Fluidd także podczas pauzy wydruku. Jeżeli otwarta karta po aktualizacji próbuje pobrać nieaktualny moduł widoku, przy kliknięciu Fluidd ponownie ładuje stronę pod adresem wybranej pozycji. Zachowuje adres drukarki. Dwa kolejne restarty Klippera rozpoznaje na podstawie pary powiadomień od Moonrakera, także wtedy, gdy połączenie przeglądarki z Moonrakerem pozostaje otwarte. Strzałka odświeżania na górnym pasku przeładowuje stronę w tej samej karcie.

Na Orange Pi w katalogu używanej gałęzi `orange-pi` wykonaj:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py --update-fluidd --port 4480
```

Otwórz ponownie widok urządzenia, aby pierwszy raz załadować wydanie z przyciskiem odświeżania. Ta aktualizacja panelu jest niezależna od wersji wyświetlanej przez makro informacji o hoście. MCU 1.0.8 i plik `MCU/M300_SD.zip` służą dotychczasowej procedurze instalacji firmware. Historyczne ilustracje instrukcji pochodzą z beta.20.
