# Zortrax M300 Classic — firmware MCU 1.0.0

**Zakres:** wyłącznie aplikacja dla oryginalnej płyty STM32F103 M300 Classic. Nie jest to firmware dla Plus, Dual, Inventure ani Orange Pi. To niezależne wydanie firmware, zgodne z hostem M300 `1.0.0-rc.2`.

[Wydanie i ZIP do wgrania](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.0) · [Instalacja główna](FIRST_INSTALL.md)

## Co zostało zmienione

Nazewnictwo MCU jest czysto numeryczne: `M300_MCU_RELEASE=1.0.0` oraz `klipper.dict.version=1.0.0`. Nie ma już widocznego dodatku `-TONED-OLED-UART8` ani automatycznego `?-data-host` w wersji kompilacji. Autonomiczny ekran informacyjny MCU pokazuje `MCU: 1.0.0`. Szczegóły budowy, hash źródła, commit GitHuba i sumy SHA-256 pozostają w osobnych plikach raportu; usunięcie sufiksu nie usuwa informacji diagnostycznej.

Aplikacja zachowuje funkcje wcześniejszej R14.19, w tym 4-bitowe obrazy autonomicznych ekranów OLED. Nie zmieniono obsługi UART, formatów poleceń, progów temperatur, watchdogów, zabezpieczeń wyjść, fan policy 3, homingu, timera XY, mapy pamięci ani bootloadera. Starsza R14.18 pozostaje zgodna z obecnym hostem i nie wymaga awaryjnego wgrywania.

## Weryfikacja paczki

Pobierz `M300_MCU_v1.0.0_SD.zip` i `SHA256SUMS-mcu-v1.0.0.txt` z niezależnego wydania MCU. W jednym katalogu:

```bash
sha256sum -c SHA256SUMS-mcu-v1.0.0.txt
unzip -l M300_MCU_v1.0.0_SD.zip
```

ZIP musi zawierać wyłącznie `M300APP.M3B`. To kontener aplikacji rozpoczynającej się pod adresem `0x08008000`, nie obraz całej pamięci MCU ani nowy bootloader. Raport kompilacji zawiera sprawdzony zakres Flash i RAM oraz kontrolę miejsca chronionego na konfigurację.

## Aktualizacja istniejącej drukarki

1. Zakończ wydruk; nie wykonuj aktualizacji w pauzie. Wyłącz grzałki, pozwól dyszy ostygnąć, zachowaj kopię konfiguracji oraz sposób powrotu do poprzedniej aplikacji.
2. Rozpakuj `M300_MCU_v1.0.0_SD.zip`. Skopiuj tylko `M300APP.M3B` do katalogu głównego karty SD używanej z już zainstalowanym bootloaderem M300.
3. Zatrzymaj host na Orange Pi: `sudo systemctl stop klipper`. Wykonaj **sprawdzoną wcześniej** procedurę wgrywania aplikacji z karty SD w bootloaderze. Nie używaj ST-Link do kasowania całego Flash; nie podmieniaj bootloadera; nie ingeruj w fabryczne dane NVM.
4. Po potwierdzonym zakończeniu programowania usuń plik aktualizacyjny z karty lub wyjmij kartę. Uruchom `sudo systemctl start klipper`.
5. We Fluidd odczytaj `ZORTRAX_MCU_STATUS`, `ZORTRAX_OLED_STATUS` i `ZORTRAX_SETTINGS_STATUS`. Oczekuj MCU `1.0.0`, modelu `M300_CLASSIC`, ABI 1, stanu Ready, fault 0, działającego chłodzenia i zgodnej prędkości UART. Na Twojej drukarce UART wynosi **750000 baud**; ta paczka go nie zmienia.

Weryfikacja kompilacji i testy symulacyjne **nie zastępują testu na rzeczywistym MCU**. Przed pierwszym ruchem po flashowaniu potwierdź stan wejść, chłodzenia, OLED i poprawną komunikację, bez uruchamiania automatycznych procedur z tej instrukcji.

## Wersjonowanie i cofanie

To wydanie firmware ma niezależny tag `mcu-v1.0.0`; **nie zmienia** hosta `1.0.0-rc.2` ani przypiętego commita bazowego Klippera. Jeżeli po wgraniu drukarka nie osiągnie stanu Ready, zatrzymaj Klippera i zastosuj sprawdzoną procedurę powrotu do wcześniejszego firmware aplikacji. Nigdy nie obchodź zabezpieczeń MCU, aby wymusić start.
