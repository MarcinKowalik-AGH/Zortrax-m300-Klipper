# M300 Classic RC12

RC12 naprawia rozpoznaną witrynę Fluidd dla M300, w której `index.html`
i główny plik JavaScript mają po 0 bajtów. Instalator weryfikuje manifest
i zgodne pliki startowe, przywraca pliki statyczne z wydania i zachowuje
`config.json`.
Z MCU 1.0.5 Klipper dalej automatycznie przekazuje pełne minuty, gdy
drukarka jest bezczynna, a MCU może zapisać fabryczny rekord ID0.

## Zaktualizuj Klippera

Poczekaj na Ready, zakończ wydruk i procedury oraz wyłącz cele grzania.
Uruchom z konta Klippera:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

To aktualizacja hosta. Jeśli masz już MCU 1.0.5, wystarczy aktualizacja
Klippera. Do pierwszego wgrania aplikacji MCU pełna paczka zawiera
`MCU/M300_SD.zip`.
[Pierwsza instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.12/docs/pl/FIRST_INSTALL.md)

## Gdy Fluidd jest puste, zacznij od naprawy

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --update-fluidd --port 4480 &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Otwórz `http://<IP-hosta>:4480/` i sprawdź, czy Fluidd się ładuje. W konsoli
uruchom `ZORTRAX_MCU_STATUS`, `ZORTRAX_HARDWARE_STATUS` i
`ZORTRAX_INFO REFRESH=0`. Po zwykłym wydruku poczekaj na bezczynność.
Sprawdź stan `SYNCED` i wzrost licznika fabrycznego. Odczytaj licznik
ponownie po następnym normalnym wyłączeniu i włączeniu drukarki.
[Instrukcja aktualizacji i kontroli](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.12/docs/pl/INSTALL.md)

## Zakres weryfikacji

Testy programowe uruchamiają naprawę z gotowej paczki i otwierają
przywróconą stronę w rzeczywistej przeglądarce. Zapis Flash i odzyskiwanie
po przerwaniu zapisu są symulowane. Odczyt z fizycznej drukarki po zapisie
i po ponownym uruchomieniu wymaga osobnego potwierdzenia. Ilustracje OLED
z beta.20 pochodzą z historycznej wersji.
