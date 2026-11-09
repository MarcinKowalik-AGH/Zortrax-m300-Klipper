# M300 Classic v1.0.0-beta.14 — stała wysokość podglądu OLED

Podgląd OLED w karcie temperatur Fluidd ma teraz **stałe wymiary
344 × 86 px**. Zachowuje proporcje 4:1 i rozmiar zbliżony do
połowy szerokości wykresu w normalnym widoku komputerowym.

Zmniejszenie okna Fluidd nie zmienia już wysokości wyświetlacza.
Jeżeli karta jest węższa niż 344 px, podgląd można przesunąć
poziomo zamiast go zmniejszać. Wymiary pozostają identyczne
także dla komunikatu o braku połączenia.

**Bez zmian**: szybkie odświeżanie z beta.13, wszystkie animacje,
wyświetlanie na canvas, 16 poziomów jasności, połączenie WebSocket,
Klipper, buzzer i firmware MCU. Nie zmieniono RLE, DMA, UART, SPI, ACK
ani procedur bazowania, grzania i drukowania.

Aktualizacja na bezczynnej drukarce ze stanem Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Na końcu odśwież Fluidd przez **Cmd+Shift+R**. Nie ma potrzeby
ponownego wgrywania MCU.

Weryfikacja obejmuje rozmiar CSS i przewijanie, 702 testy hosta,
kontrole repozytorium, TypeScript, ESLint, testy Fluidd i
kompilację produkcyjną. Wygląd w Twojej przeglądarce wymaga
potwierdzenia po instalacji.
