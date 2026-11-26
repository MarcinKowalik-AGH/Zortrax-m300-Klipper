# Opcjonalna temperatura hosta

Wykresy **Host** (CPU Orange Pi) i **MCU** (STM32) są niezależnymi opcjami.
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
| thermal_zone0 | cpub_thermal_zone | Seria Host w Fluidd |
| thermal_zone1 | ddr_thermal_zone | Odczyt na żądanie |
| thermal_zone2 | npu_thermal_zone | Odczyt na żądanie |
| thermal_zone3 | cpul_thermal_zone | Odczyt na żądanie |
| thermal_zone4 | gpu_thermal_zone | Odczyt na żądanie |

Na innej płytce lub po zmianie mapowania stref sprawdź wynik polecenia i dopasuj
`sensor_path` w `m300_host_temperature.cfg` do strefy CPU. Nie włączaj include,
jeśli wskazany plik nie istnieje lub nie jest czytelny dla użytkownika Klippera.
Temperaturę STM32 włącza osobny dodatek opisany poniżej.

## Temperatura STM32 — opcjonalny odczyt i wykres

MCU 1.0.9 dodaje potwierdzoną przez protokół obsługę wewnętrznego kanału ADC16.
Dodatek Klippera `m300_mcu_temperature.py` korzysta z tego kanału co 5 sekund,
bez komend odczytu pamięci debug. Po włączeniu include udostępnia również
standardowy czujnik `temperature_sensor MCU`, widoczny na wykresie Fluidd.
To widok tego samego pomiaru ADC, bez dodatkowego próbkowania i bez grzałki.

Po wgraniu MCU 1.0.9 według [instrukcji firmware](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/main/docs/pl/MCU_FIRMWARE_1.0.9.md),
na bezczynnej drukarce skopiuj pliki z aktualnej gałęzi `orange-pi`:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py &&
cp -n FIRST_INSTALL/m300_mcu_temperature.cfg "$HOME/printer_data/config/"
```

W `printer.cfg`, przed `SAVE_CONFIG`, dodaj:

```ini
[include m300_mcu_temperature.cfg]
```

Instalator wykonuje pełny restart procesu potrzebny po zmianie modułów Python.
Po zapisaniu include i ponownym połączeniu Fluidd wykonaj w jego konsoli
`FIRMWARE_RESTART`, aby rozpocząć nową sesję MCU. Poczekaj na `Ready`
i około 5 sekund na próbkę, a następnie odczytaj:

```gcode
M300_MCU_TEMPERATURE
```

Odczyt jest także dostępny przez Moonraker:

```bash
curl -sS 'http://127.0.0.1:7125/printer/objects/query?m300_mcu_temperature'
```

Wartości `temperature`, `adc_fraction`, `adc_raw` i `sample_age` opisują bieżący
pomiar. Przy braku świeżych danych temperatura ma wartość `null`, a pole `state`
wyjaśnia przyczynę. Czujnik mierzy temperaturę struktury STM32, nie całej płyty.
Przeliczenie wykorzystuje nominalne parametry STM32F103; jest orientacyjne.
W pliku dodatku można ustawić rzeczywiste `adc_voltage` i `temperature_offset`.

Wyłączenie: zakomentuj `[include m300_mcu_temperature.cfg]` i wykonaj
`FIRMWARE_RESTART`. Przed powrotem do MCU 1.0.8 także wyłącz ten include.
Na starszym firmware dodatek zgłasza potrzebę aktualizacji zamiast pozorować pomiar.

## Niezależne włączanie w głównym printer.cfg

Oba include są domyślnie zakomentowane. Odkomentuj tylko wybrane opcje:

```ini
[include m300_host_temperature.cfg]
[include m300_mcu_temperature.cfg]
```

Aby wyłączyć obie, zakomentuj je:

```ini
# [include m300_host_temperature.cfg]
# [include m300_mcu_temperature.cfg]
```

Po zmianie konfiguracji wykonaj `FIRMWARE_RESTART`. Wyłączony include nie ładuje
czujnika, jego pliku ani obsługi ADC i nie wymaga danej funkcji sprzętowej.
Dlatego wyłączenie MCU pozwala też uruchomić Klippera na starszym firmware.
Gdy MCU jest włączone, wykres pojawia się domyślnie; `show_on_graph: False`
w jego osobnym cfg pozostawia tylko diagnostykę. Przy braku świeżej próbki
wykres ma brak danych, a nie zapamiętaną starą temperaturę.
