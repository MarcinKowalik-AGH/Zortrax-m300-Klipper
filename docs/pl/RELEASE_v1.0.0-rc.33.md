<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | RELEASE_v1.0.0-rc.33.md - Opisuje dogrzanie w pauzie i ponowne sprawdzenie wypływu po cofnięciu. -->
# M300 Classic RC33 — Potwierdzenie wypływu po wymianie materiału

Po zmianie materiału zarówno temperatura zmierzona, jak i zadana muszą osiągać próg ekstruzji. Przy dyszy 230°C i celu 150°C wybierz **Reheat to check flow** na OLED lub **Resume** we Fluidd. Po dogrzaniu drukarka pozostanie w pauzie. Podaj materiał, sprawdź wypływ i wybierz **Confirm material flow** lub wpisz `FILAMENT_READY`. Każde przyjęte ręczne cofnięcie po potwierdzeniu ponawia pytanie o wypływ. Po kolejnym podaniu potwierdź wypływ ponownie, a następnie wybierz **Resume**.

## Aktualizacja Orange Pi

Zakończ wydruk, wyłącz grzanie i poczekaj na stan Ready. W istniejącym katalogu gałęzi `orange-pi` wykonaj:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Polecenie aktualizuje hosta. RC33 współpracuje z MCU 1.0.8. Archiwum `M300_SD.zip` służy do oddzielnej aktualizacji firmware. Fluidd działa na porcie 4480. Opcja `--update-fluidd --port 4480` służy do osobnej instalacji interfejsu. Historyczne ilustracje instrukcji pochodzą z beta.20.
