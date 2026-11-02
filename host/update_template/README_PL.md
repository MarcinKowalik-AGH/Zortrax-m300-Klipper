# Host M300 R16.5 — menu Maintenance i Material

[English](README.md) · [Instalacja](docs/pl/INSTALL.md) · [Funkcje](docs/pl/FEATURES.md)

Aktualizacja natywnego M300 R15.3/R15.5/R15.6/R15.7; wybór Z z fabrycznej rewizji
wymaga MCU R14.5. Pełny artefakt Actions zawiera aplikację MCU. Ten ZIP hosta
nie zawiera bootloadera ani firmware do wgrania.

Instalator aktualizuje menu i adapter G28 oraz migruje konfigurację do
bazowania Z przy 180C, STEP 2 us, XY 300 mm/s i natywnych limitów.
PID-y, kalibracja E, ustawienia wyświetlacza i zapisane kalibracje pozostają.
Plan pokazuje wszystkie zmiany; receipt pozwala je dokładnie cofnąć.

Grupy OLED i Fluidd: Klipper, Zortrax M300, Service / Tests (TEST M300 we Fluidd).
Po Ready wykonaj setup_fluidd.py --apply i odśwież przeglądarkę. Sześć makr
Maintenance/Material znajduje się w ZORTRAX M300; alias poziomowania i
nieukończony wydruk OEM pozostają w TEST. Zachowano sen ekranu, chłodzenie
MCU i lifecycle. Wgrany MCU R14.5 może pozostać.

Uruchom python3 VERIFY.py, python3 -m unittest discover -s tests -v (203 testów)
i python3 install.py. Zastosuj instrukcję --apply i odbioru fizycznego. CI
sprawdza programy; nie mierzy 300 mm/s przy pełnym obciążeniu drukarki.

R16.5 przywraca również połączenie po restarcie hosta/usługi przez jedną próbę
natywnego resetu starej sesji lub błędu heartbeat. Nie wznawia poprzedniego
grzania/ruchu i nie resetuje automatycznie innych kodów awarii.
Odbiór na drukarce opisuje docs/pl/CONNECTION.md.

R16.5 przywraca fabryczne nastawy procedur: kalibracja/poziomowanie 260°C, Load/Unload 240°C. Instalator aktualizuje także istniejące sekcje i makra z R16.3/R16.4. Zwykły G28 Z zachowuje osobne 180°C. Ręczne grzanie, PID oraz M600 z temperaturą pauzowanego wydruku zachowują dotychczasowe działanie. Status m300_calibration i m300_filament udostępnia procedure_temperature.

R16.5 dodaje oryginalny układ podmenu Maintenance/Material, Heat (260°C),
ruch stołu przez przytrzymanie oraz natywne Load/Unload (240°C). Sześć makr
znajduje się w ZORTRAX M300. OLED i Fluidd współdzielą teksty OEM; 110 ekranów
wzorcowych zgadza się z rendererem oryginału.
[Obsługa menu i odbiór](docs/pl/MAINTENANCE_MATERIAL.md).
