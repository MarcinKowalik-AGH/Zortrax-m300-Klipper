# Host M300 R16 — normalna obsługa i osobna grupa TEST

[English](README.md) · [Instalacja](docs/pl/INSTALL.md) · [Funkcje](docs/pl/FEATURES.md)

Aktualizacja natywnego M300 R15.5/R15.6/R15.7; wybór Z z fabrycznej rewizji
wymaga MCU R14.5. Pełny artefakt Actions zawiera aplikację MCU. Ten ZIP hosta
nie zawiera bootloadera ani firmware do wgrania.

Instalator aktualizuje menu i adapter G28 oraz migruje konfigurację do
bazowania Z przy 180C, STEP 2 us, XY 300 mm/s i natywnych limitów.
PID-y, kalibracja E, ustawienia wyświetlacza i zapisane kalibracje pozostają.
Plan pokazuje wszystkie zmiany; receipt pozwala je dokładnie cofnąć.

Grupy OLED i Fluidd: Klipper, Zortrax M300, Service / Tests (TEST M300 we Fluidd).
Po Ready wykonaj setup_fluidd.py --apply i odśwież przeglądarkę. M03/M07/M08
pozostają w TEST. Zachowano sen ekranu, chłodzenie MCU i lifecycle. Wgrany
MCU R14.5 może pozostać.

Uruchom python3 VERIFY.py, python3 -m unittest discover -s tests -v (111 testów)
i python3 install.py. Zastosuj instrukcję --apply i odbioru fizycznego. CI
sprawdza programy; nie mierzy 300 mm/s przy pełnym obciążeniu drukarki.
