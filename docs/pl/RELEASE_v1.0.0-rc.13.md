# M300 Classic RC13

Załadunek i rozładunek filamentu z OLED, Fluidd oraz konsoli działają przy
aktywnej natywnej siatce stołu Klippera. Procedura porusza wyłącznie
ekstruderem, a po zakończeniu przywraca stan współrzędnych G-code. Siatka
pozostaje aktywna. Zabezpieczenia nadal odrzucają obce transformacje
ruchu i stosują dotychczasowe zasady do procedur poruszających osiami XYZ.

## Zaktualizuj Klippera

Poczekaj na stan Ready, zakończ wydruk i procedury oraz wyłącz cele grzania.
Uruchom z konta Klippera:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Jeśli drukarka ma już MCU 1.0.5, wystarczy aktualizacja hosta Klippera.
Pełna paczka zawiera `MCU/M300_SD.zip` do pierwszej instalacji. Fluidd
jest dostępny pod dotychczasowym adresem na porcie 4480. Osobne polecenie
z opcjami `--update-fluidd --port 4480` służy do jawnej naprawy strony.
[Pierwsza instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.13/docs/pl/FIRST_INSTALL.md) ·
[Instrukcja aktualizacji](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.13/docs/pl/INSTALL.md)

## Weryfikacja

Testy regresji obejmują załadunek i rozładunek z aktywną natywną siatką.
Sprawdzają ruch wyłącznie ekstrudera, zachowanie siatki i przywrócenie
stanu parsera. Przy następnym załadunku lub rozładunku na drukarce sprawdź,
czy procedura się kończy, i porównaj wynik odczytowego `BED_MESH_OUTPUT`
przed i po jej wykonaniu. Próba sprzętowa pozostaje do wykonania.
Ilustracje OLED z beta.20 pochodzą z historycznej wersji.
