# M300 Classic beta.18 — spójny widok Tune i stała kolejność map

Zastępuje beta.17. Rewizja widoku Tune: `TUNE-VIEW-2`.

## Poprawka

W Tune **heatmapa jest zawsze nad schematem pól kontaktu stołu**. Usunięto warunek `meshChartFirst`, który zamieniał kolejność kart przed pomiarem, przy braku aktywnej siatki i w trakcie przygotowania. Zmiana stanu procedury nie przestawia już kart.

Wejście przez ikonę Tune na pasku bocznym pobiera jeden aktualny, wyłącznie odczytowy zestaw danych `bed_mesh` i `m300_pad_mesh`. Zakończenie natywnego bazowania M300 odświeża ten sam widok. Nie trzeba wcześniej uruchamiać BED_MESH. Przycisk Refresh view ponawia wyłącznie odczyt. Zachowano zwykłe subskrypcje; nie dodano ciągłego odpytywania. Żądania są ograniczone, a spóźniona odpowiedź nie nadpisuje nowszego stanu ani danych innego połączenia.

**All nadal oznacza bazowanie osi (`G28`), nie pomiar stołu.** Pomiar uruchamia jawnie BED_MESH / Calibrate. Otwarcie Tune nie uruchamia ruchu ani grzania i nie aktywuje kompensacji.

Poprawny zapisany profil `m300_pads` jest dostępny jako podgląd, także bez aktywacji kompensacji. Jeśli nie ma aktywnej ani poprawnej siatki do podglądu, karta heatmapy informuje o braku danych; nie pokazuje wymyślonej płaskiej powierzchni. Schemat pól i planowanych punktów pozostaje dostępny. Po bazowaniu XY pojawia się znacznik dyszy, ale nie są dopisywane niezmierzone wysokości.

## Bez zmian

Kod wykonawczy hosta, MCU, konfiguracja, pomiar mesh, START/END, PAUSE/CANCEL i cztery linie startowe nie zostały zmienione. Zachowano szybki kanał nawigacji OLED, animacje i kwadratowe piksele z beta.17 oraz parametry UART/SPI/RLE/ACK. Standardowe częstotliwości statusów pozostają bez zmian.

## Sprawdzenie

Pełny zestaw CI obejmuje wcześniejsze testy hosta, natywnego Klippy, ARM i frontendu oraz nowe testy wejścia do Tune, stałej kolejności kart we wszystkich stanach, podglądu zapisanej siatki bez aktywacji, braku danych, geometrii przed All, faktycznego przycisku All wysyłającego wyłącznie G28, odświeżenia po bazowaniu i przejścia z BED_MESH. Testowane są także rozłączenia, spóźnione odpowiedzi i ograniczenie liczby zapytań. Raport frontendu: `REPORTS/FLUIDD_UNIT_TESTS.json`.

Są to testy programowe. Nie wykonano ruchów ani pomiaru na fizycznej drukarce.

## Aktualizacja

Przy bezczynnej drukarce w stanie Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Następnie odśwież Fluidd przez Cmd+Shift+R. Nie trzeba ponownie wgrywać MCU. Wejdź do Tune przed pomiarem: heatmapa ma pozostać nad schematem pól. Jeśli profil nie został utrwalony przez SAVE_CONFIG przed restartem Klippera, All nie odtworzy pomiarów — trzeba wykonać nowy pomiar.

Oznaczenie strony: `data-m300-tune-revision="TUNE-VIEW-2"`. Oznaczenia OLED pozostają `NAV-PIPELINE-2` i `NAV-EVENT-1`.
