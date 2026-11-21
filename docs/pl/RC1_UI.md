# Menu OLED, Fluidd i makra Klippera w RC34

We Fluidd i w zakładce Device OrcaSlicera otwórz `M300_MAIN_MENU`. Models, Maintenance, Material, Settings i Information odpowiadają pięciu pozycjom menu Zortrax na OLED. Dla przykładu **Material → Unload the material** prowadzi do tej samej procedury z obu urządzeń, a potwierdzenie dotyczy aktualnej fazy. Przy zmianie koloru w pauzie przyciski Extrude/Retract działają przed potwierdzeniem wypływu. [Codzienna obsługa](USER_GUIDE.md).

W aktualnym wydaniu oba czasy OLED mierzy się od ostatniej obsługi w Ready, podczas druku i w pauzie. Ustaw je w **OLED_TIMERS** lub **M300_OLED_TIMERS**. Przykład `DIM=1 SLEEP=2` przygasza ekran po minucie i wyłącza go po dwóch. Obie wartości mieszczą się w zakresie 1–60 min, a rzeczywisty DIM jest mniejszą z dwóch wartości: wybranego DIM i aktualnego SLEEP. Pierwszy gest wybudza panel. [Opis działania](RELEASE_v1.0.0-rc.23.md).

[Instrukcja główna](../../README_PL.md) · [Katalog makr](MACRO_REFERENCE.md) · [Odbiory sprzętowe](ACCEPTANCE_REGISTER.md)

RC1 nie wprowadza drugiego zestawu ruchów ani oddzielnych nastaw dla przeglądarki.
Makra są krótkimi wejściami do tych samych kontrolerów, które obsługują OLED.
Fizyczny wyświetlacz, podgląd Fluidd i menu potwierdzeń nadal pokazują wspólną
sesję procedury. Zamknięcie okna nie jest zgodą na następny ruch.

## Ustawienia: kliknięcie otwiera, parametr ustawia

| OLED: Settings | Makro we Fluidd | Parametr |
|---|---|---|
| Light | M300_LIGHT | MODE=DYNAMIC/WHITE/DISABLED |
| Buzzer | M300_BUZZER | STATE=ENABLED/DISABLED |
| Sleep mode | M300_SLEEP_MODE | STATE=ENABLED/DISABLED |
| Language | M300_LANGUAGE | English; brak innych języków |
| Models sorting | M300_MODELS_SORT | MODE=DATE/NAME/NAME_CASE/SIZE |
| Full platform preheating | M300_FULL_PLATFORM_PREHEAT | STATE=ENABLED/DISABLED |
| OLED dim time / OLED sleep time | M300_OLED_TIMERS | DIM=1..60, SLEEP=1..60 |
| OLED brightness | M300_OLED_BRIGHTNESS | LEVEL=1…16 |
| LED brightness | M300_LED_BRIGHTNESS | LEVEL=1…16 |

Bez parametru makro otwiera aktualny wybór bez zmiany ustawienia. Przykład:

```gcode
M300_OLED_BRIGHTNESS
M300_LED_BRIGHTNESS LEVEL=8
```

LEVEL jest liczbą całkowitą 1–16. Wartości 0, 17, ułamki i nieprawidłowy tekst
są odrzucane przez wspólnego właściciela ustawień, bez zaokrąglania. Zapis
nadal trafia do istniejącego m300_nvm. Synchronizacja otwartego regulatora OLED
z przeglądarką i zapamiętywanie ustawień nie zostały zastąpione nową obsługą.
M300_SCREEN pozostaje odczytem statusu wyświetlacza, nie regulatorem jasności.

## Ruch, serwis i druk

| Funkcja OLED | Wejście Fluidd / konsola | Wspólna realizacja |
|---|---|---|
| Home X/Y/Z/XY/XYZ | M300_HOME_X/Y/Z/XY/ALL | ZORTRAX_PROCEDURE_START i natywne bazowanie |
| Autocalibration | M300_LEVEL | M07, potwierdzenia aktualnej fazy |
| Bed mesh | BED_MESH | m300_pad_mesh, 25 pozycji kontaktowych |
| Heat extruder / platform | M300_HEAT / M300_HEAT_PLATFORM | dotychczasowa procedura grzania i potwierdzenia |
| Load / Unload / Change | M300_LOAD / UNLOAD / CHANGE | wspólna obsługa materiału; wznowienie osobno |
| Move platform up/down | M300_PLATFORM_UP/DOWN | natywny ruch Z i kontrola zakresu; przytrzymanie na OLED, krok we Fluidd |
| Fan test | M300_FAN_TEST_START / UPPER / LOWER / END | OEM-owa kontrola wentylatorów; chłodzenie ochronne ma pierwszeństwo |
| Current procedure | M300_PROCEDURE | ponowne otwarcie istniejącej sesji bez uruchamiania nowej |
| Pause / Resume / Cancel | PAUSE / RESUME / CANCEL_PRINT | m300_print_control; warunki wydruku i pozycja nadal sprawdzane |
| PID calibration | PID_HOTEND / PID_BED / PID_SAVE | natywny PID; zapis i restart wyłącznie na postoju |
| Information / Help | M300_INFORMATION / M300_HELP | wspólne dane wersji, drukarki i błędów |

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
instalowane jako przyciski na drukarce. M300_DIAGNOSTICS zapewnia wygodny
odczyt stanu bez ruchu i grzania. Test wentylatorów pozostaje, bo jest rzeczywistą
funkcją serwisową OEM, a nie testem rozwoju portu.

## Wersje i aktualizacja

Wersja hosta to **1.0.0-rc.34**, a sparowanego MCU **1.0.8**. Information pokazuje krótki numer hosta i
numeryczny numer MCU. Pełny rzeczywisty identyfikator firmware i znaczniki
zgodności transportu pozostają w diagnostyce; nie udajemy, że MCU otrzymało
nowe oprogramowanie. Pakiet używa nazw M300_HOST, M300_FLUIDD.zip i M300_SD.zip.

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Tylko bezczynna drukarka Ready, bez pauzy. Instalator zachowuje już wprowadzone
Z=-0,5 / M07 5–6,5–1 / odsunięcie styku 2 mm, siatkę m300_pads, PID i UART.
Parametr --qualified-first-print-z nadal służy do jawnego wdrożenia tego wariantu
na zakwalifikowanym egzemplarzu; RC1 nie stosuje go automatycznie do innych drukarek.
Strzałka na górnym pasku Fluidd przeładowuje stronę również w OrcaSlicerze. RC to kandydat do wydania, nie potwierdzenie
ukończenia całej listy prób sprzętowych. Dotychczasowe 65 ilustracji beta.20
pozostaje opisanym materiałem historycznym; bieżące różnice określa ten rozdział.
