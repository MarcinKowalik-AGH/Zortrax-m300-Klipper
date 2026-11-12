# Menu OLED — struktura, funkcje i rendery z kodu

> **RC1:** bieżące makra i nawigację opisuje [spójność interfejsu RC1](RC1_UI.md). Menu główne ma tylko Klipper i Zortrax M300. Ekrany poniżej zachowano jako podpisany wzorzec beta.20; pozycja Service / Tests na starszych ilustracjach nie występuje w RC1.

[Spis dokumentacji](../../README_PL.md) · [Obsługa](USER_GUIDE.md) · [Menu OLED](OLED_MENU_REFERENCE.md) · [Ilustrowane funkcje](OLED_FUNCTIONS.md) · [Parametry](TECHNICAL_REFERENCE.md)

> Dokumentacja dla **M300 Classic**, stan kodu **v1.0.0-beta.20**, commit `4828a9da9d5fd8b0b93eb2ac267732ee7e49d506`. Nie dotyczy M300 Plus, M300 Dual ani Inventure.


**Instrukcja działania:** [65 ekranów z opisem funkcji, warunków, ikon i odpowiedników we Fluidd](OLED_FUNCTIONS.md). Ten dokument pozostaje pełnym spisem wierszy menu i zapisem renderowania, a nie tylko galerią obrazków.

## 1. Zasada zgodności

OLED w drukarce i jego podgląd w Fluidd korzystają z tego samego obrazu przygotowanego przez host. Nie jest to niezależna imitacja menu w przeglądarce. Nazwy interfejsu są **angielskie**, tak jak w kodzie tego portu. Polska jest niniejsza instrukcja; pozycja Language nie oznacza istnienia polskiego tłumaczenia ekranu.

Poniższe tabele pobrano programowo z rzeczywistych metod `rows()` modułów menu i ustawień na bezpiecznym stanie demonstracyjnym. Dane dynamiczne (temperatury, nazwa pliku, stan SD, druk) zależą od konfiguracji i bieżącej procedury. Pełny zapis wierszy, akcji i pochodzenia renderów: [OLED_RENDER_MANIFEST.json](../reports/OLED_RENDER_MANIFEST.json).

## 2. Nawigacja i bezpieczeństwo akcji

Obrót pokrętła zmienia zaznaczenie; krótki klik wybiera dostępną akcję. Back wraca z podmenu, a wybór w menu nadrzędnym jest pamiętany. Ruchy i grzanie nie są wykonywane przez sam podgląd Fluidd: obowiązują wspólne kontrolery, blokady zasobów i potwierdzenia bieżącego widoku. Przyciski okna procedury odnoszą się do konkretnego identyfikatora widoku; nie należy odtwarzać starych poleceń potwierdzenia z logu.

Dłuższe przytrzymanie ma znaczenie zależne od kontekstu. Podczas wydruku i na ekranie zakończenia istnieją akcje przytrzymania około 10 s (pauza / ponowny wydruk z potwierdzeniem usunięcia modelu). Ruch platformy przez przytrzymanie jest ograniczany i zatrzymywany po zwolnieniu. Nie traktuj długiego kliknięcia jako uniwersalnego skrótu Back na wszystkich ekranach.

## 3. Drzewo funkcjonalne

```text
Status Klippera ↔ Menu główne
├─ Klipper
│  ├─ Hotend TEMP / Bed TEMP, Heat hotend / Heat bed / Turn off heaters
│  ├─ Home X / Home Y / Home Z / Home XY / Home XYZ
│  ├─ Bed mesh (25 points)
│  ├─ Move axes → Move X / Move Y / Move Z → ±10 / ±1 / ±0.1 mm
│  ├─ Fans
│  ├─ PID calibration → hotend / bed / save
│  └─ Print status
├─ Zortrax M300
│  ├─ Models → SD card / Host files → lista → wybór / potwierdzenie
│  ├─ Maintenance → Autocalibration, Home X/Y/Z/XY/XYZ,
│  │                 Heat the extruder/platform, platform up/down, Fan test
│  ├─ Material → Unload the material / Load the material
│  ├─ Settings → Light, Buzzer, Sleep mode, Language, Models sorting,
│  │              Full platform preheating, OLED brightness, LED brightness
│  └─ Information → Firmware version / Printer information / Help → Errors
└─ Service / Tests → Diagnostics / procedury testowe / odczyty / ruchy XY

Kontekst druku: Printing → Pause menu → Resume / Change material / Stop
               Stop → No / Yes; Done → usuń model / ponowny wydruk
```

**Change material nie jest trzecią statyczną pozycją Material w tym wydaniu** — jest akcją kontekstową pauzy i dostępna przez `ZORTRAX_CHANGE`. Autocalibration nie jest tym samym co Bed mesh. Home Z wymaga odpowiedniego odniesienia XY i przygotowania styku; opis bez dopisku „180C” nie usuwa wymogu nagrzania.

## 4. Szczegółowe wiersze

Numeracja zaczyna się od 0 (Back). Wartości 200/60°C, HW05, 12 h 34 min i zastępczy numer seryjny w poniższych tabelach są wyłącznie danymi demonstracyjnymi. Nie są odczytem z Twojej drukarki. Długie listy zajmują wiele widoków, a długie napisy mogą być przewijane.

### Menu główne

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Klipper |
| 2 | Zortrax M300 |
| 3 | Service / Tests |

### Zortrax M300

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Models |
| 2 | Maintenance |
| 3 | Material |
| 4 | Settings |
| 5 | Information |

### Klipper

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Hotend TEMP: 200°C |
| 2 | Bed TEMP: 60°C |
| 3 | Heat hotend |
| 4 | Heat bed |
| 5 | Turn off heaters |
| 6 | Home X |
| 7 | Home Y |
| 8 | Home Z |
| 9 | Home XY |
| 10 | Home XYZ |
| 11 | Bed mesh (25 points) |
| 12 | Move axes |
| 13 | Fans |
| 14 | PID calibration |
| 15 | Print status |

### Maintenance

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Autocalibration |
| 2 | Home X |
| 3 | Home Y |
| 4 | Home Z |
| 5 | Home XY |
| 6 | Home XYZ |
| 7 | Heat the extruder |
| 8 | Heat the platform |
| 9 | Move the platform up |
| 10 | Move the platform down |
| 11 | Fan test |

### Material

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Unload the material |
| 2 | Load the material |

### Settings

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Light |
| 2 | Buzzer |
| 3 | Sleep mode |
| 4 | Language |
| 5 | Models sorting |
| 6 | Full platform preheating |
| 7 | OLED brightness |
| 8 | LED brightness |

### Light

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Dynamic |
| 2 | White |
| 3 | Disabled |

### Buzzer

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Enabled |
| 2 | Disabled |

### Sleep mode

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Enabled |
| 2 | Disabled |

### Language

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | English |

### Models sorting

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Date |
| 2 | Name |
| 3 | Case-sensitive name |
| 4 | File size |

### Full platform preheating

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Enabled |
| 2 | Disabled |

### Information

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Firmware version |
| 2 | Printer information |
| 3 | Help |

### Firmware version

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Host R16.12 |
| 2 | MCU 0.13.14.18 |
| 3 | Klipper ee2c6fb6b00b |
| 4 | OEM reference 1.3.1 |

### Printer information

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Model: Zortrax M300 Classic |
| 2 | Hardware version: HW05 |
| 3 | Serial number: DEMO-NOT-A-SERIAL |
| 4 | Total printing time: 12 h 34 min |

### Help

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Errors |
| 2 | github.com/ |
| 3 | MarcinKowalik-AGH/ |
| 4 | Zortrax-m300-Klipper |
| 5 | Project documentation and issues |

### Move axes

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Move X |
| 2 | Move Y |
| 3 | Move Z |

### Move X

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | X -10.0 mm |
| 2 | X -1.0 mm |
| 3 | X -0.1 mm |
| 4 | X +0.1 mm |
| 5 | X +1.0 mm |
| 6 | X +10.0 mm |

### Move Z

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Z -10.0 mm |
| 2 | Z -1.0 mm |
| 3 | Z -0.1 mm |
| 4 | Z +0.1 mm |
| 5 | Z +1.0 mm |
| 6 | Z +10.0 mm |

### PID calibration

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Hotend PID 200C |
| 2 | Bed PID 60C |
| 3 | Save calibration |

### Models

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | SD card |
| 2 | Host files |

### Bed mesh

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Ready to measure |
| 2 | Measure 25 pad points |
| 3 | 25 points / 75 contacts |

### Service / Tests

Kolejność | Pozycja na OLED
|---:|---|
| 0 | Back |
| 1 | Diagnostics |
| 2 | TEST: material procedures |
| 3 | TEST: platform calibration |
| 4 | TEST: calibration status |
| 5 | TEST: OEM print / SD |
| 6 | Current test procedure |
| 7 | Read test status |
| 8 | TEST XY 50 mm/s |
| 9 | TEST XY 60 mm/s |

## 5. Ustawienia i stany szczególne

Jasność OLED/LED ma 16 poziomów. W widoku regulacji pojawia się właściwy pasek jasności; nie należy używać go jako ogólnego paska postępu innych procedur. Buzzer można wyłączyć; nie zmienia to kontroli ruchu ani temperatury. Światło Dynamic jest powiązane ze stanem: Ready zielone, grzanie czerwone, pauza fioletowa, druk/aktywna praca białe; błędy mają odrębną sygnalizację. White i Disabled są ustawieniami preferencji, nie zniesieniem zabezpieczeń.

Sleep mode włącza istniejący mechanizm bezczynności. Bieżący czas wynika z konfiguracji display (domyślnie 300 s w tej warstwie), a historyczny identyfikator zapisu `15MIN` nie powinien być interpretowany jako potwierdzenie rzeczywistego timeoutu 15 minut. Na uśpieniu wyświetlany jest księżyc. Wybudzenie nie oznacza wydania polecenia grzania lub ruchu.

Full platform preheating włącza dodatkową stabilizację platformy przed drukiem; samo przełączenie ustawienia nie jest poleceniem natychmiastowego rozgrzania stołu. Menu Models zależy od dostępności i kwalifikacji SD; `sd_qualified: False` nie należy obchodzić przypadkowym ustawieniem bez testu. Puste miejsce listy lub komunikat „No models on SD card” nie jest awarią planera.

**Service / Tests nie jest całe odczytowe.** Odczyt diagnostyki nie porusza drukarką, ale test XY, materiał i kalibracja mogą wykonywać ruchy/grzanie. Zobacz [katalog komend](MACRO_REFERENCE.md) i warunki bezpieczeństwa każdej procedury.

## 6. Jak wykonano obrazy

Uruchomiono oryginalne funkcje rysowania `menu_frame`, `brightness_frame`, `notice_frame`, selektory symboli i bitmapową czcionkę projektu. Dla statusu użyto przypiętego silnika wyświetlacza Klippera, a dla M07 i pauzy odpowiednich rendererów produkcyjnych. Stan drukarki zastępują obiekty demonstracyjne; skrypt **nie tworzy połączenia z MCU i nie wykonuje G-code**.

Każdy ekran ma PNG **256×64** i podgląd **768×192**, powiększony metodą nearest-neighbour dokładnie 3×. To obrazy statyczne wybranych faz, nie pomiar synchroniczności ani pełne nagranie animacji. Ekran komunikatu braku modeli demonstruje istniejący prezenter komunikatów; nie jest fotografią chwilowego błędu na sprzęcie.

Odtwarzanie (ze sprawdzonego katalogu repozytorium, z Pythonem i zależnościami testów):

```bash
python ci/prepare_upstream.py
python docs/tools/render_oled_manual.py --klipper .ci/pristine
python docs/tools/check_manual.py
```

Zmiana kodu menu może świadomie zmienić rendery — wtedy trzeba ponownie przejrzeć obrazy i odnowić manifest, zamiast podmieniać je ręcznymi szkicami.

## 7. Galeria — 65 ekranów

Pełny opis każdej funkcji jest pod odnośnikiem przy ilustracji. Nie przepisuj przykładowych nastaw ani wskazań regulacji śrub.

### 1. Klipper — wejście do sterowania

![Klipper — wejście do sterowania](../img/oled/main_klipper@3x.png)

Otwiera zestaw funkcji natywnych: wybór temperatur, grzanie, bazowanie, mesh, ręczne ruchy, wentylatory, PID i status druku. Samo wejście nie rozpoczyna procedury.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#main_klipper) · [Natywne 256×64](../img/oled/main_klipper.png).

### 2. Zortrax M300 — menu funkcji OEM

![Zortrax M300 — menu funkcji OEM](../img/oled/main_zortrax@3x.png)

Otwiera Models, Maintenance, Material, Settings oraz Information. Jest to gałąź obsługi charakterystycznej dla M300, a nie przełączenie z powrotem na fabryczny firmware.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#main_zortrax) · [Natywne 256×64](../img/oled/main_zortrax.png).

### 3. Pięć grup menu Zortrax

![Pięć grup menu Zortrax](../img/oled/zortrax_menu@3x.png)

Models obsługuje pliki, Maintenance czynności przy platformie i głowicy, Material filament, Settings preferencje, Information dane drukarki i pomoc.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#zortrax_menu) · [Natywne 256×64](../img/oled/zortrax_menu.png).

### 4. Home X — bazowanie

![Home X — bazowanie](../img/oled/klipper_home@3x.png)

Wyznacza odniesienie osi X. Nie wykonuje celowo bazowania Y ani pomiaru mesh.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_home) · [Natywne 256×64](../img/oled/klipper_home.png).

### 5. Bed mesh — wejście do podmenu

![Bed mesh — wejście do podmenu](../img/oled/klipper_mesh@3x.png)

Otwiera ekran przygotowania i stanu mesh. Uruchomienie jest oddzielną pozycją Measure 25 pad points.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_mesh) · [Natywne 256×64](../img/oled/klipper_mesh.png).

### 6. PID calibration — wejście

![PID calibration — wejście](../img/oled/klipper_pid@3x.png)

Otwiera listę kalibracji PID. Samo otwarcie nie włącza grzałek.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_pid) · [Natywne 256×64](../img/oled/klipper_pid.png).

### 7. Autocalibration — mechaniczne ustawienie platformy

![Autocalibration — mechaniczne ustawienie platformy](../img/oled/maintenance_level@3x.png)

Uruchamia kreator OEM M07, który mierzy odniesienia i prowadzi przez regulację śrub. Nie zastępuje 25-punktowego mesh.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#maintenance_level) · [Natywne 256×64](../img/oled/maintenance_level.png).

### 8. Home Z w Maintenance

![Home Z w Maintenance](../img/oled/maintenance_home_z@3x.png)

Uruchamia tę samą chronioną procedurę Z co Home Z w Klipper. Nie jest inną, zimną wersją bazowania.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#maintenance_home_z) · [Natywne 256×64](../img/oled/maintenance_home_z.png).

### 9. Heat the extruder — procedura OEM

![Heat the extruder — procedura OEM](../img/oled/maintenance_heat@3x.png)

Uruchamia wspólną procedurę ZORTRAX_HEAT z komunikatami dla operatora. Domyślny cel procedury to 260°C; nie myl go z przykładową nastawą 200°C w gałęzi Klipper.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#maintenance_heat) · [Natywne 256×64](../img/oled/maintenance_heat.png).

### 10. Move the platform up — ruch z przytrzymaniem

![Move the platform up — ruch z przytrzymaniem](../img/oled/maintenance_platform@3x.png)

Przesuwa platformę w stronę dyszy w kontrolowanej sesji przytrzymania przycisku. Zwolnienie przerywa ruch; obowiązują granice i kontrola styku.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#maintenance_platform) · [Natywne 256×64](../img/oled/maintenance_platform.png).

### 11. Load the material — ładowanie

![Load the material — ładowanie](../img/oled/material_load@3x.png)

Uruchamia procedurę ładowania z nagrzewaniem, czynnościami operatora i podawaniem filamentu. Domyślna temperatura 240°C i długości wynikają z konfiguracji portu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#material_load) · [Natywne 256×64](../img/oled/material_load.png).

### 12. Settings — preferencje użytkownika

![Settings — preferencje użytkownika](../img/oled/settings@3x.png)

Otwiera światło, dźwięk, uśpienie, język, sortowanie modeli, dodatkowe wygrzewanie platformy oraz jasność OLED i LED.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#settings) · [Natywne 256×64](../img/oled/settings.png).

### 13. Full platform preheating — wybór ustawienia

![Full platform preheating — wybór ustawienia](../img/oled/settings_preheat@3x.png)

Otwiera Enabled/Disabled dla dodatkowej stabilizacji platformy przed drukiem. Ta pozycja nie ustawia bezpośrednio temperatury stołu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#settings_preheat) · [Natywne 256×64](../img/oled/settings_preheat.png).

### 14. Light

![Light](../img/oled/setting_light@3x.png)

DYNAMIC: światło zależne od stanu; WHITE: białe; Disabled: wyłączone według polityki projektu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#setting_light) · [Natywne 256×64](../img/oled/setting_light.png).

### 15. Buzzer

![Buzzer](../img/oled/setting_buzzer@3x.png)

Włącza albo wyłącza sygnalizację dźwiękową użytkownika.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#setting_buzzer) · [Natywne 256×64](../img/oled/setting_buzzer.png).

### 16. Sleep mode

![Sleep mode](../img/oled/setting_sleep@3x.png)

Włącza albo wyłącza mechanizm bezczynności ekranu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#setting_sleep) · [Natywne 256×64](../img/oled/setting_sleep.png).

### 17. Language

![Language](../img/oled/setting_language@3x.png)

W tej wersji udostępnia język English.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#setting_language) · [Natywne 256×64](../img/oled/setting_language.png).

### 18. Models sorting

![Models sorting](../img/oled/setting_sort@3x.png)

Zmienia kolejność prezentacji plików: data, nazwa, nazwa z rozróżnianiem wielkości liter albo wielkość pliku.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#setting_sort) · [Natywne 256×64](../img/oled/setting_sort.png).

### 19. Full platform preheating

![Full platform preheating](../img/oled/setting_preheat@3x.png)

Zapisuje opcję dodatkowej stabilizacji stołu przy następnym START_PRINT; domyślny czas wynika z konfiguracji, w tym porcie 60 s.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#setting_preheat) · [Natywne 256×64](../img/oled/setting_preheat.png).

### 20. Information — dane drukarki i pomoc

![Information — dane drukarki i pomoc](../img/oled/information@3x.png)

Udostępnia wersje, model/revizję sprzętu/numer seryjny i czas pracy oraz pomoc. Dane dostępne są według aktualnej identyfikacji i zapamiętanych liczników.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#information) · [Natywne 256×64](../img/oled/information.png).

### 21. Firmware version — wersje komponentów

![Firmware version — wersje komponentów](../img/oled/firmware@3x.png)

Pokazuje R16.12, wersję MCU, przypięty commit Klippera i odniesienie do OEM 1.3.1. Sam odczyt niczego nie wgrywa.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#firmware) · [Natywne 256×64](../img/oled/firmware.png).

### 22. Printer information — identyfikacja

![Printer information — identyfikacja](../img/oled/printer_information@3x.png)

Wyświetla model, wersję sprzętu, numer seryjny i sumę czasu według dostępnych danych fabrycznych oraz liczników portu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#printer_information) · [Natywne 256×64](../img/oled/printer_information.png).

### 23. Help — katalog komunikatów

![Help — katalog komunikatów](../img/oled/help@3x.png)

Prowadzi do Errors i wskazuje adres dokumentacji projektu. Kody komunikatów mają opisy, a nie każdy komunikat jest krytycznym wyłączeniem.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#help) · [Natywne 256×64](../img/oled/help.png).

### 24. Move axes — wybór osi

![Move axes — wybór osi](../img/oled/move_axes@3x.png)

Otwiera wybór X/Y/Z. Samo wejście nie wykonuje przejazdu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#move_axes) · [Natywne 256×64](../img/oled/move_axes.png).

### 25. Move X — kroki ręczne

![Move X — kroki ręczne](../img/oled/move_x@3x.png)

Wybór wiersza wykonuje względny krok −10, −1, −0,1, +0,1, +1 albo +10 mm. Nie jest to bazowanie ani tryb nieprzerwanego ruchu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#move_x) · [Natywne 256×64](../img/oled/move_x.png).

### 26. Move Z — kroki ręczne

![Move Z — kroki ręczne](../img/oled/move_z@3x.png)

Wybór wiersza wykonuje względny krok −10, −1, −0,1, +0,1, +1 albo +10 mm. Nie jest to bazowanie ani tryb nieprzerwanego ruchu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#move_z) · [Natywne 256×64](../img/oled/move_z.png).

### 27. Hotend PID 200C

![Hotend PID 200C](../img/oled/pid@3x.png)

Uruchamia PID_CALIBRATE dla extruder przy 200°C z tej pozycji menu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#pid) · [Natywne 256×64](../img/oled/pid.png).

### 28. Models — źródło plików

![Models — źródło plików](../img/oled/models@3x.png)

Pozwala wybrać oryginalną kartę SD albo pliki hosta. Dostępność SD zależy od zakwalifikowania jej obsługi, a nie samego obecnego w drukarce gniazda.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#models) · [Natywne 256×64](../img/oled/models.png).

### 29. Bed mesh — uruchomienie pomiaru

![Bed mesh — uruchomienie pomiaru](../img/oled/bed_mesh@3x.png)

Kliknięcie Measure 25 pad points uruchamia BED_MESH: przygotowanie temperatur i bazowania, 25 pozycji po trzy kontakty, interpolację oraz utworzenie profilu. Samo wejście do podmenu jeszcze nie mierzy.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#bed_mesh) · [Natywne 256×64](../img/oled/bed_mesh.png).

### 30. Service / Tests — narzędzia kontrolne

![Service / Tests — narzędzia kontrolne](../img/oled/service_tests@3x.png)

Zawiera odczyt diagnostyki i statusów, ale także wywołania testów materiału, kalibracji i przejazdów XY.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#service_tests) · [Natywne 256×64](../img/oled/service_tests.png).

### 31. Hotend TEMP — wybór wartości

![Hotend TEMP — wybór wartości](../img/oled/klipper_temp_hotend@3x.png)

Otwiera listę wartości do późniejszego polecenia grzania. Wskazana liczba jest nastawą menu, nie pomiarem aktualnej temperatury.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_temp_hotend) · [Natywne 256×64](../img/oled/klipper_temp_hotend.png).

### 32. Bed TEMP — wybór wartości

![Bed TEMP — wybór wartości](../img/oled/klipper_temp_bed@3x.png)

Otwiera listę wartości do późniejszego polecenia grzania. Wskazana liczba jest nastawą menu, nie pomiarem aktualnej temperatury.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_temp_bed) · [Natywne 256×64](../img/oled/klipper_temp_bed.png).

### 33. Heat hotend — bezpośrednie grzanie

![Heat hotend — bezpośrednie grzanie](../img/oled/klipper_heat_hotend@3x.png)

Wysyła natywne ustawienie celu grzałki extruder na temperaturę wybraną wcześniej w menu. Nie bazuje i nie uruchamia druku.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_heat_hotend) · [Natywne 256×64](../img/oled/klipper_heat_hotend.png).

### 34. Heat bed — bezpośrednie grzanie

![Heat bed — bezpośrednie grzanie](../img/oled/klipper_heat_bed@3x.png)

Wysyła natywne ustawienie celu grzałki heater_bed na temperaturę wybraną wcześniej w menu. Nie bazuje i nie uruchamia druku.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_heat_bed) · [Natywne 256×64](../img/oled/klipper_heat_bed.png).

### 35. Turn off heaters — wyłączenie celów grzałek

![Turn off heaters — wyłączenie celów grzałek](../img/oled/klipper_heaters_off@3x.png)

Wywołuje TURN_OFF_HEATERS. Nie jest to polecenie CANCEL_PRINT i nie należy go używać zamiast anulowania zadania.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_heaters_off) · [Natywne 256×64](../img/oled/klipper_heaters_off.png).

### 36. Home Y — bazowanie

![Home Y — bazowanie](../img/oled/klipper_home_y@3x.png)

Wyznacza odniesienie osi Y. Nie wykonuje celowo bazowania X ani pomiaru mesh.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_home_y) · [Natywne 256×64](../img/oled/klipper_home_y.png).

### 37. Home Z — bazowanie

![Home Z — bazowanie](../img/oled/klipper_home_z@3x.png)

Wyznacza odniesienie osi Z kontaktem dyszy z polem platformy; nie tworzy mapy nierówności.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_home_z) · [Natywne 256×64](../img/oled/klipper_home_z.png).

### 38. Home XY — bazowanie

![Home XY — bazowanie](../img/oled/klipper_home_xy@3x.png)

Bazowanie obu osi poziomych odbywa się w kolejności Y, potem X. Nie jest to pełny homing Z.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_home_xy) · [Natywne 256×64](../img/oled/klipper_home_xy.png).

### 39. Home XYZ — bazowanie

![Home XYZ — bazowanie](../img/oled/klipper_home_xyz@3x.png)

Uruchamia wspólne bazowanie Y, X i kontaktowe Z. Pozostaje zwykłym bazowaniem, a nie nowym pomiarem 25 pozycji.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_home_xyz) · [Natywne 256×64](../img/oled/klipper_home_xyz.png).

### 40. Fans — stan i sterowanie nawiewem

![Fans — stan i sterowanie nawiewem](../img/oled/klipper_fans@3x.png)

Otwiera odczyt wentylatora modelu i automatycznego chłodzenia hotendu, z pozycjami prędkości nawiewu modelu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#klipper_fans) · [Natywne 256×64](../img/oled/klipper_fans.png).

### 41. Print status — szczegóły zadania

![Print status — szczegóły zadania](../img/oled/print_details@3x.png)

Pokazuje stan zadania, nazwę pliku i czas. Przy aktywnym właścicielu m300_print_ui czynności pauzy i zatrzymania mają osobny kontekstowy ekran.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#print_details) · [Natywne 256×64](../img/oled/print_details.png).

### 42. Heat the platform — procedura stołu

![Heat the platform — procedura stołu](../img/oled/maintenance_heat_bed@3x.png)

Uruchamia wspólną procedurę grzania platformy, dostępną także z makra ZORTRAX_HEAT_PLATFORM.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#maintenance_heat_bed) · [Natywne 256×64](../img/oled/maintenance_heat_bed.png).

### 43. Move the platform down — ruch z przytrzymaniem

![Move the platform down — ruch z przytrzymaniem](../img/oled/maintenance_platform_down@3x.png)

Przesuwa platformę od dyszy w kontrolowanej sesji przytrzymania przycisku. Zwolnienie przerywa ruch; obowiązują granice i kontrola styku.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#maintenance_platform_down) · [Natywne 256×64](../img/oled/maintenance_platform_down.png).

### 44. Fan test — test serwisowy

![Fan test — test serwisowy](../img/oled/maintenance_fan_test@3x.png)

Uruchamia interaktywny test górnego i dolnego wentylatora. Kontroler przejmuje sterowanie wyjściami na czas tej jawnej sesji.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#maintenance_fan_test) · [Natywne 256×64](../img/oled/maintenance_fan_test.png).

### 45. Unload the material — rozładowanie

![Unload the material — rozładowanie](../img/oled/material_unload@3x.png)

Uruchamia rozgrzanie i kontrolowane wycofanie materiału zgodnie z fazami procedury.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#material_unload) · [Natywne 256×64](../img/oled/material_unload.png).

### 46. Move Y — kroki ręczne

![Move Y — kroki ręczne](../img/oled/move_y@3x.png)

Wybór wiersza wykonuje względny krok −10, −1, −0,1, +0,1, +1 albo +10 mm. Nie jest to bazowanie ani tryb nieprzerwanego ruchu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#move_y) · [Natywne 256×64](../img/oled/move_y.png).

### 47. Bed PID 60C

![Bed PID 60C](../img/oled/pid_bed@3x.png)

Uruchamia PID_CALIBRATE dla heater_bed przy 60°C z tej pozycji menu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#pid_bed) · [Natywne 256×64](../img/oled/pid_bed.png).

### 48. Save calibration — zapis PID

![Save calibration — zapis PID](../img/oled/pid_save@3x.png)

Wywołuje SAVE_CONFIG, zapisując oczekujące wyniki kalibracji i restartując Klippera. To nie jest polecenie samego odczytu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#pid_save) · [Natywne 256×64](../img/oled/pid_save.png).

### 49. Host files — pliki na Orange Pi

![Host files — pliki na Orange Pi](../img/oled/models_host@3x.png)

Przechodzi do katalogu modeli hosta obsługiwanego przez projekt. Plik nie jest automatycznie uruchamiany tylko przez wejście do listy.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#models_host) · [Natywne 256×64](../img/oled/models_host.png).

### 50. Lista temperatur HOTEND

![Lista temperatur HOTEND](../img/oled/temperature_hotend@3x.png)

Krótki klik na liczbie ustawia wartość używaną przez późniejsze Heat. Lista jest filtrowana limitami grzałki z konfiguracji; widoczne 200/60°C są przykładami.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#temperature_hotend) · [Natywne 256×64](../img/oled/temperature_hotend.png).

### 51. Lista temperatur BED

![Lista temperatur BED](../img/oled/temperature_bed@3x.png)

Krótki klik na liczbie ustawia wartość używaną przez późniejsze Heat. Lista jest filtrowana limitami grzałki z konfiguracji; widoczne 200/60°C są przykładami.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#temperature_bed) · [Natywne 256×64](../img/oled/temperature_bed.png).

### 52. Print speed — prędkość wentylatora modelu

![Print speed — prędkość wentylatora modelu](../img/oled/fan_controls@3x.png)

Ustawia nawiew modelu na jeden z poziomów 0/25/50/75/100%. W tym podmenu słowo speed dotyczy wentylatora, nie prędkości drukowania.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#fan_controls) · [Natywne 256×64](../img/oled/fan_controls.png).

### 53. OLED brightness

![OLED brightness](../img/oled/oled_brightness@3x.png)

Zmienia jasność oryginalnego wyświetlacza w 16 dostępnych poziomach. Ekran regulacji pokazuje podgląd poziomu i polecenia obsługi.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#oled_brightness) · [Natywne 256×64](../img/oled/oled_brightness.png).

### 54. LED brightness

![LED brightness](../img/oled/led_brightness@3x.png)

Zmienia jasność oświetlenia drukarki w 16 dostępnych poziomach. Ekran regulacji pokazuje podgląd poziomu i polecenia obsługi.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#led_brightness) · [Natywne 256×64](../img/oled/led_brightness.png).

### 55. M07 — przygotowanie

![M07 — przygotowanie](../img/oled/level_prepare@3x.png)

Wyświetla ostrzeżenie i warunki przygotowania autokalibracji.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#level_prepare) · [Natywne 256×64](../img/oled/level_prepare.png).

### 56. M07 — pozycja wyjściowa śrub

![M07 — pozycja wyjściowa śrub](../img/oled/level_tighten@3x.png)

Prosi o dokręcenie trzech pokręteł regulacyjnych zgodnie z procedurą.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#level_tighten) · [Natywne 256×64](../img/oled/level_tighten.png).

### 57. M07 — nagrzewanie

![M07 — nagrzewanie](../img/oled/level_heating@3x.png)

Pokazuje etap nagrzewania ekstrudera w kreatorze.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#level_heating) · [Natywne 256×64](../img/oled/level_heating.png).

### 58. M07 — regulacja wskazanej śruby

![M07 — regulacja wskazanej śruby](../img/oled/level_adjust@3x.png)

Podaje narożnik, kierunek i przybliżony obrót potrzebny według bieżącego pomiaru.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#level_adjust) · [Natywne 256×64](../img/oled/level_adjust.png).

### 59. M07 — wynik i zakończenie

![M07 — wynik i zakończenie](../img/oled/level_result@3x.png)

Prezentuje wynik autokalibracji i przejście dalej po potwierdzeniu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#level_result) · [Natywne 256×64](../img/oled/level_result.png).

### 60. PAUSE MENU — wznowienie, wymiana, zatrzymanie

![PAUSE MENU — wznowienie, wymiana, zatrzymanie](../img/oled/pause@3x.png)

Resume the print wznawia zgodne zadanie; Change the material otwiera wymianę w pauzie; Stop the print przechodzi do jawnego potwierdzenia anulowania.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#pause) · [Natywne 256×64](../img/oled/pause.png).

### 61. STOP THE PRINT? — potwierdzenie anulowania

![STOP THE PRINT? — potwierdzenie anulowania](../img/oled/cancel_confirmation@3x.png)

No pozostawia zadanie w pauzie; Yes, stop the print wywołuje CANCEL_PRINT. Anulowanie zamyka plik i usuwa stan pauzy, wyłącza cele grzałek, a parkowanie nie może blokować anulowania.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#cancel_confirmation) · [Natywne 256×64](../img/oled/cancel_confirmation.png).

### 62. Notice #101 — brak modeli

![Notice #101 — brak modeli](../img/oled/no_models@3x.png)

Informuje o braku modeli w odczytywanym źródle. Nie jest sam w sobie błędem planera ruchu.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#no_models) · [Natywne 256×64](../img/oled/no_models.png).

### 63. Księżyc — ekran bezczynności

![Księżyc — ekran bezczynności](../img/oled/sleep@3x.png)

Pokazuje przejście panelu w uśpienie zgodnie z polityką wyświetlacza.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#sleep) · [Natywne 256×64](../img/oled/sleep.png).

### 64. Status Ready — temperatury i stan

![Status Ready — temperatury i stan](../img/oled/status_ready@3x.png)

Pokazuje temperatury, nawiew, mnożnik prędkości i komunikat statusu. Wartości są bieżącymi obserwacjami w działającej drukarce; tutaj użyto stanu demonstracyjnego.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#status_ready) · [Natywne 256×64](../img/oled/status_ready.png).

### 65. Status Printing — postęp zadania

![Status Printing — postęp zadania](../img/oled/status_printing@3x.png)

Pokazuje temperatury, postęp, czas i komunikat. 42% oraz 200/60°C w renderze są wyłącznie przykładem.

[Obsługa, warunki, grafika i Fluidd](OLED_FUNCTIONS.md#status_printing) · [Natywne 256×64](../img/oled/status_printing.png).

## 8. Podgląd w Fluidd

Sterowanie ×1/×2/×3, centrowanie, kolorystyka i zasady HIDE/SHOW opisane są w [aktualizacji z 10.11.2026](UPDATE_2026-11-10.md). To nie są nowe pozycje na fizycznym OLED.
