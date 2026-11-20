<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | RELEASE_v1.0.0-rc.30.md - Opisuje nastawy transportu filamentu i aktualizację Orange Pi. -->
# M300 Classic RC30 — ustawienia wyładunku i załadunku filamentu

W istniejącej sekcji `[m300_filament]` konfiguracji Klippera można ustawić cztery parametry. Korzystają z nich procedury na OLED, we Fluidd i w OrcaSlicerze oraz komendy `M600`, `LOAD_FILAMENT` i `UNLOAD_FILAMENT`. Temperatury podaje się w °C, a prędkości filamentu w mm/s.

```ini
unload_temperature: 240
unload_speed: 2
load_temperature: 0
load_speed: 2
```

Przy wartości `load_temperature: 0` wymiana w pauzie używa zapamiętanej temperatury wydruku. Samodzielny załadunek i wymiana z zimną nastawą korzystają z domyślnych 240°C lub zachowanej starszej opcji `procedure_temperature`. Wpisanie np. `load_temperature: 210` wybiera stałe 210°C zarówno dla samodzielnego załadunku, jak i wymiany podczas pauzy. Przy wymianie Klipper utrzymuje temperaturę wyładunku do zakończenia ostatniego odcinka cofania. Podanie nowego filamentu wymaga potwierdzenia i osiągnięcia temperatury ładowania. Po zakończeniu wraca zapamiętana nastawa druku.

Parametr `TEMP` w poleceniu `ZORTRAX_LOAD` lub `ZORTRAX_UNLOAD` obowiązuje przez jedną operację. W `ZORTRAX_CHANGE TEMP=...` dotyczy tylko ładowania. Po zapisaniu zmian w konfiguracji uruchom ponownie Klipper w spoczynku. Odczytaj cztery nastawy poleceniem `ZORTRAX_FILAMENT_STATUS`.

## Instalacja

Po zakończeniu druku, w stanie Ready z wyłączonymi grzałkami, w katalogu gałęzi `orange-pi` wykonaj:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Aktualizacja dotyczy hosta. Instalator dopisuje brakujące opcje do istniejącej sekcji i zachowuje wybrane wartości. MCU 1.0.8 obsługuje to wydanie. `M300_SD.zip` służy do osobnej aktualizacji MCU. Fluidd działa na porcie 4480, a jego osobny instalator przyjmuje `--update-fluidd --port 4480`. Instrukcja zawiera ilustracje z beta.20.
