# Zortrax M300 Classic v1.0.0-beta.24 — instalacja od początku

> **Instalator beta.23:** przykłady dotyczą portu 4480. Nowa instalacja KIAUH pozostająca na 80 wymaga `--port 80` lub jednoznacznego wykrycia; instalator nie zmienia nginx. Po sukcesie zapisuje port/katalog obok printer.cfg. [Szczegóły](INSTALLATION_AND_CI.md).

Instrukcja zakłada, że w drukarce jest już zgodny bootloader M300 obsługujący
aktualizację z SD, a na Raspberry Pi lub Orange Pi nie ma jeszcze oprogramowania
drukarki. Wydanie jest przeznaczone dla **klasycznego M300, STM32F103,
oryginalnego hotendu, płyty kontaktowej i dyszy 0,4 mm**. M300 Plus, Dual
i Inventure mają inne układy; ta paczka ich nie obsługuje.

## Co pobrać: gotową paczkę czy patch?

**Zalecana jest gotowa, wersjonowana paczka z naszego GitHuba.** KIAUH służy
do przygotowania usług systemowych i zależności. Następnie nasz instalator
zastępuje jego tymczasowego Klippera oraz Fluidd sprawdzonym zestawem M300.
Nie trzeba ręcznie kopiować patchy ani kompilować firmware drukarki lub Fluidd.

| Element | Co otrzymuje użytkownik |
|---|---|
| System Linux | Obraz dobrany do konkretnego Raspberry Pi lub Orange Pi; nie ma jednego obrazu pasującego do obu rodzin |
| Klipper host | Pełne źródła przypiętej wersji z kompletem zmian M300, nie same moduły extras |
| MCU | Gotowy `MCU/M300APP.M3B`, R14.19, do posiadanego bootloadera SD |
| Fluidd | Gotowa kompilacja 1.37.7 z menu i wizualizacją M300 |
| Konfiguracja | Oddzielne pliki sprzętu, termiki, procedur i makr; ścieżki i UART ustawia instalator |
| Kontrola wydania | Sumy SHA-256, identyfikator źródeł, raporty testów i licencje |

Klipper jest przypięty do `ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`.
Nie należy brać najnowszego Klippera i nakładać na niego kilku plików tego portu.
Host jest głównie w Pythonie. Jego mała biblioteka C zostanie zbudowana na
docelowej płytce, aby pasowała do ARM32/ARM64. Nie dostarczamy jej w wersji x86
z serwera budującego. Moonraker i usługi systemowe pochodzą z instalacji KIAUH;
nie są częścią zamrożonej kompilacji MCU/Fluidd.

## 1. System, sieć i UART

Na Raspberry Pi wybierz Raspberry Pi OS Lite Bookworm/Debian 12 z Pythonem 3.11,
a na Orange Pi wspierany obraz Debian 12 lub Ubuntu 24.04 dla
**dokładnego modelu płytki**. Włącz SSH,
ustaw sieć i utwórz zwykłego użytkownika z sudo. Wszystkie dalsze polecenia
wykonuj jako ten użytkownik.

Instalator pierwszego uruchomienia obsługuje Python **3.10–3.12**. Dobrym punktem
wyjścia jest Debian 12 z Pythonem 3.11 albo Ubuntu 24.04 z Pythonem 3.12,
jeżeli taki obraz jest dostępny dla płytki. CI sprawdza Python 3.12; instalacja
całego systemu na każdym modelu SBC pozostaje osobnym testem sprzętowym.
System z Pythonem 3.13 wymaga zgodnego środowiska 3.10–3.12.

| Host | Ustawienie portu |
|---|---|
| Raspberry Pi | `sudo raspi-config`: wyłącz konsolę logowania po serial, włącz sprzęt UART i zrestartuj system. Sprawdź `readlink -f /dev/serial0`; alias i typ UART zależą od modelu Pi. |
| Orange Pi | Włącz nakładkę UART właściwą dla modelu i systemu. W naszym przetestowanym hoście działa `/dev/ttyS1`; inne modele mogą mieć inną nazwę i piny. |

Połącz UART 3,3 V zgodnie z dokumentacją płytki i posiadanego bootloadera:
TX hosta do RX MCU, RX hosta do TX MCU i wspólne GND. Numery pinów należy
sprawdzić dla danego modelu. OLED nadal podłączony jest do MCU drukarki,
więc nie trzeba podłączać go do SPI Raspberry Pi lub Orange Pi.
Konfiguracja kompilacji MCU M300 używa USART1: PA9 to TX, a PA10 to RX MCU.
To nazwy sygnałów procesora, nie potwierdzona numeracja styków złącza DEBUG.
Nie należy podstawiać numeracji P4 z Inventure.

Ustaw **750000 baud po obu stronach**, także w ustawieniu UART bootloadera.
Dla tego łącza mamy czysty test ruchów XY do zadanych 400 mm/s. Próba 1500000
wykazała retransmisje, dlatego nie jest domyślną rekomendacją tej bety.
Instalator nie przestawia prędkości w drukarce.

Sprawdź wybrany port, zastępując `ttyS1` właściwą nazwą:

```bash
ls -l /dev/ttyS1
sudo fuser -v /dev/ttyS1
systemctl is-active serial-getty@ttyS1.service
tr ' ' '\n' </proc/cmdline | grep '^console='
```

Na tym porcie nie może działać konsola systemowa ani inny program. Jeśli
użytkownik nie ma praw do portu, dodaj go do grupy urządzenia, zwykle poleceniem
`sudo usermod -aG dialout "$USER"`, i zaloguj się ponownie.

## 2. KIAUH: przygotowanie usług

```bash
sudo apt-get update
sudo apt-get install -y git curl unzip build-essential python3-dev libffi-dev
git clone https://github.com/dw-0/kiauh.git "$HOME/kiauh"
"$HOME/kiauh/kiauh.sh"
```

Wybierz **Install → Klipper → jedna instancja**, następnie **Moonraker**
i **Fluidd**. Zachowaj standardowe ścieżki `~/klipper`, `~/klippy-env`,
`~/printer_data` i usługi `klipper.service`, `moonraker.service`.
Dla Fluidd wybierz **port 80**. Przy innym porcie trzeba później podać tę
wartość instalatorowi. Na tym etapie nie ustawiaj silników, grzałek ani innej
drukarki. Początkowy błąd pustej konfiguracji Klippera jest spodziewany.

## 3. Pobranie stałej wersji beta

Paczka Release jest dostępna publicznie, bez logowania do GitHuba.

```bash
mkdir -p "$HOME/m300-releases" &&
cd "$HOME/m300-releases" &&
curl -fLO https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/download/v1.0.0-beta.24/Zortrax_M300_Klipper_v1.0.0-beta.24.zip &&
curl -fLO https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/download/v1.0.0-beta.24/SHA256SUMS-v1.0.0-beta.24.txt &&
grep '  Zortrax_M300_Klipper_v1.0.0-beta.24.zip$' SHA256SUMS-v1.0.0-beta.24.txt | sha256sum -c - &&
unzip Zortrax_M300_Klipper_v1.0.0-beta.24.zip &&
cd Zortrax_M300_Klipper_v1.0.0-beta.24 &&
sha256sum -c --quiet SHA256SUMS
```

## 4. Wgranie aplikacji MCU

Skopiuj **`MCU/M300APP.M3B`** do katalogu głównego karty SD zgodnej z posiadanym
bootloaderem. Zatrzymaj tymczasowego Klippera: `sudo systemctl stop klipper`.
Uruchom przewidzianą w bootloaderze aktualizację aplikacji z karty. Zachowaj
750000 baud. Po poprawnym wgraniu wyjmij kartę aktualizacyjną albo usuń plik
aktualizacji przed kolejnymi uruchomieniami.

Plik zawiera aplikację od adresu **0x08008000**. Nie jest wsadem bootloadera,
pełnym zrzutem Flash ani poleceniem kasowania fabrycznych danych. Instalator
hosta nie wykonuje tej operacji automatycznie.

## 5. Pierwsza instalacja M300 na hoście

W katalogu rozpakowanej paczki:

```bash
sudo systemctl start klipper
python3 install-fresh.py --serial /dev/ttyS1 --baud 750000 --port 4480
```

To wyświetla plan. Dla Raspberry Pi podstaw port wybrany w punkcie 1,
np. `--serial /dev/serial0`. Po sprawdzeniu ścieżek zastosuj ten sam wybór:

```bash
python3 install-fresh.py --serial /dev/ttyS1 --baud 750000 --port 4480 --apply
```

Instalator sprawdza sumy plików, rozpoznaje pustą konfigurację KIAUH i odmawia
nadpisania istniejącej drukarki lub portu M300. Instaluje przypięte zależności
Pythona, buduje bibliotekę dla procesora hosta, zachowuje starego Klippera
i konfigurację, instaluje hosta M300 oraz gotowy Fluidd, a następnie restartuje
usługi. Zachowuje `config.json` Fluidd oraz poprzedni katalog strony.
Usuwa rozpoznane aktualizatory stockowego Klippera/Fluidd, aby późniejsza
aktualizacja nie nadpisała portu. Niestandardowe źródła wymagają ręcznego przeglądu.
Nie zmienia nakładek UART, ustawień startu Linuxa ani firmware MCU; nie wysyła
bazowania, ruchu lub grzania.

Przy błędzie zachowaj komunikat i katalog
`~/m300-first-install-backup-<data>`. Błąd w trakcie wymiany hosta, konfiguracji
lub strony przywraca poprzednie pliki. Samo zainstalowanie plików nie
potwierdza komunikacji z MCU — trzeba sprawdzić stan Ready.

## 6. Kontrola po instalacji

Otwórz `http://<IP-hosta>/`, odśwież Fluidd z pominięciem pamięci przeglądarki
i odczytaj bez wykonywania ruchów:

```gcode
ZORTRAX_MCU_STATUS
ZORTRAX_OLED_STATUS
ZORTRAX_INFO REFRESH=0
PRINT_CONTROL_STATUS
QUERY_ENDSTOPS
QUERY_PROBE
M105
```

Oczekiwane: Ready, zgodne 750000 baud, MCU `0.13.14.18-OEM-ERRORS-UART8`,
kontroler druku `0.13.16.29-UNIFIED-NATIVE-START`, cele temperatur 0°C i poprawne
odczyty temperatury otoczenia. Sprawdź reakcje krańcówek i styku dyszy.
[Profil fabrycznej rewizji i osi Z](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-beta.24/docs/en/HARDWARE_VARIANTS.md)
powinien odpowiadać drukarce. Nie należy zgadywać skali Z po błędzie odczytu
fabrycznej rewizji.

Konfiguracja startowa przewiduje X0..300, Y0..305, Z0..300 i park X300 Y305.
Przed wykorzystaniem pełnego zakresu/parkowania sprawdź faktyczny prześwit,
zakresy, skalę Z, średnicę dyszy i kalibrację ekstrudera na własnym egzemplarzu.
PID jest wartością początkową, a nie pomiarem danej maszyny. Następnie wykonaj
pod nadzorem próbę homingu, regulację PID dla używanego materiału i oryginalne
pięciopunktowe poziomowanie mechaniczne. Przed 25-punktowym `BED_MESH` ustaw
i sprawdź podgląd granic metalowych pól. Różne płyty mają różne pola;
instalator nie kopiuje indywidualnie zmierzonych prostokątów z drukarki autora.

W OrcaSlicer ustaw jedną wspólną procedurę startową:

```gcode
START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single]
```

Procedura końcowa:

```gcode
END_PRINT
```

[Opis pauzy, parkowania, M600 i wznowienia](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-beta.24/docs/pl/PRINT_CONTROL.md).

## Aktualizacje i zakres potwierdzenia

Tag i pliki `v1.0.0-beta.24` pozostają niezmienne. Gałąź `orange-pi` jest kanałem
późniejszych aktualizacji projektu. Po tej pierwszej instalacji można ją
sklonować i używać zwykłego instalatora `install-orange-pi.py --port 4480`
(beta.23 preferuje 4480 i ponownie sprawdza zapisany port/katalog). Nie aktualizuj portu przyciskiem
instalującym stockowego Klippera lub Fluidd. System Linux i Moonraker to osobne
komponenty — przed ich zmianą zachowuj kopie konfiguracji.

Raporty w paczce obejmują 702 testy hosta, prawdziwe procesy Klippera FILEOUTPUT,
test pierwszej konfiguracji oraz budowanie ARM i Fluidd. Nie zastępują prób
na wszystkich płytkach SBC, rewizjach drukarki i eksportach Z-Suite.
Potwierdzony sprzętowo jest m.in. test XY na HW05 przy 750000 baud. Na nowej
instalacji pozostają do wykonania wydruk, pauza/wznowienie/M600 i ocena łącza.

Źródła instalacji systemowej: [KIAUH](https://dw-0.github.io/kiauh/setup/installation/),
[UART Raspberry Pi](https://www.raspberrypi.com/documentation/computers/configuration.html),
[Armbian](https://docs.armbian.com/User-Guide_Getting-Started/),
[Moonraker](https://moonraker.readthedocs.io/en/latest/installation/).


## Dokumentacja po uruchomieniu

[Obsługa](USER_GUIDE.md) · [Menu OLED i rendery](OLED_MENU_REFERENCE.md) · [Mesh](BED_MESH_AND_LEVELING.md) · [Parametry i termika](TECHNICAL_REFERENCE.md) · [Spis dokumentacji](../../README_PL.md).

Ta instrukcja opisuje pierwszą instalację. Dokumentacja użytkowa z 10.11.2026 nie zmienia kodu wykonawczego beta.20 ani parametrów istniejącej drukarki. Host API podglądu to NAV-EVENT-1, pipeline frontendu to NAV-PIPELINE-2, wygląd przycisków to OLED-ZOOM-2, a panel Tune to TUNE-PREPARE-1.

## Podgląd i instrukcja ekranowa po instalacji beta.20

Sprawdź [ilustrowaną instrukcję 65 funkcji OLED](OLED_FUNCTIONS.md) i [zmiany z 10.11.2026](UPDATE_2026-11-10.md). W prawym dolnym obszarze karty temperatur są przyciski ×1/×2/×3 pod HIDE; ekran pozostaje wycentrowany. Tune jest dostępne również przed pierwszym pomiarem; samo wejście nie wykonuje ruchu. All oznacza bazowanie, Calibrate — BED_MESH. Użytkownik potwierdził poprawny wygląd podglądu beta.20; nie zastępuje to odbioru nowej instalacji sprzętowej.
