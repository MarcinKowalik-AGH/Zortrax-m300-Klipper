# M300 Classic beta.13 — przyspieszenie emulatora OLED we Fluidd

Poprawiłem dwie przyczyny obserwowanych opóźnień i pustych miejsc
w animowanych ikonach podglądu OLED.

**Odświeżanie:** zamiast czekać na standardową subskrypcję Moonraker
aktualizowaną mniej więcej co 250 ms, Fluidd wysyła osobne, wyłącznie
odczytowe zapytanie `printer.objects.query` o klatkę OLED. Odbywa się
to na istniejącym połączeniu WebSocket (bez nowych portów i połączeń).
Zapytania są wykonywane kolejno — następne dopiero po odpowiedzi,
co zapobiega przeciążeniu Orange Pi. Po zwinięciu podglądu lub ukryciu
karty przeglądarki odczyt jest wstrzymywany.

**Animacja:** podgląd jest teraz rysowany na Canvas 256×64. Poprzednia
kompletna klatka pozostaje na ekranie podczas dekodowania następnej.
Zapobiega to chwilowym pustym obszarom, które mogły występować przy
wymianie całego elementu PNG. Dodatkowe testy sprawdzają, czy animowane
ikony są kompletne w źródłowych klatkach renderera Klippera.

Szerokość podglądu nadal wynosi **50% karty temperatur**.
Zachowano 16 poziomów jasności, oryginalne animacje i wyświetlanie
informacji o rozłączeniu.

**Bez zmian pozostają** MCU, ekran fizyczny, kompresja RLE, DMA,
UART, SPI, potwierdzenia ACK, buzzer, grzałki, silniki, bazowanie,
Bed Mesh i procedury błędów.

Aktualizacja przy bezczynnej drukarce i stanie Klipper Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Po instalacji odśwież stronę Fluidd: **Cmd+Shift+R**. Nie
wgrywaj firmware MCU.

Wymagana walidacja: 702 testy hosta, testy animacji, procedur,
TypeScript, ESLint, produkcyjny Fluidd i kompilacja STM32F103.
Rzeczywistą płynność należy potwierdzić na Orange Pi.
