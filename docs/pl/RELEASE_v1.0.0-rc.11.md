# M300 Classic RC11

RC11 domyślnie aktualizuje wyłącznie Klippera w działającej instalacji.
Zachowuje istniejące pliki i preferencje Fluidd oraz konfigurację nginx.
MCU 1.0.5 nadal automatycznie synchronizuje fabryczny licznik czasu
druku ID0 zgodnie z funkcją wprowadzoną w RC10.

## Zaktualizuj hosta Klippera

Poczekaj na stan Ready, zakończ druk i inne procedury oraz wyłącz cele
grzania. Uruchom z konta Klippera:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Jeśli masz już MCU 1.0.5, wystarczy zaktualizować hosta. Do pierwszego
wgrania aplikacji MCU pełna paczka zawiera `MCU/M300_SD.zip`.
[Pierwsza instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.11/docs/pl/FIRST_INSTALL.md) ·
[Pełna instrukcja aktualizacji](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.11/docs/pl/INSTALL.md)

## Osobna aktualizacja lub naprawa Fluidd

```bash
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --update-fluidd --port 4480
```

Polecenie używa istniejącej witryny nginx na 4480 i zachowuje
`config.json` i preferencje. Zmiany metadanych ZIP nie powodują już
wymiany działających, zgodnych plików. Nowe pliki są czytelne dla nginx
również przy restrykcyjnym `umask` konta instalującego. Jeżeli instalator
może zweryfikować lokalną trasę HTTP, sprawdza nową stronę i JavaScript,
a po nieudanej kontroli przywraca poprzedni katalog.

Po naprawie otwórz `http://<IP-hosta>:4480/`. HTTP 200 z odpowiedzią o
długości 0 bajtów oznacza pustą stronę. Sprawdź aktywną witrynę i pliki
według [instrukcji diagnostyki Fluidd](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.11/docs/pl/INSTALL.md#gdy-fluidd-nie-otwiera-się-lub-pokazuje-pustą-stronę).
Ilustracje OLED z beta.20 dokumentują historyczną kompilację.
