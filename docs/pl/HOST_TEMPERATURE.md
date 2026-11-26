# Opcjonalna temperatura hosta

Na wykresie Fluidd pojawia się jedna dodatkowa seria **Host**: temperatura CPU.
Odczyty DDR, NPU, drugiej grupy CPU i GPU są dostępne na żądanie przez SSH.
Nie są dodawane jako kolejne serie wykresu. Funkcja jest domyślnie wyłączona.

## Działająca instalacja

W gałęzi `orange-pi` pobierz pliki i skopiuj szablon, jeśli jeszcze go nie masz:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
cp -n FIRST_INSTALL/m300_host_temperature.cfg "$HOME/printer_data/config/"
```

Do tej opcji nie jest potrzebne uruchamianie `install-orange-pi.py`.
Nowa instalacja kopiuje plik automatycznie, pozostawiając include zakomentowany.

W `printer.cfg`, przed blokiem `SAVE_CONFIG`, włącz:

```ini
[include m300_host_temperature.cfg]
```

Aby wyłączyć, zakomentuj tę samą linię:

```ini
# [include m300_host_temperature.cfg]
```

Po zmianie, przy bezczynnej drukarce, wykonaj w konsoli Fluidd `FIRMWARE_RESTART`.
Konfiguracja zawiera tylko czujnik pomiarowy, bez sterowania grzałką.

## Pozostałe odczyty

Przez SSH uruchom:

```bash
python3 "$HOME/m300-orange-pi/read-host-temperatures.py"
```

Opcja `--json` zwraca dane do dalszego przetwarzania. Polecenie tylko czyta pliki
systemowe; działa także przy wyłączonym include, bez restartu i bez zapisu historii.

| Strefa potwierdzona na Orange Pi Zero 4 / A733 | Typ | Sposób prezentacji |
|---|---|---|
| thermal_zone0 | cpub_thermal_zone | Jedyna seria Host w Fluidd |
| thermal_zone1 | ddr_thermal_zone | Odczyt na żądanie |
| thermal_zone2 | npu_thermal_zone | Odczyt na żądanie |
| thermal_zone3 | cpul_thermal_zone | Odczyt na żądanie |
| thermal_zone4 | gpu_thermal_zone | Odczyt na żądanie |

Na innej płytce lub po zmianie mapowania stref sprawdź wynik polecenia i dopasuj
`sensor_path` w `m300_host_temperature.cfg` do strefy CPU. Nie włączaj include,
jeśli wskazany plik nie istnieje lub nie jest czytelny dla użytkownika Klippera.
MCU nie jest dodawane przez tę opcję: odczyt wewnętrznego czujnika STM32 wymaga
osobnego sprawdzenia obsługi w firmware M300.
