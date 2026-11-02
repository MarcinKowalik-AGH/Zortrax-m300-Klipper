# Kompilacja i rozwój

[English](../en/BUILD.md)

## GitHub Actions

1. Zapisz zmiany w main albo uruchom workflow ręcznie w Actions.
2. Otwórz uruchomienie dotyczące konkretnego commitu.
3. Sprawdź zakończenie kompilacji ARM, testów hosta, rzeczywistego Klippy
   FILEOUTPUT i pakowania.
4. Pobierz artefakt w sekcji Artifacts. BUILD_PROVENANCE.json wskazuje commit,
   a SHA256SUMS obejmuje pliki wynikowe.

Runner: Ubuntu 24.04, GNU ARM/newlib, Python 3.12. Rzeczywiste wersje
kompilatora, linkera i Pythona są w TOOLCHAIN.json i logach. Testy MCU wykonują
modele rejestrów skompilowane natywnym C; nie mierzą cykli fizycznego F103.

Builder kontroluje sumę ZIP upstream, hashe źródeł przed zmianą, konfigurację
F103, wektory pod 0x08008000, granice pamięci, komendy i stałe słownika,
lokalne chłodzenie i własność zasobów. Pakowanie sprawdza świeże pliki według
BUILD_REPORT.json przed utworzeniem M3B.

## Odpowiednik lokalny

Potrzebne są GNU Arm Embedded z newlib/nano, make, natywny kompilator C i
Python 3.12. W osobnym środowisku Pythona:

~~~bash
python ci/prepare_upstream.py
python -m pip install -r .ci/pristine/scripts/klippy-requirements.txt
python mcu/SOURCE_MCU/tools/build.py --archive mcu/SOURCE_MCU/UPSTREAM_KLIPPER_PINNED.zip --work .ci/arm-build --output dist/mcu --jobs 4
python ci/run_checks.py --dictionary dist/mcu/klipper.dict
python ci/package_release.py --build dist/mcu
~~~

Przy ponownej kompilacji w istniejącym własnym katalogu buildera dodaj --fresh.
Obce istniejące katalogi są chronione przed zastąpieniem. Pobrane źródła
upstream, generowane katalogi hosta i wyniki kompilacji są pomijane przez Git.

## Wprowadzanie zmian

Moduły runtime zmieniaj w host/klippy/extras, ustawienia ekranu w host/config,
a kod MCU w mcu/SOURCE_MCU. Zmiana zachowania powinna mieć odpowiedni test.
Aktualizacja hosta i jej manifest powstają dopiero podczas budowania.
Lista plików aktualizacji i liczba testów hosta są w PORT.json.

Opcjonalny skrypt porównania księżyca wymaga prywatnie przechowywanego
oryginalnego firmware. Nie jest zaliczany do automatycznych testów publicznego CI.
