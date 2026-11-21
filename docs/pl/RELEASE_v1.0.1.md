# M300 Classic 1.0.1 — opuszczenie stołu po Cancel

21.11.2026. **Host 1.0.1 + MCU 1.0.8**, projektowy Fluidd na porcie **4480**.
Poprawka zastępuje 1.0.0.

Zwykłe **Cancel** opuszcza teraz stół tak jak `END_PRINT`: o maksymalnie
**300 mm od bieżącej pozycji**, z ograniczeniem do skonfigurowanego końca osi Z.
Po zakończeniu zjazdu głowica parkuje w ustawionym narożu, domyślnie X300 Y305,
jeżeli dostępny prześwit pozwala na ruch XY.

Grzanie jest wyłączane, a natywny plik i pauza zamykane przed oczekiwaniem na
opróżnienie kolejki i zjazd stołu. Termin zakończenia uwzględnia rzeczywisty czas
zaplanowanego przejazdu: wolna oś Z może wykonać zjazd trwający 300 sekund bez
fałszywego przekroczenia zwykłego limitu 120 sekund. Ruch nadal wymaga ważnego
bazowania i zgody zabezpieczeń MCU. Cancel bez aktywnego wydruku nie rusza osi.

Zestaw hosta obejmuje **992 testy**, w tym anulowanie z druku i pauzy, ograniczenie
Z, prześwit, wolny pełny zjazd i natywne przyciski Fluidd. Scenariusz anulowania
w rzeczywistym Klippym FILEOUTPUT sprawdza również końcową wysokość stołu.
Instalator rozpoznaje dokładne moduły wcześniejszego wydania 1.0.0.

## Aktualizacja

Na postoju, w stanie Ready i z wyłączonymi celami obu grzałek, wykonaj w swoim
istniejącym klonie gałęzi `orange-pi`:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Po instalacji odczytaj `ZORTRAX_INFO REFRESH=0`: host **1.0.1**, MCU **1.0.8**.
Wystarczy aktualizacja hosta; zainstalowanego MCU 1.0.8 nie trzeba ponownie
wgrywać. Pełny pakiet nadal zawiera `M300_SD.zip` dla drukarek wymagających tego MCU.
Osobna naprawa Fluidd:
`python3 install-orange-pi.py --update-fluidd --port 4480`.

[Aktualizacja i rollback](INSTALL.md) · [Pierwsza instalacja](FIRST_INSTALL.md) ·
[Sterowanie drukiem](PRINT_CONTROL.md). Ilustracje OLED zachowują oznaczoną bazę
beta.20. Testy programowe nie dopisują odbioru fizycznego zjazdu do rejestru prób.
