<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | RELEASE_v1.0.0-rc.32.md - Opisuje obsługę ekstrudera w pauzie i aktualizację Orange Pi. -->
# M300 Classic RC32 — ręczne przepłukanie dyszy w pauzie

W pauzie poczekaj, aż drukarka zakończy ruch. Przy zmianie koloru poczekaj na pytanie o wypływ. W panelu **Narzędzie** we Fluidd lub w zakładce **Device** w OrcaSlicerze ustaw długość i prędkość filamentu. **Extrude** podaje go, a **Retract** cofa. Możesz powtarzać ruchy przed potwierdzeniem wypływu. Wydruk wznowisz osobno przyciskiem **Resume**.

Po samodzielnym załadunku lub wyładunku dysza pozostaje w zadanej temperaturze do ręcznego wyłączenia grzania albo upływu zwykłego czasu bezczynności Klippera. Jeśli w pauzie dysza już ostygła, ustaw temperaturę roboczą materiału i poczekaj na dogrzanie.

Przykład ze standardowego panelu: 30 mm i 4 mm/s odpowiada ruchowi `G1 E30 F240` dla podania lub `G1 E-30 F240` dla cofnięcia w trybie względnym. Prędkość i długość odczytywane są z pól panelu. Pozycja XYZ, pozycja pliku i zapisana pozycja logiczna ekstrudera pozostają dostępne do wznowienia. Automatyczny załadunek i wyładunek nadal korzystają z nastaw `[m300_filament]`. Wartości `auto` wynoszą 240°C i 2 mm/s dla obu kierunków.

## Aktualizacja Orange Pi

Zakończ wydruk, wyłącz grzanie i poczekaj na stan Ready. W istniejącym katalogu gałęzi `orange-pi` wykonaj:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Polecenie aktualizuje hosta. RC32 współpracuje z MCU 1.0.8. Archiwum `M300_SD.zip` służy do oddzielnej aktualizacji firmware. Fluidd działa na porcie 4480. Opcja `--update-fluidd --port 4480` służy do osobnej instalacji interfejsu. Historyczne ilustracje instrukcji pochodzą z beta.20.
