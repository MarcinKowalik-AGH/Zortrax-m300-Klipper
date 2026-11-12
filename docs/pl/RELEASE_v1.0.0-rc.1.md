# Zortrax M300 Classic v1.0.0-rc.1 — wspólne menu OLED, makra Fluidd i procedury Klippera

[Instrukcja główna](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/main/README_PL.md) · [Katalog makr](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/main/docs/pl/MACRO_REFERENCE.md) · [Odbiory sprzętowe](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/main/docs/pl/ACCEPTANCE_REGISTER.md)

RC1 nie wprowadza drugiego zestawu ruchów ani oddzielnych nastaw dla przeglądarki.
Makra są krótkimi wejściami do tych samych kontrolerów, które obsługują OLED.
Fizyczny wyświetlacz, podgląd Fluidd i menu potwierdzeń nadal pokazują wspólną
sesję procedury. Zamknięcie okna nie jest zgodą na następny ruch.

## Ustawienia: kliknięcie otwiera, parametr ustawia

| OLED: Settings | Makro we Fluidd | Parametr |
|---|---|---|
| Light | ZORTRAX_LIGHT | MODE=DYNAMIC/WHITE/DISABLED |
| Buzzer | ZORTRAX_BUZZER | STATE=ENABLED/DISABLED |
| Sleep mode | ZORTRAX_SLEEP_MODE | STATE=ENABLED/DISABLED |
| Language | ZORTRAX_LANGUAGE | English; brak innych języków |
| Models sorting | ZORTRAX_MODELS_SORT | MODE=DATE/NAME/NAME_CASE/SIZE |
| Full platform preheating | ZORTRAX_FULL_PLATFORM_PREHEAT | STATE=ENABLED/DISABLED |
| OLED brightness | ZORTRAX_OLED_BRIGHTNESS | LEVEL=1…16 |
| LED brightness | ZORTRAX_LED_BRIGHTNESS | LEVEL=1…16 |

Bez parametru makro otwiera aktualny wybór bez zmiany ustawienia. Przykład:

```gcode
ZORTRAX_OLED_BRIGHTNESS
ZORTRAX_LED_BRIGHTNESS LEVEL=8
```

LEVEL jest liczbą całkowitą 1–16. Wartości 0, 17, ułamki i nieprawidłowy tekst
są odrzucane przez wspólnego właściciela ustawień, bez zaokrąglania. Zapis
nadal trafia do istniejącego m300_nvm. Synchronizacja otwartego regulatora OLED
z przeglądarką i zapamiętywanie ustawień nie zostały zastąpione nową obsługą.
ZORTRAX_SCREEN pozostaje odczytem statusu wyświetlacza, nie regulatorem jasności.

## Ruch, serwis i druk

| Funkcja OLED | Wejście Fluidd / konsola | Wspólna realizacja |
|---|---|---|
| Home X/Y/Z/XY/XYZ | ZORTRAX_HOME_X/Y/Z/XY/ALL | ZORTRAX_PROCEDURE_START i natywne bazowanie |
| Autocalibration | ZORTRAX_LEVEL | M07, potwierdzenia aktualnej fazy |
| Bed mesh | BED_MESH | m300_pad_mesh, 25 pozycji kontaktowych |
| Heat extruder / platform | ZORTRAX_HEAT / ZORTRAX_HEAT_PLATFORM | dotychczasowa procedura grzania i potwierdzenia |
| Load / Unload / Change | ZORTRAX_LOAD / UNLOAD / CHANGE | wspólna obsługa materiału; wznowienie osobno |
| Move platform up/down | ZORTRAX_PLATFORM_UP/DOWN | natywny ruch Z i kontrola zakresu; przytrzymanie na OLED, krok we Fluidd |
| Fan test | ZORTRAX_FAN_TEST_START / UPPER / LOWER / END | OEM-owa kontrola wentylatorów; chłodzenie ochronne ma pierwszeństwo |
| Current procedure | ZORTRAX_PROCEDURE | ponowne otwarcie istniejącej sesji bez uruchamiania nowej |
| Pause / Resume / Cancel | PAUSE / RESUME / CANCEL_PRINT | m300_print_control; warunki wydruku i pozycja nadal sprawdzane |
| PID calibration | PID_HOTEND / PID_BED / PID_SAVE | natywny PID; zapis i restart wyłącznie na postoju |
| Information / Help | ZORTRAX_INFORMATION / ZORTRAX_HELP | wspólne dane wersji, drukarki i błędów |

Modele we Fluidd wybiera się także przez standardową kartę plików. Nie dodano
makra, które obchodzi sprawdzanie wybranego pliku. Nie dodano eksperymentalnej
strefy Y315 ani czyszczenia wymagającego podnoszenia stołu pod wydrukiem.

## Co znika z panelu

Menu główne OLED zawiera tylko **Klipper** i **Zortrax M300**. Usunięto stronę
Service / Tests z laboratoryjnymi przejazdami XY i powielonymi procedurami.
Fluidd nie tworzy grupy TEST M300 i ukrywa stare laboratoryjne wpisy także po
odczytaniu zapisanych preferencji przeglądarki. Pusta zarządzana grupa jest
usuwana; grupa zawierająca niepowiązane własne makra nie jest kasowana.

Instalator wycofuje tylko rozpoznane ciała starych makr. Własne dodatkowe
polecenia, zmienne lub zmodyfikowana definicja nie są usuwane. Kopia i rollback
obejmują zmienione pliki. Testy programowe pozostają w repozytorium; nie są
instalowane jako przyciski na drukarce. ZORTRAX_DIAGNOSTICS zapewnia wygodny
odczyt stanu bez ruchu i grzania. Test wentylatorów pozostaje, bo jest rzeczywistą
funkcją serwisową OEM, a nie testem rozwoju portu.

## Wersje i aktualizacja

Wersja publiczna to **1.0.0-rc.1**. Information pokazuje krótki numer hosta i
numeryczny numer MCU. Pełny rzeczywisty identyfikator firmware i znaczniki
zgodności transportu pozostają w diagnostyce; nie udajemy, że MCU otrzymało
nowe oprogramowanie. Pakiet używa nazw M300_HOST, M300_FLUIDD.zip i M300_SD.zip.

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Tylko bezczynna drukarka Ready, bez pauzy. Instalator zachowuje już wprowadzone
Z=-0,5 / M07 5–6,5–1 / odsunięcie styku 2 mm, siatkę m300_pads, PID i UART.
Parametr --qualified-first-print-z nadal służy do jawnego wdrożenia tego wariantu
na zakwalifikowanym egzemplarzu; RC1 nie stosuje go automatycznie do innych drukarek.
Odśwież Fluidd przez Cmd+Shift+R. RC to kandydat do wydania, nie potwierdzenie
ukończenia całej listy prób sprzętowych. Dotychczasowe 65 ilustracji beta.20
pozostaje opisanym materiałem historycznym; bieżące różnice określa ten rozdział.

Firmware MCU pozostaje `0.13.14.19-TONED-OLED-UART8`; `MCU/M300_SD.zip` nie jest potrzebny do tej aktualizacji hosta.
