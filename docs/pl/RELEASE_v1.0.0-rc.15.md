# M300 Classic RC15

Tryb Dynamic utrzymuje białe światło po zakończeniu `START_PRINT` dla
bieżącego pliku SD, również gdy cele grzania zmieniają się po rafcie.
Rozpoznanie tej fazy działa niezależnie od licznika czasu druku.
Przygotowanie, pauza, alarmy, wybór trybu światła i jasność mają własne reguły.

RC14 i RC15 prowadzą cztery linie na jednej zadanej wysokości czyszczenia,
domyślnie Z0,28. Aktywna kompensacja siatki może dać widoczny ruch Z przy
przejściu z Y w X. Starszy kontroler `0.13.16.38-PRINT-DRAIN-XY-PURGE`
zlecał dodatkowe odsunięcie do Z5 między tymi parami.

## Zaktualizuj Klippera

Poczekaj na stan Ready, zakończ wydruk i procedury oraz wyłącz cele grzania.
Uruchom z konta Klippera:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Jeśli drukarka ma już MCU 1.0.5, wystarczy aktualizacja hosta.
Pełna paczka zawiera `MCU/M300_SD.zip` do pierwszej instalacji. Fluidd
działa na dotychczasowym porcie 4480. Osobne polecenie
`--update-fluidd --port 4480` służy do jawnej naprawy strony.
[Pierwsza instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.15/docs/pl/FIRST_INSTALL.md) ·
[Instrukcja aktualizacji](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.15/docs/pl/INSTALL.md)

## Sprawdź wynik

```gcode
PRINT_CONTROL_STATUS
ZORTRAX_MAINTENANCE_STATUS
ZORTRAX_ERROR_STATUS
```

`PRINT_CONTROL_STATUS` podaje rewizję `0.13.16.40-PRINT-LIGHT` oraz
`model_print_ready: true` po zakończeniu czyszczenia dla bieżącego pliku.
Jeśli światło świeci na czerwono, odczytaj `status_led.state`.
`HEATING` oznacza grzanie. `ERROR` oznacza sygnał błędu, którego
szczegóły podaje `ZORTRAX_ERROR_STATUS`.

Testy programowe sprawdzają stan gotowości pliku i zadaną wysokość linii
czyszczących. Próba na drukarce pozostaje do wykonania. Ilustracje OLED
z beta.20 pochodzą z historycznej wersji.
