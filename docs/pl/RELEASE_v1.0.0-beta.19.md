# Zortrax M300 Classic v1.0.0-beta.19 — powiększanie podglądu OLED ×1 ×2 ×3

Wersja zastępuje beta.18. Zachowano szybki kanał nawigacji `NAV-PIPELINE-2` / `NAV-EVENT-1`; nowe sterowanie obrazem ma identyfikator `OLED-ZOOM-1`.

## Zmiany

Po **prawej stronie wirtualnego ekranu 256×64** w karcie temperatur Fluidd znajdują się trzy małe przyciski **×1**, **×2**, **×3**, w kolorystyce cyjanowego OLED. Wybrany przycisk jest podświetlony. Sterowanie działa również klawiaturą, a skala jest zapamiętywana lokalnie w przeglądarce. Jeśli pamięć lokalna jest zablokowana lub zawiera nieprawidłową wartość, zostaje użyte ×1. Przy wąskim oknie przewijany jest jedynie powiększony obraz — przyciski pozostają po prawej.

Przy standardowych gęstościach ekranu **DPR 1 i DPR 2** otrzymujemy dla samego obrazu:

| Przycisk | Rozmiar treści w pikselach CSS | Piksel źródłowego OLED |
|---|---:|---|
| ×1 | 256×64 | kwadratowy blok 1×1 CSS |
| ×2 | 512×128 | kwadratowy blok 2×2 CSS |
| ×3 | 768×192 | kwadratowy blok 3×3 CSS |

Do wymiarów dochodzi wąska ciemna ramka. Przy ułamkowym DPR lub zmianie powiększenia strony przeglądarka wybiera najbliższe **całkowite kwadratowe bloki pikseli urządzenia**, więc faktyczny rozmiar CSS może nieznacznie odbiegać od tabeli. Nie wprowadzamy interpolacji. Gwarancja nie dotyczy dodatkowego skalowania lupą systemową, pulpitem zdalnym ani animowanego powiększania gestem.

Zmiana skali **przerysowuje ostatni zdekodowany obraz bez ponownego pobierania lub dekodowania PNG**. Nie zmienia menu, animacji, szybkiej nawigacji, transmisji UART/SPI, fizycznego OLED ani standardowych statusów Klippera. Pozostają wszystkie poprawki beta.18, w tym Tune, zapisane profile mesh oraz START/PAUSE/CANCEL.

## Aktualizacja beta.18

Na Orange Pi, wyłącznie przy bezczynnej drukarce **Ready**:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Po instalacji odśwież Fluidd skrótem **Cmd+Shift+R**. Nie trzeba ponownie wgrywać MCU, zmieniać Moonrakera ani wykonywać kalibracji stołu. Nie wymuszaj nadpisania lokalnych zmian.

## Walidacja

Warunkiem publikacji są zakończone sukcesem: kompilacja ARM, testy Klippera i hosta, testy komponentu Vue (umieszczenie i aktywacja ×1/×2/×3, pamięć ustawienia, brak ponownego dekodowania przy zmianie skali), ESLint, kontrola typów, produkcyjny Fluidd, rzeczywiste porównania obrazu w Chromium i Firefoksie oraz kontrola sum pakietu.

Testy programowe nie są pomiarem na drukarce. Po aktualizacji sprawdź w Fluidd trzy wielkości i zachowanie szybkiego przewijania oraz animacji podczas obracania pokrętłem.
