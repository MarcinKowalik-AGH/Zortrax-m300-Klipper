# Aktualizacja działającej instalacji M300 Classic

Nowy host przygotuj według [instrukcji pierwszej instalacji](FIRST_INSTALL.md)
i użyj [paczki v1.0.0](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.0).
Gdy Fluidd pokazuje pustą stronę, [najpierw napraw Fluidd](#napraw-fluidd-a-potem-zaktualizuj-klippera).
[English](../en/INSTALL.md).

Po wycofaniu starszej aktualizacji z błędem oczekującej odpowiedzi licznika zobacz [wznowienie instalacji RC18](RELEASE_v1.0.0-rc.18.md).

## 1. Zaktualizuj Klippera

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
(cd "$m300_dir" && sha256sum -c --quiet SHA256SUMS) &&
python3 "$m300_dir/install-orange-pi.py"
```

Aby zainstalować konkretną wersję, rozpakuj jej pełny ZIP i uruchom
`python3 install-orange-pi.py` w katalogu głównym paczki. Sprawdź sumy ZIP-a i
jego zawartości zgodnie z [krokiem pobierania](FIRST_INSTALL.md#3-pobranie-wersjonowanej-paczki).
Polecenie domyślne aktualizuje hosta Klippera i zachowuje konfigurację UART,
zapisane PID, mesh, ustawienia maszyny, stronę i preferencje Fluidd oraz
konfigurację nginx.

Sprawdź wynik `INSTALLED_M300_HOST` i pole `host_update`. Zachowaj ścieżkę
`host_receipt`, gdy została podana. Jeśli zaktualizowany host nie wystartuje
lub nie osiągnie Ready, instalator przywraca poprzednie pliki na podstawie
tego potwierdzenia. W razie odmowy sprawdź wskazany plik lub stan drukarki.

Opcja `--organize-config` wydziela procedury M300, tabele temperatur i zapisane
aliasy PID oraz usuwa rozpoznane, zbędne wpisy aktualizacji strony.
[Opis zmian konfiguracji](../en/CONFIGURATION_AUDIT.md). Opcja
`--qualified-first-print-z` wymaga sprawdzonego mechanicznie prześwitu
konkretnej drukarki. Zwykła aktualizacja jej nie wymaga.

## Aktualizacja po błędzie Git „corrupt loose object”

Pozostaw uszkodzony katalog na miejscu. Przy bezczynnej drukarce pobierz nową kopię do osobnego katalogu na Orange Pi. Instalator nadal używa istniejącej konfiguracji drukarki. Poniższe polecenie pobiera aktualnie opublikowaną gałąź wdrożeniową.

```bash
m300_src=$(mktemp -d "$HOME/m300-orange-pi.XXXXXX") &&
git clone --depth 1 --single-branch --no-tags --branch orange-pi \
  https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper.git "$m300_src" &&
(cd "$m300_src" && sha256sum -c --quiet SHA256SUMS) &&
python3 "$m300_src/install-orange-pi.py"
```

Zachowaj nową ścieżkę, aby używać jej przy kolejnych aktualizacjach. Pełny ZIP oznaczony wersją umożliwia instalację dokładnie 1.0.0. Po osobnej naprawie Fluidd sprawdź pole `fluidd_http_verified` i otwórz menu na porcie 4480.

## 2. Sprawdź wersję MCU

Jeśli masz już MCU 1.0.8, pomiń aktualizację z SD. Aby wgrać wersję MCU
dołączoną do 1.0.0, użyj `MCU/M300APP.M3B` z pełnego wydania albo rozpakuj
plik z `MCU/M300_SD.zip` lub osobnego
[ZIP-a MCU na SD](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.8).
Zastosuj procedurę aktualizacji aplikacji posiadanego bootloadera M300.
[Instrukcja MCU 1.0.8](MCU_FIRMWARE_1.0.8.md).

Z MCU 1.0.8 synchronizacja działa automatycznie z dotychczasową konfiguracją.
Klipper przyjmuje i ignoruje stary wpis `factory_counter_backup:`. Możesz go
usunąć po aktualizacji hosta. Zachowaj dotychczasowe pliki licznika Klippera
wraz z dziennikiem synchronizacji. Jeśli firmware MCU nie udostępnia
poleceń licznika podczas normalnej pracy, Klipper dalej zlicza nowy czas
drukowania lokalnie.

## 3. Sprawdź instalację

W konsoli istniejącego Fluidd pod `http://<IP-hosta>:4480/` wykonaj
polecenia odczytu:

```gcode
STATUS
ZORTRAX_MCU_STATUS
ZORTRAX_HARDWARE_STATUS
ZORTRAX_LINK_STATUS
ZORTRAX_INFO REFRESH=0
QUERY_PROBE
```

Potwierdź Ready, zgodność prędkości UART po obu stronach oraz wersję
`1.0.8`, jeśli wgrano nowe MCU. Sprawdź [fabryczną rewizję i skalę Z](../en/HARDWARE_VARIANTS.md)
swojej płyty, np. HW04/Z800 lub HW05/Z400. Gdy dysza nie styka się ze
stołem, sonda powinna być otwarta. Zobacz, jak sprawdzić
[stan automatycznej synchronizacji licznika](MCU_FIRMWARE_1.0.8.md#odczyt-licznika).

Aby sprawdzić licznik na fizycznej drukarce, zanotuj minuty fabryczne przed
zwykłym wydrukiem przez `ZORTRAX_HARDWARE_STATUS`. Wydruk musi mieć co
najmniej minutę drukowania modelu. Gdy drukarka będzie bezczynna i spełni warunki zapisu, sprawdź `factory_counter_sync: SYNCED`,
`factory_counter_banks: NORMALIZED`, `factory_counter_pending: false` i wzrost
`factory_print_minutes`. Odczytaj tę wartość ponownie po następnym normalnym
wyłączeniu i włączeniu drukarki. Testy wydania symulują zapis Flash i
odzyskanie po przerwaniu zapisu.

Przed pomiarem stołu sprawdź układ pól poleceniem `BED_MESH PREVIEW=1`.
[Mesh i poziomowanie](BED_MESH_AND_LEVELING.md) · [Procedury druku](PRINT_CONTROL.md) ·
[Import z SD](../en/MODELS_SD.md) · [Ilustrowana instrukcja OLED](OLED_FUNCTIONS.md)

## Napraw Fluidd, a potem zaktualizuj Klippera

Jeśli masz klon w `~/m300-orange-pi`, przy bezczynnej drukarce w stanie Ready
uruchom przez SSH z konta Klippera:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --update-fluidd --port 4480 &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Pierwsze wywołanie instalatora naprawia statyczną stronę na 4480 i zachowuje
`config.json`. Drugie aktualizuje hosta Klippera. Otwórz
`http://<IP-hosta>:4480/` i wykonaj powyższe kontrole.

## Zaktualizuj lub napraw Fluidd

Użyj tego polecenia, gdy chcesz osobno zaktualizować stronę lub naprawić
rozpoznane wdrożenie Fluidd dla M300. Wykorzystuje istniejącą witrynę nginx
na 4480. Można je wykonać także przy niedostępnym Klipperze lub Moonrakerze.

```bash
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --update-fluidd --port 4480
```

Z pełnej paczki uruchom to samo polecenie z `python3 install-orange-pi.py`
w katalogu głównym ZIP-a. Przy niestandardowym układzie nginx opcja
`--fluidd-root /bezwzględna/ścieżka/do/fluidd` wskazuje istniejący,
zweryfikowany katalog strony. Instalator zachowuje konfigurację nginx,
`config.json` i preferencje Fluidd. Wynik `INSTALLED_M300_FLUIDD` z
`fluidd_http_verified: true` potwierdza, że nginx zwrócił przez HTTP
właściwy HTML oraz startowe pliki JavaScript i CSS. Instalator sprawdza
adres nasłuchu wybranej witryny, w tym adres LAN. Zachowaj ścieżki
`fluidd_root` i `fluidd_backup`. Wartość `null` przy kopii oznacza, że
zweryfikowano już zgodną stronę. Przy błędzie `FLUIDD_HTTP_UNVERIFIED`
polecenie kończy się błędem. Jeśli nastąpiła podmiana, instalator wymienia
katalogi z powrotem. Następnie sprawdź nginx i żądania HTTP opisane poniżej. [Wybór portu i ponawianie CI](INSTALLATION_AND_CI.md).

## Gdy Fluidd nie otwiera się lub pokazuje pustą stronę

Połącz się przez SSH z hostem i wykonaj:

```bash
base=http://127.0.0.1:4480
curl --noproxy '*' --silent --show-error --max-time 5 --output /dev/null \
  --write-out 'Fluidd: HTTP %{http_code}, %{size_download} B\n' "$base/"
curl --noproxy '*' --silent --show-error --max-time 5 --output /dev/null \
  --write-out 'Moonraker przez nginx: HTTP %{http_code}\n' "$base/server/info"
```

- **HTTP 200 i 0 bajtów dla Fluidd** oznacza pustą odpowiedź HTML.
  Przez `sudo nginx -T` znajdź aktywną witrynę na 4480 i sprawdź jej
  `index.html`. Aby naprawić rozpoznane wdrożenie M300, uruchom
  osobne polecenie Fluidd z poprzedniej sekcji.
- **HTTP 403 lub 404 dla Fluidd** wymaga sprawdzenia katalogu witryny,
  obecności pliku i uprawnień odczytu procesu nginx.
- **HTTP 000 lub błąd połączenia** wymaga sprawdzenia nginx poleceniami
  `sudo nginx -t`, `systemctl is-active nginx` i `sudo ss -ltnp`.
  Jeśli witryna nasłuchuje tylko na określonym adresie LAN, podstaw go
  za `127.0.0.1` w powyższych poleceniach.
- **Fluidd zwraca HTML, a Moonraker zwraca 502**. Sprawdź
  `systemctl is-active moonraker` i przekierowanie do Moonrakera w nginx.
- **Fluidd zwraca HTML, a przeglądarka jest pusta**. W panelu Sieć
  narzędzi deweloperskich sprawdź, czy główne żądanie
  `assets/index-*.js` zwraca niepusty plik JavaScript. Otwórz też adres w oknie prywatnym.

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
ponowną próbą.

## Przywróć poprzednią stronę Fluidd

Skopiuj **bezwzględną ścieżkę `fluidd_backup`** z potwierdzenia tej witryny.
Wartość `null` oznacza, że przy danej aktualizacji nie utworzono kopii.
W poniższym poleceniu zastąp przykładową ścieżkę tą z potwierdzenia.

```bash
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480 --restore-fluidd '/ścieżka/z/potwierdzenia/.m300-fluidd.ABC123.previous'
```

Instalator identyfikuje bieżący katalog witryny oraz sąsiednią kopię,
przywraca pliki statyczne i zachowuje bieżący `config.json`. Wymiana
katalogów jest atomowa. Po wyniku `RESTORED_M300_FLUIDD` sprawdź
`fluidd_http_verified: true` i otwórz menu Fluidd na porcie 4480.
Wskazana kopia pozostaje dostępna. Ponowienie z tą samą kopią sprawdza
już przywróconą wersję.
