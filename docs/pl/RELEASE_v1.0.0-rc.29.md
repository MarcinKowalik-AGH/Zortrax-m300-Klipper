# M300 Classic RC29 — wyładunek przy 240°C podczas wymiany materiału

Podczas wydruku polecenia `M600` i `ZORTRAX_CHANGE` oraz opcja zmiany materiału na OLED i we Fluidd kierują drukarkę do tej samej procedury. Po zaparkowaniu dysza osiąga temperaturę wyładunku 240°C. W ustawieniach domyślnych ekstruder wycofuje 110 mm z prędkością 2 mm/s. Po zakończeniu ostatniego odcinka wycofania Klipper ustawia temperaturę ładowania.

Przy wydruku w 210°C dysza wraca do 210°C na ładowanie. Opcjonalny parametr `ZORTRAX_CHANGE TEMP=...` ustala temperaturę ładowania nowego filamentu. Po włożeniu filamentu potwierdź operację na OLED lub we Fluidd. Ekstruder czeka na osiągnięcie temperatury i podaje domyślnie 150 mm. Sprawdź wypływ materiału, potwierdź gotowość i wybierz wznowienie. Podczas pierwszej próby obejrzyj wyjętą końcówkę i sprawdź, czy nowy filament przechodzi swobodnie przez gardziel.

## Aktualizacja Orange Pi

Zakończ wydruk. Gdy Klipper jest gotowy i grzałki mają nastawę 0°C, w katalogu istniejącej instalacji z gałęzi `orange-pi` wykonaj:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Zmiana dotyczy hosta. MCU 1.0.8 obsługuje tę wersję. Archiwum `M300_SD.zip` służy do osobnej instalacji firmware. Fluidd pracuje na porcie 4480. Opcja osobnego instalatora interfejsu to `--update-fluidd --port 4480`. Część ilustracji instrukcji pochodzi z beta.20.
