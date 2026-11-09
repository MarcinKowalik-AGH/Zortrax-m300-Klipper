# M300 v1.0.0-beta.12 — podgląd OLED 50% szerokości i mniejsze opóźnienia

Wprowadzono dwie poprawki odpowiadające obserwacjom w Fluidd:

- **Rozmiar:** podgląd OLED pod wykresem temperatur zajmuje teraz
  połowę szerokości karty i jest wyśrodkowany. Zachowuje format 4:1.
- **Płynność:** poprzednio podgląd czekał na ACK całej ramki OLED,
  a następnie maksymalnie co 500 ms wysyłał PNG do przeglądarki.
  Teraz korzysta z ostatniej ramki już wyrenderowanej na Orange Pi,
  bez oczekiwania na zakończenie transmisji do MCU.
  Zmiany szybsze od odświeżania są scalane, bez budowania kolejki;
  minimalny odstęp wynosi 125 ms. PNG korzysta z bezstratnej,
  szybszej kompresji. W praktyce limit odświeżania zwykle wynika
  z subskrypcji Moonraker (około 4 razy/s).

**Ważne:** podgląd może nieznacznie wyprzedzać rzeczywisty obraz
na wyświetlaczu M300. Nie jest odczytem matrycy ani potwierdzeniem ACK.
Nie można nim obsługiwać drukarki — jest tylko do odczytu.

Oryginalny RLE, bloki różnicowe, SPI/DMA, UART, ACK, timeouty,
obsługa buzzera i wentylatorów, bazowanie X/Y/Z, grzałki,
kalibracja, Bed Mesh i procedury błędów pozostały niezmienione.
**Nie wgrywaj ponownie firmware MCU.**

Aktualizacja hosta i Fluidd przy bezczynnej drukarce w stanie Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Po zakończeniu odśwież Fluidd: **Cmd+Shift+R**.

Testy automatyczne obejmują 700 testów hosta, testy zgodności
procedur i kontraktów transportu, testy Fluidd, TypeScript, ESLint,
kompilację firmware oraz pełne GitHub Actions. Opóźnienie
na rzeczywistym Orange Pi i w Twojej sieci trzeba zweryfikować
po aktualizacji.
