# M300 Classic RC27 — menu Zortrax we Fluidd

W grupie makr **ZORTRAX M300** wybierz **ZORTRAX_MAIN_MENU**. W zakładce Device w OrcaSlicerze użyj tego samego przycisku. Menu zawiera Models, Maintenance, Material, Settings i Information w kolejności z OLED.

- **Material → Unload the material** uruchamia wspólną procedurę. Poczekaj na komunikat i potwierdź na OLED albo w oknie Fluidd. Makro `ZORTRAX_PROCEDURE` otwiera bieżący etap po zamknięciu okna.
- **Maintenance** zawiera bazowanie, grzanie, kalibrację, obsługę platformy i wentylatorów. Kliknięcie ruchu platformy wykonuje jeden krok 1 mm. Na OLED przytrzymanie pokrętła nadal steruje ruchem.
- **Models** otwiera pliki hosta oraz kartę SD, jeśli dostęp do niej został zakwalifikowany w konfiguracji. Wybierz plik, po zakończeniu importu wybierz **Refresh**, a następnie **Start printing**. Wybór pliku i uruchomienie wydruku są osobnymi czynnościami.

Na bezczynnej drukarce Ready z wyłączonym grzaniem zaktualizuj hosta z używanego katalogu gałęzi `orange-pi`:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Menu wykorzystuje obecny Fluidd na porcie 4480 i MCU 1.0.8. Do tej aktualizacji wystarcza instalacja hosta. Archiwum `MCU/M300_SD.zip` służy osobnej aktualizacji firmware. Ilustracje beta.20 w podręczniku przedstawiają wcześniejszy interfejs.

Jeśli potrzebna jest osobna naprawa plików WWW, istniejący instalator udostępnia opcje `--update-fluidd --port 4480`. [Instrukcja aktualizacji i naprawy](INSTALL.md).
