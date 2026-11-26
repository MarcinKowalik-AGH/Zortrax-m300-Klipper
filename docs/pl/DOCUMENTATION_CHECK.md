# Kontrola podręcznika i pochodzenie ilustracji

Podręcznik jest przygotowany dla M300 Classic z hostem 1.0.4 i MCU 1.0.9. [Strona projektu](../../README_PL.md) prowadzi do instalacji, eksploatacji oraz prób sprzętowych. [Podręcznik operatora](USER_GUIDE.md) łączy czynności od pomiaru płyty po zakończenie wydruku. Źródłami wersji i limitów są [manifest portu](../../PORT.json) i [profil drukarki](../../host/config/m300_classic_base.cfg).

## Obrazy

- [Aktualny widok z kamerą i temperaturami Host/MCU](../img/m300-fluidd-camera-thermals-oled-2026-11-26.png) to niezmieniony zrzut z 26.11.2026, użyty na stronie głównej. OLED pokazuje przygotowanie meshu 25 punktów.


- [Wydruk testu przepływu na M300 Classic](../img/m300-orcaslicer-fluidd-printing.png) to oryginalny zrzut zakładki Device z 20.11.2026. Widoczne są wydruk, temperatury, podgląd OLED i aktywny profil `m300_pads`.
- Trzy wcześniejsze zdjęcia ekranu pokazują historyczny układ Fluidd, grupy makr i podgląd zmierzonej siatki. [Manifest zrzutów](../reports/IMAGE_PROVENANCE.json) podaje daty, wymiary i sumy SHA-256 wszystkich pięciu PNG.
- [Atlas OLED](OLED_FUNCTIONS.md) obejmuje 65 demonstracyjnych stanów beta.20. Każdy ma obraz 256 × 64 oraz powiększenie 3×. Powiązania ilustracji z funkcjami zawiera [katalog](../reports/OLED_FUNCTION_CATALOG.json). Osobno przechowujemy [trzy demonstracje skalowania we Fluidd](../reports/FLUIDD_OLED_DEMO.json).

## Odtworzenie kontroli

W katalogu źródłowym z Pythonem i Pillow wykonaj:

```bash
python3 docs/tools/check_manual.py
python3 ci/acceptance_register.py --check
```

Pierwsze polecenie porównuje makra z konfiguracją, sprawdza odnośniki, sumy obrazów i zgodność klatek OLED. Drugie porównuje [rejestr sprzętu](ACCEPTANCE_REGISTER.md) z danymi źródłowymi. Wyniki fizycznych prób dopisuje się na podstawie relacji operatora. Test programowy obejmujący przerwę przy programowaniu banku i odczyt licznika po normalnym cyklu zasilania mają w rejestrze osobne podstawy dowodowe.
