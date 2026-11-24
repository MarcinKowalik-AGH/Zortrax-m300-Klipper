# Opcjonalna kamera USB w M300

Podłącz kamerę USB UVC do Orange Pi, na którym działa Klipper. Kamera jest
opcjonalna i domyślnie wyłączona. Zwykła instalacja i aktualizacja M300 nie
instalują oprogramowania kamery ani nie uruchamiają transmisji.

## Pierwsze włączenie

W terminalu SSH, jako użytkownik `klipper` użyty do KIAUH:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-camera.py --enable --apply
```

Polecenie wymaga aktualnej gałęzi `orange-pi`, opublikowanej po pomyślnym CI.
W klonie źródeł `main` odpowiednikiem jest `python3 ci/install_camera.py --enable --apply`.
Uruchomienie bez `--apply` jedynie pokazuje plan.

Instalator doinstaluje pakiety Debiana/Armbiana `ustreamer` i `v4l-utils`,
wybierze jedną kamerę USB oraz zapisze jej stałą ścieżkę, jeśli udostępnia ją
system. Przy kilku kamerach wskaż właściwą przez `--device`:

```bash
ls -l /dev/v4l/by-id/
python3 install-camera.py --enable --device /dev/v4l/by-id/usb-TWOJA_KAMERA-video-index0 --apply
```

Wpisz rzeczywistą ścieżkę z wyniku pierwszego polecenia. Instalator pomija
urządzenia metadanych i sprzętowe kodeki SoC.

Po powodzeniu odśwież Fluidd pod `http://m300:4480/` lub adresem IP hosta.
Podgląd nosi nazwę **M300 USB**. Gdy karta kamery jest ukryta w układzie
pulpitu, włącz ją w ustawieniach układu Fluidd.

## Włączenie i wyłączenie w konfiguracji

W edytorze konfiguracji Fluidd otwórz `m300_camera.conf`
(`~/printer_data/config/m300_camera.conf`). Najważniejsze ustawienia:

```ini
[camera]
enabled: True
device: /dev/v4l/by-id/usb-TWOJA_KAMERA-video-index0
resolution: 640x480
fps: 10
format: auto
port: 8088
fluidd_port: 4480
```

Po zapisaniu wykonaj w SSH:

```bash
cd "$HOME/m300-orange-pi" &&
python3 install-camera.py --apply
```

`enabled: False` wyłącza i zatrzymuje usługę transmisji, a także wyłącza
podgląd w Fluidd. Nie jest to tylko ukrycie obrazu. Można również użyć
`python3 install-camera.py --disable --apply`.

Ten plik obsługuje instalator kamery. **Nie dodawaj go do `printer.cfg`**.
Zmiany stosuje powyższe polecenie; sam zapis pliku ani `RESTART` Klippera
nie przełączają kamery. Przy innym katalogu danych podaj `--data /ścieżka/printer_data`.

Początkowe 640×480 i 10 kl./s ograniczają obciążenie hosta. Jeśli kamera
obsługuje 1280×720, możesz zmienić `resolution` na `1280x720` i ponownie
wykonać `--apply`. `format: auto` wybiera MJPEG z kamery, jeśli jest dostępny;
w przeciwnym razie YUYV z kodowaniem na hoście. `MJPEG` i `YUYV` można też
wybrać jawnie. Tryby kamery sprawdzisz poleceniem:

```bash
v4l2-ctl --device /dev/video0 --list-formats-ext
```

## Podgląd i diagnostyka

Instalator dodaje wpis kamery przez API Moonrakera bez jego restartu. Usługa
`m300-camera.service` działa jako użytkownik Klippera, z dostępem do grupy
`video`, niższym priorytetem CPU i automatycznym startem po restarcie systemu.
Nie zmienia firmware MCU, makr ani konfiguracji ruchu/temperatur.

Strumień działa przez tę samą witrynę i port Fluidd:

| Cel | Adres |
|---|---|
| Obraz MJPEG | `/m300-camera/stream` |
| Pojedyncze zdjęcie JPEG | `/m300-camera/snapshot` |
| Stan przechwytywania | `/m300-camera/state` |

Backend nasłuchuje lokalnie na `127.0.0.1:8088`. Instalator dodaje oznaczony
blok do aktywnej witryny nginx na `fluidd_port`, sprawdza `nginx -t`,
przeładowuje nginx i weryfikuje obraz przez HTTP. Przy błędzie przywraca
poprzednią konfigurację nginx i usługę kamery. Kopia i potwierdzenie zmian
są zapisane w katalogu `m300-camera-backup-*` obok konfiguracji.

```bash
systemctl status m300-camera.service --no-pager
journalctl -u m300-camera.service -n 80 --no-pager
curl --fail http://127.0.0.1:4480/m300-camera/state
```

Jeśli masz już Crowsnest lub inny streamer używający tej samej kamery,
zatrzymaj go przed włączeniem tej opcji albo pozostań przy istniejącym
streamerze. Instalator nie zatrzymuje cudzych usług. Przy niestandardowej
witrynie nginx użyj `--nginx-site /etc/nginx/sites-available/fluidd` i
ustaw rzeczywisty `fluidd_port` w konfiguracji.

Wyłączenie transmisji jest możliwe bez podłączonej kamery. Jeśli Moonraker
jest niedostępny, kamera zostaje zatrzymana, a komunikat wyjaśnia, że wpis
w Fluidd wymaga ponownego zastosowania po jego uruchomieniu.

Testy oprogramowania obejmują konfigurację, domyślne wyłączenie, dobór urządzeń,
nginx, API i przywracanie po błędzie. Odbiór obrazu z konkretnej kamery wymaga
wykonania instalatora na docelowym Orange Pi; dopiero `video_verified: true`
potwierdza sprawdzenie strumienia i zdjęcia na tym hoście.
