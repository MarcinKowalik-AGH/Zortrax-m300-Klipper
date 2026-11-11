# M300 Classic — instalacja Git na Orange Pi

**Aktualny host: R16.12 + M300-305-105-R1. Maksymalne nastawy: ekstruder305°C, stół105°C.** Odcięcia czujników:310/120°C. MCU, Fluidd i dotychczasowy instalator bez zmian.

## Aktualizacja istniejącej instalacji

Drukarka musi być bezczynna, Klipper Ready. Uruchom jako użytkownik Klippera, nie root:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Instalator odczytuje aktywne ścieżki Klippera i printer.cfg z lokalnego Moonrakera; nie zakłada katalogu ~/klipper. Weryfikuje pliki, przygotowuje kopię/receipt, zatrzymuje Klippera na czas aktualizacji i uruchamia go ponownie. Nie zmienia portu Fluidd, nie flashuje MCU i nie uruchamia grzania.

## Pierwsze pobranie tej gałęzi

```bash
git clone --branch orange-pi --single-branch https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper.git "$HOME/m300-orange-pi" &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Nie używaj clone, jeżeli katalog już istnieje. Gdy Git zgłosi lokalne zmiany, nie wykonuj reset --hard ani kasowania katalogu w ciemno.

## Sprawdzenie w konsoli Fluidd

```gcode
ZORTRAX_TEMPERATURE_LIMITS
STATUS
```

Oczekiwane revision=M300-305-105-R1, bound=true, target_limits305/105 i sensor_shutdown_limits310/120. To polecenia informacyjne.

## Walidacja

768 testów hosta ponownie PASS; przejście z poprzedniej gałęzi orange-pi, dołączone pliki konfiguracyjne, zachowanie PID/UART/rotation_distance, idempotencja i rollback sprawdzone na tymczasowym systemie plików. Test305/105 na sprzęcie został zgłoszony przez użytkownika11.11.2026; nie jest to deklaracja testów wszystkich materiałów. Raport: THERMAL305_VALIDATION.json.

Profile Orca są w oddzielnym repozytorium Zortrax-m300-Orca-Slicer. Ta aktualizacja nie instaluje Orca na Orange Pi ani na komputerze.
