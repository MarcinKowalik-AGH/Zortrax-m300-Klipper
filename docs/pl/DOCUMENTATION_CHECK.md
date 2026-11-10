# Kontrola kompletności dokumentacji i pochodzenie materiałów

[Spis dokumentacji](../../README_PL.md) · [Obsługa](USER_GUIDE.md) · [OLED](OLED_MENU_REFERENCE.md)

Dokumentacja odnosi się do **v1.0.0-beta.17**, commit `d6ddf9c3bee58dc2209946a0073f8a708d964073`, stan opisu 10.11.2026. Aktualizacja dokumentacji nie jest nowym wydaniem firmware i nie wymaga zmiany konfiguracji drukarki.

## Wykonanie uzgodnionego planu

| Wymaganie | Realizacja | Kontrola |
|---|---|---|
| Główna instrukcja i spis | [README_PL](../../README_PL.md) | Odnośniki do wszystkich rozdziałów |
| Zakres Klippera i architektura | [OVERVIEW_PL](OVERVIEW_PL.md) | Podział odpowiedzialności, diagram Mermaid, stan i ograniczenia |
| Pierwsza instalacja | [FIRST_INSTALL](FIRST_INSTALL.md) | Zachowana istniejąca procedura, uaktualniony wybór beta.17 |
| Obsługa użytkownika | [USER_GUIDE](USER_GUIDE.md) | Start, filament, pauza, wznowienie, anulowanie, aktualizacja |
| Rzeczywiste menu i obrazy | [OLED_MENU_REFERENCE](OLED_MENU_REFERENCE.md) | Wiersze pobrane z kodu, 43 ekrany × 2 rozdzielczości |
| Trzy zrzuty użytkownika | Wprowadzenie / obsługa / mesh | Własne pliki repo, podpisy, historyczny panel oznaczony |
| Planer i wydajność ekstruzji | [PRINT_LIMITS_AND_PLANNER](PRINT_LIMITS_AND_PLANNER.md) | Rozdzielenie limitów ruchu, suchego testu i przepływu |
| Parametry oraz UART/SPI | [TECHNICAL_REFERENCE](TECHNICAL_REFERENCE.md) | Szablon vs efektywna konfiguracja, zgodność baud, skale Z |
| Mapy temperatur z firmware | Rozdział techniczny | 205 par stołu i 2 punkty liniowego hotendu, granice interpretacji |
| Leveling i mesh | [BED_MESH_AND_LEVELING](BED_MESH_AND_LEVELING.md) | M07 ≠ mesh, 25 pozycji, 61×61 resampling, zapis ≠ aktywacja |
| Wszystkie makra konfiguracyjne | [MACRO_REFERENCE](MACRO_REFERENCE.md) | 39 nazw porównanych z sekcjami źródłowych CFG |
| Ograniczenia i walidacja | Ten rozdział i przegląd | Brak deklaracji testu na sprzęcie lub pomiaru przepływu |

## Materiały fotograficzne

Trzy zrzuty zostały dostarczone przez użytkownika z prośbą o umieszczenie w publicznej dokumentacji. Zachowano oryginalne pliki PNG, pełne wymiary, paletę i treść — bez kadrowania, przeskalowania ani odtwarzania tekstu. Sumy opublikowanych plików są identyczne z oryginałami. Nazwy oryginałów, sumy SHA-256 i opisy: [IMAGE_PROVENANCE.json](../reports/IMAGE_PROVENANCE.json).

Aktualny interfejs jest na zrzucie z 10.11.2026. Makra z 08.11.2026 pokazują wcześniejszy stan grupowania, a nie wadę bieżącej beta.17. Zrzut mesh z 09.11.2026 jest przykładowym wynikiem użytkownika, nie plikiem kalibracji do pobrania i zastosowania w innej drukarce.

## Rendery OLED

43 obrazy natywne 256×64 i 43 podglądy 768×192 wykonano funkcjami projektu z przypiętego kodu. Przykładowe temperatury, stan zadania, rewizja HW05, licznik godzin i zastępczy numer seryjny są jawnie demonstracyjne. Nie zebrano nowych odczytów z drukarki. Manifest: [OLED_RENDER_MANIFEST.json](../reports/OLED_RENDER_MANIFEST.json).

[Skrypt renderowania](../tools/render_oled_manual.py) odtwarza menu, czcionki i grafiki; [skrypt kontroli](../tools/check_manual.py) sprawdza pliki, odnośniki, nazwy makr, wymiary i identyczność skalowania nearest-neighbour oraz wymagane fakty z konfiguracji. Nie generowano obrazów OLED modelem obrazowym i nie próbowano sterować drukarką z dokumentacji.

## Kontrole automatyczne

```bash
python docs/tools/check_manual.py
```

Raport: [DOCUMENTATION_VALIDATION.json](../reports/DOCUMENTATION_VALIDATION.json). Kontrola jest powtarzalna i kończy się błędem, gdy brakuje rozdziału, zrzutu, renderu, odnośnik lokalny jest błędny, nazwy makr odbiegają od źródeł albo podgląd nie jest dokładnym powiększeniem 3×. Raport dokumentacji nie zastępuje istniejących testów firmware.

Oprogramowanie odniesienia beta.17 miało pełny udany [przebieg CI 42723306325](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/actions/runs/42723306325): 741 testów hosta, 111 testów frontendu, natywny Klippy FILEOUTPUT, kompilację ARM i 60 przypadków porównania pikseli w Chromium/Firefox. Nie są to nowe pomiary mechaniki, temperatury czy wydajności ekstrudera wykonane podczas pisania instrukcji.

## Co sprawdzono merytorycznie, a czego nie należy wnioskować

- Parametry w tabelach porównano z plikami konfiguracji i odpowiednimi modułami. Efektywna konfiguracja istniejącej drukarki może różnić się od szablonu.
- Rozdzielono procedury natywne od testów eksperymentalnych i kwalifikowanych funkcji SD/Z-code.
- Usunięto nieprecyzyjne utożsamienie map temperatur z samymi celami grzania.
- Nie podano niezmierzonego maksymalnego przepływu fabrycznego hotendu. Wyliczenia Q są oznaczone jako przykłady.
- Nie stwierdzono, że kolorowy mesh jest aktywny; udokumentowano `AUTO` i brak profilu.
- Nie obiecano uniwersalnej numeracji złącza DEBUG ani zalecanego 1500000 baud dla każdej instalacji.
- Kod wykonawczy hosta, MCU, konfiguracja ruchu/grzania i frontend nie są zmieniane przez tę publikację dokumentacji.

## Źródła pierwotne

W każdym rozdziale odnośniki prowadzą do źródeł projektu lub dokumentacji producenta/Klippera. Podstawowe pliki: [konfiguracja sprzętu](../../host/config/m300_classic_base.cfg), [czujniki](../../host/config/m300_classic_sensors.cfg), [procedury](../../host/config/m300_classic_services.cfg), [makra](../../host/config/m300_operations.cfg), [menu](../../host/klippy/extras/m300_menu.py), [kontroler druku](../../host/klippy/extras/m300_print_control.py), [mesh](../../host/klippy/extras/m300_pad_mesh.py). Archiwalne audyty: [PROVENANCE](../en/PROVENANCE.md), [CONFIGURATION_AUDIT](../en/CONFIGURATION_AUDIT.md), [HARDWARE_VARIANTS](../en/HARDWARE_VARIANTS.md).

Nie dołączono pełnego fabrycznego dumpu, prywatnych logów, poświadczeń ani numeru seryjnego użytkownika. Dokumentacja nie znosi konieczności testu odbiorczego na fizycznej maszynie po zmianie mechaniki lub elektroniki.
