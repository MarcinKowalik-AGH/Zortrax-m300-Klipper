# Aktualizacja działającej instalacji M300 Classic

Nowy host przygotuj według [instrukcji pierwszej instalacji](FIRST_INSTALL.md)
i użyj [paczki v1.0.0-rc.9](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.0-rc.9).
Ta instrukcja dotyczy hosta z działającym portem M300. [English](../en/INSTALL.md)

## 1. Zaktualizuj Klippera i Fluidd

Poczekaj na stan Ready. Zakończ wydruk lub wstrzymaną sesję, zaczekaj na
zakończenie ruchów i procedur, wyłącz oba cele grzania. Uruchom polecenia z
konta obsługującego Klippera. Moonraker musi udostępniać stan drukarki pod
`127.0.0.1:7125`.

Gałąź `orange-pi` zawiera najnowszą zweryfikowaną paczkę. Polecenia
aktualizują istniejący klon tej gałęzi w `~/m300-orange-pi` albo pobierają go
przy pierwszym użyciu.

```bash
m300_dir="$HOME/m300-orange-pi"
if [ -d "$m300_dir/.git" ]; then
  git -C "$m300_dir" pull --ff-only
else
  git clone --depth 1 --single-branch --no-tags --branch orange-pi \
    https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper.git "$m300_dir"
fi &&
python3 "$m300_dir/install-orange-pi.py" --port 4480
```

Aby zainstalować konkretną wersję, rozpakuj jej pełny ZIP i uruchom
`python3 install-orange-pi.py --port 4480` w katalogu głównym paczki. Sprawdź sumy ZIP-a i
jego zawartości zgodnie z [krokiem pobierania](FIRST_INSTALL.md#3-pobranie-wersjonowanej-paczki).
Do aktualizacji Klippera i Fluidd używaj instalatora M300.

Instalator sprawdza sumy i wersję plików hosta przed zapisem. Zachowuje
konfigurację UART, zapisane PID, mesh i ustawienia maszyny. Polecenie wybiera
działający Fluidd na porcie 4480 i zapisuje wybór obok `printer.cfg`.
Nginx musi już udostępniać stronę na tym porcie. Jeśli instalator odmówi
wyboru, sprawdź aktywną konfigurację przez `sudo nginx -T`. Niestandardowy
układ może wymagać także `--fluidd-root /bezwzględna/ścieżka/do/fluidd`.
[Wybór portu i ponawianie CI](INSTALLATION_AND_CI.md).

Sprawdź wynik `INSTALLED_M300_HOST` oraz pola `host_update`, `fluidd_port` i
`fluidd_root`. Zachowaj podane ścieżki `host_receipt` i `fluidd_backup`.
Jeśli po wymianie plików host nie wystartuje lub nie osiągnie Ready,
instalator przywraca poprzednie pliki hosta na podstawie `host_receipt`. W razie odmowy
zachowaj komunikat i sprawdź wskazany plik lub stan drukarki przed kolejną próbą.

Opcja `--organize-config` wydziela procedury M300, tabele temperatur i zapisane
aliasy PID oraz usuwa rozpoznane, zbędne wpisy aktualizacji strony.
[Opis zmian konfiguracji](../en/CONFIGURATION_AUDIT.md). Opcja
`--qualified-first-print-z` wymaga sprawdzonego mechanicznie prześwitu
konkretnej drukarki. Zwykła aktualizacja jej nie wymaga.

## 2. Wgraj MCU z karty SD

Instalator hosta pozostawia aktualny firmware MCU. Aby połączyć RC9 z
MCU 1.0.5, użyj `MCU/M300APP.M3B` z pełnego wydania albo rozpakuj plik
z `MCU/M300_SD.zip` lub osobnego [ZIP-a MCU na SD](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.5).
Zastosuj procedurę aktualizacji aplikacji posiadanego bootloadera M300.
Na zgodnym starszym MCU Klipper nadal liczy czas druku lokalnie.
[Instalacja MCU i synchronizacja licznika](MCU_FIRMWARE_1.0.5.md).

## 3. Sprawdź instalację

Otwórz `http://<IP-hosta>:4480/` i odśwież stronę z pominięciem pamięci
podręcznej. W konsoli wykonaj polecenia odczytu:

```gcode
STATUS
ZORTRAX_MCU_STATUS
ZORTRAX_HARDWARE_STATUS
ZORTRAX_LINK_STATUS
ZORTRAX_INFO REFRESH=0
QUERY_PROBE
```

Potwierdź Ready, zgodność prędkości UART po obu stronach oraz wersję
`1.0.5`, jeśli wgrano nowe MCU. Sprawdź [fabryczną rewizję i skalę Z](../en/HARDWARE_VARIANTS.md)
swojej płyty, np. HW04/Z800 lub HW05/Z400. Gdy dysza nie styka się ze
stołem, sonda powinna być otwarta. Jeżeli synchronizacja jest włączona,
sprawdź [stan licznika](MCU_FIRMWARE_1.0.5.md#włączenie-i-odczyt).

Przed pomiarem stołu sprawdź układ pól poleceniem `BED_MESH PREVIEW=1`.
[Mesh i poziomowanie](BED_MESH_AND_LEVELING.md) · [Procedury druku](PRINT_CONTROL.md) ·
[Import z SD](../en/MODELS_SD.md) · [Ilustrowana instrukcja OLED](OLED_FUNCTIONS.md)

## Przywróć poprzedni stan po aktualizacji hosta

Do ręcznego wycofania aktualizacji przy bezczynnej drukarce odczytaj `root` i
`config` z zachowanego potwierdzenia JSON. Podstaw obie ścieżki oraz ścieżkę
do pliku potwierdzenia w poniższych poleceniach:

```bash
if cd "$HOME/m300-orange-pi/M300_HOST" &&
  sudo systemctl stop klipper.service
then
  python3 install.py --root "/ścieżka/do/klippera" \
    --config "/ścieżka/do/printer.cfg" --rollback "/ścieżka/do/RECEIPT.json"
  sudo systemctl start klipper.service
fi
```

Dla paczki ZIP użyj jej katalogu `M300_HOST`. Sprawdź, czy wycofanie zwróciło
`ROLLED_BACK_M300_HOST`. Jeśli przywróciło `moonraker.conf`, wykonaj
`sudo systemctl restart moonraker.service`. Jeżeli instalator odmówi
nadpisania późniejszej edycji, zachowaj ją i sprawdź wskazany plik przed
ponowną próbą. Aby przywrócić Fluidd, użyj zgłoszonych ścieżek `fluidd_backup`
i `fluidd_root`. Przenieś bieżący katalog strony w inne miejsce, przywróć
kopię pod `fluidd_root` i wykonaj `sudo systemctl reload nginx`.
