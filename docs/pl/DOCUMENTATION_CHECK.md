# Kontrola dokumentacji beta.20 i pochodzenie ilustracji

[Instrukcja główna](../../README_PL.md) · [Ilustrowane funkcje OLED](OLED_FUNCTIONS.md) · [Zmiany dzisiejsze](UPDATE_2026-11-10.md)

Stan opisu: **10 listopada 2026, beta.20**, kod odniesienia `4828a9da9d5fd8b0b93eb2ac267732ee7e49d506`. Zmiana dokumentacji nie zmienia wykonawczego hosta, MCU, frontendu ani konfiguracji. Nie utworzono nowej bety tylko dla manuali.

## Zakres wykonany

| Wymaganie | Dokument lub materiał |
|---|---|
| Aktualna wersja na stronie głównej i w instrukcjach instalacji | README PL/EN, FIRST_INSTALL PL/EN i INSTALL EN wskazują opublikowaną beta.20 |
| Dzisiejsze poprawki | UPDATE_2026-11-10: beta.18 Tune, beta.19 skalowanie, beta.20 układ i kolorystyka |
| Instrukcja funkcji z obrazami | OLED_FUNCTIONS: 65 ilustrowanych pozycji/stadiów z działaniem, warunkami, opisem grafiki i odpowiednikiem Fluidd |
| Rzeczywiste menu i bitmapy | OLED_MENU_REFERENCE oraz 65 obrazów 256×64 i 65 dokładnych powiększeń 3× |
| Current UI po angielsku | FRONTEND_BETA20; historyczne sekcje w FLUIDD_M300 są wyraźnie oznaczone |
| Instrukcja ×1/×2/×3 | Trzy demonstracje z rzeczywistego arkusza CSS beta.20 i helpera pikseli |
| Poprawione rozróżnienia | TEMP nie grzeje; Heat uruchamia cel; All nie mierzy mesh; podgląd nie aktywuje kompensacji; PID SAVE restartuje |
| Parametry, planer, mapy temperatur | Zachowane opisy źródeł, limitów, przepływu i 205 par charakterystyki stołu |
| Aktualizacja i granice testów | Ready/bezczynność, zachowanie kalibracji, brak potrzeby wgrywania MCU dla tych zmian, jawne granice testów programowych |

## Trzy rodzaje obrazów

**Zrzuty użytkownika:** oryginalne PNG panelu Fluidd, makr i wyniku mesh pozostają niezmienione bajtowo. Ich sumy zapisuje [IMAGE_PROVENANCE.json](../reports/IMAGE_PROVENANCE.json). To obrazy wcześniejszego interfejsu; obraz makr jest historyczny, a stary mesh ma odmienną kolejność kart. Nie udajemy, że przedstawiają beta.20 po wszystkich zmianach.

**Rendery fizycznego OLED:** programowe wywołanie produkcyjnych metod rows(), selektorów grafik, fontu bitmapowego oraz rendererów menu/statusu/procedur. Użyto demonstracyjnych temperatur, stanu druku, rewizji sprzętu i zastępczego numeru seryjnego. Żaden render nie komunikuje się z MCU ani nie wydaje G-code. [Manifest 65 ekranów](../reports/OLED_RENDER_MANIFEST.json) zawiera SHA natywnej klatki i PNG. [Katalog funkcji](../reports/OLED_FUNCTION_CATALOG.json) wiąże wszystkie obrazy z opisami.

**Demonstracje Fluidd:** izolowana przeglądarka z produkcyjnym CSS komponentu i skompilowaną funkcją pikseli. Są podpisane jako demonstracyjne, nie jako zrzuty aktywnej sesji drukarki. [Manifest demonstracji](../reports/FLUIDD_OLED_DEMO.json) wskazuje źródła, wersję przeglądarki i sumy trzech obrazów. Nie udostępniono plików fontów.

## Odtwarzanie i kontrola

```bash
python ci/prepare_upstream.py
python docs/tools/render_oled_manual.py --klipper .ci/pristine
python docs/tools/check_manual.py
```

Do odtworzenia demonstracji Fluidd potrzebny jest skompilowany TypeScript helper i Chromium/Playwright. [Skrypt demonstracji](../tools/render_fluidd_oled_manual.py) przyjmuje --module oraz opcjonalnie --chromium-executable. Sam renderer OLED wymaga Pillow i Jinja2 zgodnie z zależnościami projektu.

[Sprawdzenie dokumentacji](../tools/check_manual.py) kontroluje kompletność rozdziałów, lokalne odnośniki, obrazy i ich sumy, dokładne powiększenie 3×, zgodność wszystkich 39 makr, źródła 205 par mapy temperatury, 25/61×61 w mesh, bieżące rewizje i wszystkie 65 opisów. [Raport](../reports/DOCUMENTATION_VALIDATION.json) podaje rzeczywistą liczbę kontroli, nie stałą deklarację poprzedniego wydania.

Plik [DOCUMENTATION_FILES.json](../reports/DOCUMENTATION_FILES.json) zawiera sumy publikowanych materiałów, a [DOC_SOURCE_BASELINE.json](../reports/DOC_SOURCE_BASELINE.json) sumy źródeł użytych do ilustracji i weryfikacji. Kontrola kończy się błędem, jeżeli źródło lub wymagany obraz nie pasuje; nie zmniejsza się wymagań tylko po to, żeby uzyskać PASS.

## Co rzeczywiście potwierdzono

Release beta.20 ma udany [build 42798305380](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/actions/runs/42798305380): 741 testów hosta, 140 frontendu, 84 porównania pikseli, 54 testy geometrii w Chromium/Firefox, ARM, natywny Klippy i integralność pakietu. Użytkownik zaakceptował zgłoszony efekt wizualny beta.20. Jest to osobne od bieżącej walidacji dokumentacji.

Nie wykonano nowych pomiarów temperatur, przepływu, mechaniki ani dokładności kontaktowego Z na drukarce. Przykładowe 200/60°C, odchyłki, obroty śrub i czas druku na ilustracjach nie są nastawami do kopiowania. Nie zadeklarowano uniwersalnego maksymalnego przepływu ekstrudera ani gwarancji równego rastra po lupie systemowej/pulpicie zdalnym. Oryginalne tagi wydania i pliki ZIP pozostają niezmienione.
