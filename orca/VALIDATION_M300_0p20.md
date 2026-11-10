# Audyt OrcaSlicer M300 Classic 0,20 mm (2026-11-10)

## Rezultat
- **PASS statyczny**: oryginalny pakiet `.orca_printer` Inventure odczytany z repo; przygotowany jeden M300 i **jeden proces 0,20 mm**.
- **PASS**: 21 plików ZIP: 1 printer, 1 process, 18 filaments, 1 bundle_structure.json; CRC32 każdego wpisu zweryfikowany.
- **PASS**: parytet kluczy i typów JSON z Inventure: **144/144 pól drukarki**, **334/334 pól procesu**, **123/123 pól dla każdego z 18 materiałów**, razem 2692 sprawdzonych pozycji. Z-PEEK wzorowano na pełnym schemacie Z-NYLON (brak Z-PEEK wśród 17 profili OEM Inventure).
- **PASS**: wszystkie materiały mają zgodność wyłącznie z `Zortrax M300 0.4 nozzle`; sufiks `@Zortrax M300` uniemożliwia pomylenie z Inventure.
- **PASS**: wszystkie przyspieszenia procesu ≤ **700 mm/s²** (`max_accel` hosta); maksymalne XYZ i E według `m300_classic_base.cfg`.
- **PASS**: wszystkie 17 roboczych materiałów mają temperatury głowicy ≤265°C i stołu ≤105°C (fabryczna specyfikacja M300); `Z-PEEK` ma flagę błędu/niedostępności.
- **PASS**: profil to `gcode_flavor=klipper`, relatywne E, `START_PRINT EXTRUDER_TEMP=... BED_TEMP=... MESH=AUTO` / `END_PRINT`, brak skryptów Z-Code i lokalnych ścieżek konwertera.
- **NOT VERIFIED**: import i slicowanie w Orca GUI oraz rzeczywisty druk na M300. To nie jest dowód gotowości termicznej i ruchowej. Bazowy projekt `m300_classic_services.cfg` ma `workflow_qualified: False`.

## Parametry procesu 0,20 mm
| Funkcja | Prędkość [mm/s] | Przyspieszenie [mm/s²] |
|---|---:|---:|
| Pierwsza warstwa | 20 (infill 25) | 300 |
| Obrys zewnętrzny | 25 | 400 |
| Obrys wewnętrzny | 40 | 600 |
| Wypełnienie rzadkie | 50 | 700 |
| Wypełnienie pełne | 40 | 600 |
| Górna powierzchnia | 30 | 400 |
| Mosty | 20 | 300 |
| Ruch jałowy XY | 120 | 700 |
| Domyślne | — | 600 |

**Uwaga metodologiczna**: podane przyspieszenia są roboczym ustawieniem Orca ograniczonym do parametrów Klippera; audyty Inventure/Z-SUITE nie zawierały zweryfikowanej tabeli przyspieszeń M300 OEM. Jeden profil procesu nie może jednocześnie odwzorowywać różnych prędkości obrysów/wypełnienia Z-SUITE dla wszystkich filamentów; indywidualnie w filamentach uwzględniono temperaturę, chłodzenie, retrakcję (gdzie dane istnieją), ograniczenie volumetric flow (≤8 mm³/s, lub niższe), ale to wymaga testu przepływu.

## Katalog materiałów
| Kod Z-Code katalogu Inventure | Nazwa | Nozzle [°C] | Bed 1st [°C] | Max flow [mm³/s] | Zastosowanie na M300 Classic |
|---|---|---:|---:|---:|---|
| 0x01 | Z-ULTRAT | 260 | 105 | 8 | Zortrax M300 official |
| 0x02 | Z-GLASS | 245 | 85 | 8 | Zortrax M300 official |
| 0x03 | Z-HIPS | 235 | 95 | 8 | Zortrax M300 official |
| 0x04 | Z-PCABS | 265 | 105 | 8 | EKSPERYMENTALNY: brak na liscie M300 Classic |
| 0x05 | Z-PETG | 240 | 85 | 8 | Zortrax M300 official |
| 0x06 | Z-ULTRAT Plus | 250 | 80 | 8 | EKSPERYMENTALNY: brak na liscie M300 Classic |
| 0x07 | Z-SUPPORT | 240 | 50 | 8 | BLOKADA: material podpory dual |
| 0x08 | Z-ESD | 245 | 85 | 8 | Zortrax M300 official |
| 0x09 | Z-PHA | 205 | 60 | 8 | EKSPERYMENTALNY: brak na liscie M300 Classic |
| 0x0A | Z-PLA | 220 | 55 | 8 | EKSPERYMENTALNY: brak na liscie M300 Classic |
| 0x0B | Z-PLA Pro | 215 | 65 | 8 | Zortrax M300 official |
| 0x0C | Z-ASA Pro | 255 | 105 | 8 | Zortrax M300 official |
| 0x0D | Z-SUPPORT Plus | 245 | 80 | 4 | BLOKADA: material podpory dual |
| 0x0E | Z-SEMIFLEX | 235 | 60 | 2 | EKSPERYMENTALNY: brak na liscie M300 Classic |
| 0x0F | Z-FLEX | 225 | 65 | 4 | EKSPERYMENTALNY: brak na liscie M300 Classic |
| 0x10 | Z-NYLON | 260 | 95 | 8 | EKSPERYMENTALNY: brak na liscie M300 Classic |
| 0x11 | Z-SUPPORT Premium | 255 | 95 | 8 | BLOKADA: material podpory dual |
| 0x12 | Z-PEEK | 380 | 0 | 1 | BLOKADA: 380C poza limitem hotendu |

Kody Z-Code identyfikują materiały w **projekcie Inventure** i **nie są automatycznie kodami obsługiwanymi przez firmware M300**. Importowany G-code do Klippera nie używa tych kodów do wyboru materiału.

## Różnice względem presetów Inventure
1. Usunięto Windows `post_process` konwertujący do Z-Code i ścieżkę obrazka stołu; zmieniono `gcode_flavor=marlin` na `klipper`.
2. Wszystkie 144/334/123 pola pozostały obecne, ale ustawienia rzeczywistej komory grzewczej, filtracji i power-loss recovery wyłączono (M300 Classic nie ma tych funkcji).
3. Wszelkie prędkości w G-code to mm/s; `retraction_speed_mm_min_or_zsuite_setting` w źródle nie ma potwierdzonej jednostki — nie przepisano wartości 73/80 jako mm/s. Zastosowano nominalne 35 mm/s i dodatkowe ograniczenia dla FLEX.
4. Skorygowano niespójności w źródle: Z-PCABS 270→265°C, 115→105°C stołu; Z-ULTRAT Plus temperatura następnych warstw 235→250°C; Z-SUPPORT 220→240°C, Z-SUPPORT Plus 220→245°C; typ Z-NYLON ABS→PA.
5. Materiały Z-SUPPORT (3) katalogowo obecne i widoczne dla jednej głowicy, lecz nie da się używać odrębnych, rozpuszczalnych podpór równocześnie z filamentem modelowym; Z-PEEK (380°C) z maską `filament_printable=0` oznaczony jako niekompatybilny z `max_temp=270`. Pozostałe profile spoza siedmiu materiałów firmowo wymienionych dla M300 Classic są **eksperymentalne**.
6. M300 ma obszar **300×300×300**, a 305 mm pozycji Y jest strefą parkowania, nie dodatkowym obszarem druku. Limit `max_velocity=300`, `max_accel=700`, Z max 25/50, SCV=2 pochodzą z bieżącej konfiguracji portu Klippera, nie z fabrycznego pliku Z-SUITE.
7. Fabryczna specyfikacja M300 mówi o hotend max 290°C i stole max 105°C, podczas gdy aktualny Klipper ma odpowiednio 270°C i 120°C; przyjęto ostrożniejsze limity operacyjne 265°C i 105°C.

## Przyjęcie instalacji
W Orca: **File > Import > Import Configs** → plik `.orca_printer` → wybierz `Zortrax M300 0.4 nozzle` i `0.20mm Standard @Zortrax M300 0.4 nozzle`. Sprawdź 18 materiałów oznaczonych `@Zortrax M300`. Przetnij testowy model dla Z-PLA Pro, obejrzyj G-code pod kątem `START_PRINT`/`END_PRINT`, braku wywołania konwertera i braku prędkości/temperatur poza limitami. Na fizycznej drukarce kwalifikuj homing, ruch, grzanie, wentylatory, purge, bed-mesh, raft i wydruk dopiero po sprawdzeniu stanu Ready i jego zabezpieczeń. **Nie drukuj Z-PEEK. Materiałów Z-SUPPORT nie można użyć jako oddzielnego materiału podporowego równolegle z innym filamentem na jednogłowicowym M300.**

## Materiały źródłowe
- `MarcinKowalik-AGH/Zortrax-Inventure-OrcaSlicer-integration`: `presets/Zortrax Inventure 0.4 nozzle - single.orca_printer`, `docs/ZCODE_HEADER_AND_MATERIALS.md`, `docs/analysis_databases/speed_accel_material_database_v2026-05-03.json`.
- `MarcinKowalik-AGH/Zortrax-m300-Klipper`: `host/config/m300_classic_base.cfg`, `host/config/m300_classic_services.cfg`, `host/config/m300_operations.cfg`.
- Audyt `ZORTRAX_M300_STOCK_1.3.1_PELNA_INWENTARYZACJA_I_BRAKI_2026-10-18` na Google Drive.
- Specyfikacja fabryczna: https://store.zortrax.com/sale/zortrax-outlet-m300classic1
- Import w Orca: https://github.com/OrcaSlicer/OrcaSlicer/wiki/import_export

## Poprawka kompatybilności pól OrcaSlicer
Pole `filament_printable` to **maska bitowa ekstruderów**, nie poziom ostrzeżenia: `1` umożliwia użycie na pierwszym (jedynym) ekstruderze M300, `3` w Inventure dopuszcza oba ekstrudery, `0` zabrania użycia Z-PEEK. Dla 17 materiałów ustawiono `1`, dla Z-PEEK `0`. Pole `enable_power_loss_recovery` jest enumem tekstowym i ustawiono prawidłowe `disable` zamiast niepoprawnego `0`. Poprawka z audytu schematu OrcaSlicer wykonana bez zmian liczby i typów pól.
