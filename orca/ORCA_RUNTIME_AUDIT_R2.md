# M300 Classic — rzeczywisty test OrcaSlicer 2.3.2, R2

## Wynik i zakres

Uruchomiono oficjalny **OrcaSlicer 2.3.2 dla Linux x86_64** i pocięto model dwóch oddzielnych wież 6×6×5 mm, wymuszający przejazdy i retrakcje. **17 profili: PASS generowania i kontroli G-code; 0 błędów w tych 17 profilach. Z-PEEK: wyłącznie katalog, NIE do drukowania.** To nie jest potwierdzenie zgodności fizycznej wszystkich 17 materiałów z M300 ani dokładnego odtworzenia fabrycznych nastaw Z-SUITE.

Dowód pierwszego pełnego przebiegu R2: https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/actions/runs/42923571153

- SHA-256 sprawdzonego AppImage: `c64336ceec37d941766e675cbaaaf5124e184402bf18177fbf81ba5102734ad8`.
- SHA-256 wejściowego starego pakietu: `b696611f54e3805a35304b78a781d7392bb4f170dd4722e251af1cb4b28ce32f`.
- SHA-256 poprawionego pakietu R2: `e1e0407a3ff23c8a2d82ba9db7a7122a65df7ac6ec400473601024e402c57363`.
- GUI import na komputerze użytkownika: **nie wykonano**. Fizyczny wydruk: **nie wykonano**.
- CLI wymagało dwóch technicznych zmian metadanych wyłącznie w kopiach testowych: `type` z manifestu oraz `from=system` dla samodzielnych, pełnych presetów. Orca 2.3.2 CLI porównuje pustego rodzica `inherits` profilu User zamiast nazwy samodzielnej drukarki. Żadnych nastaw slicera ani list kompatybilności nie zmieniano w tym adapterze. Sam pakiet pozostaje pakietem User, takim jak Inventure.

## Wykryte problemy i poprawki

**1. Temperatura stołu wynosiła 0°C w wygenerowanym starcie.** Przy pustym `default_bed_type` CLI wybierało `Cool Plate`, którego pola temperatur były zerowe. Poprzednia walidacja samych kluczy tego nie wykryła. M300 ma tu jedną fizyczną płytę: ustawiono domyślny `High Temp Plate`, a wszystkie sloty temperatur płyt przypisano do dotychczasowych temperatur `hot_plate_temp` konkretnego filamentu. Nie zmieniono nominalnych temperatur materiałów. Teraz także domyślny wybór Cool Plate generuje właściwą temperaturę. Normalne temperatury po pierwszej warstwie sprawdzono w poleceniach `M140`.

**2. Stare `ACCEL_TO_DECEL`.** Inventure miało włączone `accel_to_decel_enable`. Orca emitowała usunięty z nowego Klippera parametr. Wyłączono tylko tę opcję. Wartości przyspieszeń pozostały 300–700 mm/s²; nie zmieniono SCV, minimum_cruise_ratio ani limitów firmware. Źródło: https://www.klipper3d.org/Config_Changes.html (2025-08-11).

**3. Z-PEEK nie jest blokowany przez samą maskę.** Test wykazał, że `filament_printable=0` nie powstrzymuje CLI 2.3.2 przed wygenerowaniem `START_PRINT EXTRUDER_TEMP=380`. Wcześniejsze stwierdzenie o pewnej blokadzie przez Orca było nieprawidłowe. PEEK pozostaje opisany jako niedopuszczony do druku. Bieżący kod M300 `cmd_start` sprawdza limit hotendu 270°C przed rozpoczęciem grzania i ruchu, ale nie wykonano tego testu na sprzęcie. Nie należy wysyłać takiego G-code do drukarki ani podnosić limitów.

**4. SEMIFLEX ma prawidłową retrakcję.** Początkowy parser testu nie rozpoznawał poprawnego zapisu `E-.2`. Poprawiono parser liczb, nie profil filamentu. Rzeczywista retrakcja wynosi 0,2 mm przy 10 mm/s.

## Start, koniec i pauza

W pakiecie pozostaje:

```gcode
G90
M83
START_PRINT EXTRUDER_TEMP={first_layer_temperature[0]} BED_TEMP=[bed_temperature_initial_layer_single] MESH=AUTO
```

Dla Z-PLA Pro rzeczywisty wynik to:

```gcode
G90
M83
START_PRINT EXTRUDER_TEMP=215 BED_TEMP=65 MESH=AUTO
```

Na dalszej warstwie jest `M140 S60`. Koniec: `END_PRINT`. Pole pauzy: `PAUSE`. Nie ma dodatkowego G28, oczekiwania M109/M190 ani osobnej linii purge przed START_PRINT w G-code slicera.

Makro w `host/config/m300_operations.cfg` przekazuje parametry do `ZORTRAX_PRINT_START`. Kod `m300_print_control.py` wykonuje grzanie i oczekiwanie, homing, załadowanie istniejącego `m300_pads` (AUTO bez zapisanego meshu przechodzi na NONE), cztery linie purge i kontynuację pliku. AUTO nie mierzy nowej siatki. `END_PRINT` obsługuje opróżnienie kolejki ruchów, własną retrakcję, parkowanie i wyłączenie grzałek/wentylatora modelu. Nie dopisano duplikatów tych procedur w Orca.

Menu OLED/Fluidd oraz definicje makr należą do hosta. Import presetu Orca dodaje wywołania G-code, a nie menu lub nowe makra do `printer.cfg`.

## Ekstruzja i retrakcja — dane z wygenerowanego G-code

M83, dysza 0,4 mm, filament 1,75 mm, `use_firmware_retraction=0`, bez G10/G11. Dodatkowe podanie po retrakcji wynosi 0. Z-hop 0,4 mm. Dla każdego badanego materiału wystąpiło **109 retrakcji, 108 powrotów filamentu i 108 sprawdzonych podniesień Z**; jedna końcowa retrakcja pozostaje nieodwrócona po ukończeniu modelu. Mnożniki przepływu pozostawiono bez zmian. Pressure Advance w profilu pozostaje wyłączone; zapisana liczba 0,02 nie stanowi aktywnej kalibracji.

| Materiał | Retrakcja mm | Cofanie mm/s | Powrót mm/s | Flow ratio | MVS mm³/s | Start dysza/stół °C |
|---|---:|---:|---:|---:|---:|---|
| Z-ASA Pro | 1 | 35 | 35 | 0,95 | 8 | 255/105 |
| Z-ESD | 1,8 | 35 | 35 | 0,97 | 8 | 245/85 |
| Z-FLEX | 2,5 | 25 | 35 | 1 | 4 | 225/65 |
| Z-GLASS | 1 | 35 | 35 | 0,97 | 8 | 245/85 |
| Z-HIPS | 1 | 35 | 35 | 0,95 | 8 | 235/95 |
| Z-NYLON | 2 | 35 | 35 | 0,95 | 8 | 260/95 |
| Z-PCABS | 1 | 35 | 35 | 0,94 | 8 | 265/105 |
| Z-PETG | 2 | 35 | 35 | 0,97 | 8 | 240/85 |
| Z-PHA | 1 | 35 | 35 | 0,98 | 8 | 205/60 |
| Z-PLA Pro | 1,5 | 35 | 35 | 0,98 | 8 | 215/65 |
| Z-PLA | 1 | 35 | 35 | 0,98 | 8 | 225/55 |
| Z-SEMIFLEX | 0,2 | 10 | 10 | 1 | 2 | 235/60 |
| Z-SUPPORT Plus | 1 | 35 | 35 | 0,95 | 4 | 245/80 |
| Z-SUPPORT Premium | 1 | 35 | 35 | 0,95 | 8 | 255/95 |
| Z-SUPPORT | 1 | 35 | 35 | 0,95 | 8 | 240/50 |
| Z-ULTRAT Plus | 1 | 35 | 35 | 0,926 | 8 | 255/80 |
| Z-ULTRAT | 1 | 35 | 35 | 0,926 | 8 | 260/105 |

Przykłady: `G1 E-1.5 F2100` i `G1 E1.5 F2100` dla PLA Pro; `G1 E-.2 F600` dla SEMIFLEX. F jest w mm/min, zatem 2100/60 = 35 mm/s.

`nil` w opcjach filamentu oznacza dziedziczenie opcji drukarki. Nie zastąpiono poprawnego dziedziczenia przypadkowymi wartościami. Retrakcja PAUSE/END hosta (domyślnie 2 mm przy 2 mm/s) jest inną operacją niż retrakcja przejazdów z Orca.

## Co oznacza PASS

PASS dotyczy wczytania ustawień przez silnik Orca 2.3.2, rozwinięcia startu i końca, temperatur stołu, dodatniej ekstruzji, liczbowej zgodności retrakcji/powrotu/Z-hop, załadowania flow ratio i średnic oraz braku starego ACCEL_TO_DECEL i niechcianych M201/M203/M205/G10/G11/M82. Nie oznacza fizycznie skalibrowanego przepływu, retrakcji, jakości, przyczepności raftu ani homologacji wszystkich materiałów. Z-SUPPORT nie daje osobnych rozpuszczalnych podpór równolegle z materiałem modelu w jednogłowicowym M300.

R2 zachowuje wszystkie 144/334/123 klucze Inventure. Nie zmieniono firmware, drukarki ani ustawień na Orange Pi. Ten raport zastępuje sprzeczne wnioski wcześniejszego `VALIDATION_M300_0p20.md` w opisanych wyżej punktach.
