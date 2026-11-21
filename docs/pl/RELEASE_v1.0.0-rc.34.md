<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | RELEASE_v1.0.0-rc.34.md - Opisuje nazwy makr M300 i aktualizację konfiguracji. -->
# Nazwy makr M300 · RC34

36 makr operatorskich ma teraz prefiks `M300_`, np. `M300_STATUS`, `M300_LOAD`, `M300_UNLOAD` i `M300_MAIN_MENU`. OLED i Fluidd używają tych samych procedur. Dotychczasowe nazwy działają w zapisanych plikach G-code. Polecenia Klippera `START_PRINT`, `END_PRINT`, `PAUSE`, `RESUME` i `BED_MESH` zachowują swoje nazwy. Niższy poziom, np. `ZORTRAX_MCU_STATUS`, pozostaje dostępny w konsoli. [Lista makr](MACRO_REFERENCE.md).

## Aktualizacja Orange Pi

Zakończ wydruk, wyłącz grzanie i poczekaj na stan Ready. W istniejącym katalogu gałęzi `orange-pi` wykonaj:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py &&
python3 M300_HOST/setup_fluidd.py --apply
```

Polecenie aktualizuje hosta. RC34 współpracuje z MCU 1.0.8. Archiwum `M300_SD.zip` służy do oddzielnej aktualizacji firmware. Fluidd działa na porcie 4480. Opcja `--update-fluidd --port 4480` służy do osobnej instalacji interfejsu. Historyczne ilustracje instrukcji pochodzą z beta.20.
