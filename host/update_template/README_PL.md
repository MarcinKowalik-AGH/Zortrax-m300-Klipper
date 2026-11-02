# Host M300 R15.7 — rewizja fabryczna i wariant Z

[English](README.md) · [Instalacja](docs/pl/INSTALL.md) · [Warianty sprzętu](docs/pl/HARDWARE_VARIANTS.md)

Aktualizacja natywnego hosta M300 Classic R15.5/R15.6. Domyślny wybór factory
wymaga pasującej aplikacji MCU R14.5. Aplikacja MCU jest w pełnym artefakcie
Actions, a nie wewnątrz tego ZIP-a samego hosta.

ID3 fabryczne wybiera Z=800 dla rewizji przed HW05, w pozostałych 400. Natywny
stepper, M07 i status OLED używają jednej skali. ZORTRAX_HARDWARE_STATUS podaje
rewizję, rotation_distance z pliku/używane i tryb. Błędny rekord nie jest
zgadywany. Jawny z_profile=config zachowuje skalę wybraną w konfiguracji.

Instalator zachowuje zapisane PID-y, kalibrację ekstrudera, pliki konfiguracji
i obecne ustawienia ekranu. Rozpoznaje znane sumy modułów R15.5/R15.6,
zapisuje dokładny receipt do cofnięcia i odmawia nadpisania nieznanych edycji.
Zachowano poprawki menu R15.6 oraz księżyc / Entering sleep mode.
Nie dodano cyklicznych zapytań ani przechwytywania ruchu.

Uruchom python3 VERIFY.py, python3 -m unittest discover -s tests -v i
python3 install.py, aby zobaczyć plan. Zestaw zawiera 92 testów.
Kolejność zgodnej aktualizacji MCU/hosta opisuje docs/pl/INSTALL.md. Publiczne
CI i kompilacja ARM są walidacją programową; droga fizycznego Z wymaga pomiaru.
