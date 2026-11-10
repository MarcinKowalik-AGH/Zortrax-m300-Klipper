# Katalog makr, procedur i komend diagnostycznych

[Spis dokumentacji](../../README_PL.md) · [Obsługa](USER_GUIDE.md) · [Menu OLED](OLED_MENU_REFERENCE.md) · [Parametry](TECHNICAL_REFERENCE.md)

> Dokumentacja dla **M300 Classic**, stan kodu **v1.0.0-beta.17**, commit `d6ddf9c3bee58dc2209946a0073f8a708d964073`. Nie dotyczy M300 Plus, M300 Dual ani Inventure.


## 1. Co obejmuje katalog

Poniżej są **wszystkie 39 sekcji `[gcode_macro ...]`** z siedmiu plików `host/config` w beta.17. Liczba przycisków we Fluidd może być inna: zależy od włączonych plików, ukrytych makr, ustawień użytkownika i komend rejestrowanych bezpośrednio przez moduły. Nazwa grupy w interfejsie nie stanowi zabezpieczenia; opis procedury i jej kontroler określają skutki.

W szczególności PAUSE/RESUME oraz część statusów nie muszą mieć osobnej sekcji gcode_macro. Końcowa obsługa CANCEL_PRINT jest wiązana przez `m300_print_control`, dlatego samo odczytanie krótkiego makra bazowego nie wyjaśnia całego parkowania i zamknięcia pliku.

## 2. Makra dostarczane w konfiguracji

| Makro | Grupa funkcjonalna | Działanie | Parametry / uwagi |
|---|---|---|---|
| [`START_PRINT`](../../host/config/m300_operations.cfg) | Druk | Przygotowanie druku: grzanie, natywne bazowanie, profil mesh, 2Y + 2X linii startowych. | EXTRUDER_TEMP i BED_TEMP: cele aktualne, gdy pominięte; MESH=AUTO; PURGE opcjonalny (domyślnie 250 mm w module). |
| [`END_PRINT`](../../host/config/m300_operations.cfg) | Druk | Zakończenie: drenaż ruchów, parkowanie, wyłączenie celów grzałek i wentylatora modelu. | Bez parametrów makra. |
| [`CANCEL_PRINT`](../../host/config/m300_operations.cfg) | Druk | Publiczne anulowanie; moduł m300_print_control wiąże finalną obsługę, zamyka plik i czyści pauzę przed ewentualnym parkowaniem. | Bez parametrów; nie utożsamiać z M112 ani samym ciałem makra bazowego. |
| [`ZORTRAX_REPRINT`](../../host/config/m300_operations.cfg) | Druk | Potwierdzenie usunięcia modelu i ponowny wydruk zapamiętanego zakończonego zadania. | Wymaga prawidłowego zakończonego zadania. |
| [`ZORTRAX_STATUS`](../../host/config/m300_operations.cfg) | Diagnostyka | Odczyt stanu MCU, łącza i ruchu. | Bez ruchu/grzania. |
| [`ZORTRAX_FANS`](../../host/config/m300_operations.cfg) | Diagnostyka | Odczyt sterowania wentylatorami i niezależnej polityki chłodzenia MCU. | Bez uruchamiania testu. |
| [`ZORTRAX_LIGHT`](../../host/config/m300_operations.cfg) | Ustawienia | Wspólne ustawienie światła. | MODE: DYNAMIC, WHITE, DISABLE; pominięcie otwiera wybór. |
| [`ZORTRAX_SCREEN`](../../host/config/m300_operations.cfg) | Diagnostyka | Odczyt stanu bezczynności, jasności i wybudzenia wyświetlacza. | Bez parametrów. |
| [`ZORTRAX_LEVEL`](../../host/config/m300_operations.cfg) | Poziomowanie | Autokalibracja śrub M07 przez wspólne kroki OLED/Fluidd. | TEMP=260; nie jest mesh. |
| [`BED_MESH`](../../host/config/m300_operations.cfg) | Poziomowanie | Pomiar 25 pozycji kontaktowych i utworzenie profilu; PREVIEW=1 tylko podgląd. | PROFILE, PREVIEW, HOTEND_TEMP, BED_TEMP i parametry geometrii wymienione poniżej. |
| [`ZORTRAX_HEAT`](../../host/config/m300_operations.cfg) | Termika | Procedura OEM grzania hotendu z potwierdzeniem końca. | TEMP=260. |
| [`ZORTRAX_HEAT_PLATFORM`](../../host/config/m300_operations.cfg) | Termika | Procedura grzania stołu z widocznym postępem i potwierdzeniem wyłączenia. | TEMP=60. |
| [`ZORTRAX_FULL_PLATFORM_PREHEAT`](../../host/config/m300_operations.cfg) | Ustawienia | Włącza dodatkową stabilizację platformy przed startem druku; samo nie grzeje. | STATE opcjonalny; pominięcie otwiera wybór. |
| [`ZORTRAX_HOME_X`](../../host/config/m300_operations.cfg) | Ruch | Bazowanie wyłącznie X wspólną procedurą. | Bez parametrów. |
| [`ZORTRAX_HOME_Y`](../../host/config/m300_operations.cfg) | Ruch | Bazowanie wyłącznie Y wspólną procedurą. | Bez parametrów. |
| [`ZORTRAX_HOME_XY`](../../host/config/m300_operations.cfg) | Ruch | Bazowanie XY z właściwym przygotowaniem M300. | Bez parametrów. |
| [`ZORTRAX_HOME_Z`](../../host/config/m300_operations.cfg) | Ruch | Kontaktowe bazowanie Z po ustaleniu XY i przygotowaniu termicznym. | Bez parametrów. |
| [`ZORTRAX_HOME_ALL`](../../host/config/m300_operations.cfg) | Ruch | Pełne bazowanie XYZ, w tym wspólne zabezpieczenie odstępu Z. | Bez parametrów. |
| [`ZORTRAX_PLATFORM_UP`](../../host/config/m300_operations.cfg) | Ruch | Przesunięcie platformy w stronę dyszy, wymaga poprawnego Z. | DISTANCE=1 mm, SPEED opcjonalny. |
| [`ZORTRAX_PLATFORM_DOWN`](../../host/config/m300_operations.cfg) | Ruch | Oddalenie platformy od dyszy. | DISTANCE=1 mm, SPEED opcjonalny. |
| [`ZORTRAX_LOAD`](../../host/config/m300_operations.cfg) | Materiał | Prowadzone ładowanie materiału. | TEMP=240; nie uruchamiać w trwającym wydruku. |
| [`ZORTRAX_UNLOAD`](../../host/config/m300_operations.cfg) | Materiał | Prowadzone wyładowanie materiału. | TEMP=240. |
| [`ZORTRAX_CHANGE`](../../host/config/m300_operations.cfg) | Materiał | Wymiana materiału w chronionej pauzie; nie wznawia samoczynnie pliku. | TEMP opcjonalny; wymaga kontekstu zmiany materiału. |
| [`ZORTRAX_FAN_TEST_START`](../../host/config/m300_operations.cfg) | Wentylatory | Rozpoczyna wspólny interaktywny test wentylatorów. | Nie znosi automatycznego chłodzenia hotendu. |
| [`ZORTRAX_FAN_UPPER`](../../host/config/m300_operations.cfg) | Wentylatory | Przełącza żądanie górnego wentylatora w procedurze testu. | Żądanie OEM 0 / 150 z 255; niezależna ochrona ma pierwszeństwo. |
| [`ZORTRAX_FAN_LOWER`](../../host/config/m300_operations.cfg) | Wentylatory | Przełącza żądanie dolnego wentylatora w procedurze testu. | Żądanie OEM 0 / 150 z 255. |
| [`ZORTRAX_FAN_TEST_END`](../../host/config/m300_operations.cfg) | Wentylatory | Zamyka test i przywraca właściwą politykę. | Bez parametrów. |
| [`ZORTRAX_SETTINGS`](../../host/config/m300_operations.cfg) | Ustawienia | Otwiera wspólne Settings. | Bez parametrów. |
| [`ZORTRAX_BUZZER`](../../host/config/m300_operations.cfg) | Ustawienia | Włącza/wyłącza istniejący buzzer. | STATE opcjonalny. |
| [`ZORTRAX_SLEEP_MODE`](../../host/config/m300_operations.cfg) | Ustawienia | Włącza/wyłącza istniejące usypianie; zachowuje czas z konfiguracji. | STATE opcjonalny. |
| [`ZORTRAX_LANGUAGE`](../../host/config/m300_operations.cfg) | Ustawienia | Otwiera wybór języka; obsługiwany jest tylko English. | Nie oferuje tłumaczeń nieobecnych w kodzie. |
| [`ZORTRAX_MODELS_SORT`](../../host/config/m300_operations.cfg) | Ustawienia | Ustawia sortowanie plików. | MODE: DATE, NAME, NAME_CASE, SIZE. |
| [`ZORTRAX_INFORMATION`](../../host/config/m300_operations.cfg) | Informacje | Otwiera Information, opcjonalnie odświeża historię Moonrakera. | REFRESH=1. |
| [`ZORTRAX_HELP`](../../host/config/m300_operations.cfg) | Informacje | Pokazuje pomoc projektu i odnośniki. | Bez parametrów. |
| [`PID_HOTEND`](../../host/config/klipper_calibration.cfg) | PID | Natywna kalibracja PID hotendu, zapis osobno. | TARGET=200. |
| [`PID_BED`](../../host/config/klipper_calibration.cfg) | PID | Natywna kalibracja PID stołu, zapis osobno. | TARGET=60. |
| [`PID_SAVE`](../../host/config/klipper_calibration.cfg) | PID | SAVE_CONFIG — zapis uzyskanej kalibracji i restart Klippera. | Wyłącznie bezczynna drukarka. |
| [`TEST_ZORTRAX_STATUS`](../../host/config/m300_tests.cfg) | Testy | Odczytuje konfigurację, sprzęt, OLED i wentylatory. | Odczyt bez ruchu/grzania. |
| [`TEST_ZORTRAX_XY`](../../host/config/m300_tests.cfg) | Testy | Testowe przejazdy XY; nie jest testem przepływu ani zwykłym bazowaniem. | SPEED=50 mm/s (maks. 60), LOOPS=1 (zakres 1…10); wymaga bezpiecznych warunków. |


## 3. Parametry makra BED_MESH

Makro przekazuje wyłącznie obsługiwane argumenty do procedury pomiaru. Parametry opisuje [rozdział mesh](BED_MESH_AND_LEVELING.md), a dokładne bieżące wartości są w konfiguracji konkretnej drukarki.

```text
PROFILE PREVIEW CORNER_PAD_WIDTH CENTER_PAD_WIDTH EDGE_MARGIN
FRONT_RIGHT_X FRONT_RIGHT_Y FRONT_LEFT_X FRONT_LEFT_Y CENTER_X CENTER_Y
REAR_RIGHT_X REAR_RIGHT_Y REAR_LEFT_X REAR_LEFT_Y
FIT_TRAVEL TRAVEL_MARGIN HOTEND_TEMP BED_TEMP
FRONT_RIGHT_BOUNDS FRONT_LEFT_BOUNDS CENTER_BOUNDS REAR_RIGHT_BOUNDS REAR_LEFT_BOUNDS
```

Bezpieczna kontrola geometrii bez ruchu: `BED_MESH PREVIEW=1`. Nie publikujemy przykładu z parametrami konkretnej płyty jako uniwersalnego zamiennika istniejącej kalibracji.

## 4. Komendy spoza powyższych sekcji makr

| Komenda | Rola |
|---|---|
| `PAUSE`, `RESUME` | Wspólne sterowanie pauzą i wznowieniem przez kontroler druku |
| `PRINT_CONTROL_STATUS` | Stan START/PAUSE/CANCEL i wersja kontrolera |
| `ZORTRAX_PRINT_START`, `ZORTRAX_PRINT_END` | Wejścia kontrolera wywoływane przez makra START/END |
| `ZORTRAX_MCU_STATUS` | MCU, model, gotowość i zabezpieczenia |
| `ZORTRAX_LINK_STATUS` | UART i dopasowanie parametrów host/MCU |
| `ZORTRAX_MOTION_STATUS` | Natywny ruch i stan bazowania |
| `ZORTRAX_HARDWARE_STATUS`, `ZORTRAX_CONFIG_STATUS` | Odczyty konfiguracji i dostępnego sprzętu |
| `ZORTRAX_OLED_STATUS` | Transport i podgląd, w tym NAV-EVENT-1 oraz liczniki zdarzeń |
| `ZORTRAX_OLED_PERF` | Odczyt dostępnych statystyk wydajności OLED; nie jest zmianą zegara SPI |
| `ZORTRAX_DISPLAY_STATUS` | Bezczynność/wybudzenie/jasność warstwy wyświetlacza |
| `ZORTRAX_FANS_STATUS` | Żądania wentylatorów i stan polityki chłodzenia |
| `ZORTRAX_UI_SHOW`, `ZORTRAX_UI_SETTING` | Wspólne menu i ustawienia; zwykle wywoływane przez makra |
| `ZORTRAX_PROCEDURE` | Stan/okno procedury, gdy odpowiedni moduł jest włączony |
| `PID_STATUS` | Odczyt parametrów i stanu kalibracji PID |
| `BED_MESH_PROFILE`, `BED_MESH_OUTPUT`, `BED_MESH_CLEAR` | Wczytanie/profil, odczyt oraz wyłączenie aktywnej kompensacji |
| `SAVE_CONFIG` | Trwały zapis i restart, nie wykonywać podczas druku |
| `M112`, `FIRMWARE_RESTART` | Awaryjne zatrzymanie; restart po rozpoznaniu i usunięciu przyczyny |

Dostępność komend kontroluj przez `HELP` i właściwe moduły załadowanej konfiguracji. Nie wywołuj nieznanego polecenia tylko dlatego, że znajduje się na historycznym zrzucie. Polecenia `ZORTRAX_UI_ACTION ...` zawierają identyfikatory aktualnego widoku — nie przepisuj ich z cudzej sesji.

## 5. Grupy we Fluidd

Aktualny pełny zrzut w [instrukcji użytkownika](USER_GUIDE.md) pokazuje grupy ZORTRAX M300 i Klipper oraz podgląd OLED. Starszy zrzut z 08.11.2026 zawiera makra pozostające jeszcze w Uncategorized; jest zachowany jako dokument historyczny, nie lista oczekiwanego podziału beta.17. Rozwijany przycisk przy makrze służy do podania parametrów, a nie do ręcznego potwierdzania wszystkich kroków wewnętrznych.

## 6. Źródła

[Operacje](../../host/config/m300_operations.cfg) · [PID](../../host/config/klipper_calibration.cfg) · [Testy](../../host/config/m300_tests.cfg) · [Kontroler wydruku](../../host/klippy/extras/m300_print_control.py) · [Procedury UI](../../host/klippy/extras/m300_procedures.py).
