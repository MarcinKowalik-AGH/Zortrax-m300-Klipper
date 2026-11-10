# Zortrax M300 Classic v1.0.0-beta.20 — wycentrowany OLED, przyciski pod HIDE

Wersja zastępuje beta.19. Rewizja wyglądu: `OLED-ZOOM-2`. Zmiana dotyczy **wyłącznie Fluidd**.

## Układ i kolorystyka

Przyciski ×1 / ×2 / ×3 są **przy prawej krawędzi panelu pod napisem HIDE**, niezależnie od skali i szerokości wirtualnego ekranu. OLED jest wycentrowany względem **całej karty**, a nie względem wolnej przestrzeni pomiędzy obrazem i przyciskami. Układ wykorzystuje symetryczne kolumny po 40 px. Jeżeli podgląd ×2 lub ×3 nie mieści się w karcie, przewija się poziomo **tylko obraz**, nie przyciski.

**Wysokość całej kolumny przycisków** odpowiada zawsze wysokości najmniejszego podglądu **×1**, nawet przy wybraniu ×2 lub ×3. Wysokość automatycznie uwzględnia gęstość pikseli i powiększenie przeglądarki: **68 pikseli CSS przy DPR 1 lub 66 pikseli CSS przy DPR 2** (z cienką ramką ochronną). Trzy równe przyciski wypełniają tę samą wysokość.

Kolory pochodzą bezpośrednio z 16-poziomowej palety oryginalnego renderera: pełna jasność `#16A1FE`, obrys `#0A436C`, podświetlenie aktywnego przycisku `#0C588E`, tło `#020610`. Nie ma już niezależnego turkusowego odcienia przycisków.

## Zachowane funkcje

Bez zmian pozostają: szybkie zdarzenia nawigacji OLED, animacje, wyświetlanie kwadratowych pikseli, dekodowanie ostatniego PNG bez pobierania nowej klatki przy zmianie skali, zapamiętywanie wyboru ×1/×2/×3, MCU i Orange Pi, UART/SPI, temperatura/ruch, kalibracja/mesh i START/PAUSE/RESUME/CANCEL. Wejście do panelu i zmiana skali nie wysyłają żadnych poleceń do drukarki.

## Aktualizacja standardowej beta.19

Na Orange Pi, wyłącznie przy bezczynnej drukarce w stanie **Ready**:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Po instalacji odśwież Fluidd przez **Cmd+Shift+R**. Nie trzeba aktualizować MCU ani zmieniać Moonrakera.

## Walidacja

Warunkiem publikacji jest zakończona sukcesem pełna kompilacja i testy hosta/MCU/ARM, kontrola Klippy, ESLint/TypeScript, testy komponentu Vue, rzeczywiste pomiary ułożenia w Chromium i Firefoksie przy różnych skalach/rozmiarach karty i DPR, dotychczasowe testy pikseli, produkcyjny Fluidd oraz kontrola integralności. Testy przeglądarkowe nie zastępują oględzin na Twoim monitorze i testu działającej drukarki.
