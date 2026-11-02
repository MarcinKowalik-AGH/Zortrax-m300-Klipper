# Zortrax M300 Classic — Klipper R16.5

[English](README.md) · [Instalacja](docs/pl/INSTALL.md) · [Funkcje / odbiór](docs/pl/FEATURES.md) · [Kompilacja](docs/pl/BUILD.md)

Iteracja testowa: **MCU R14.5 + host R16.5**, Klipper
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`, STM32F103, Cartesian M300 Classic.

- Natywne grzanie, wentylatory, PID, SAVE_CONFIG, XYZ/E i obsługa druku Klippera.
- Natywny G28/probe z punktem M300, minimum 180C przy Z i końcowym odstępem 5 mm.
- Fabryczna rewizja wybiera Z400/Z800 raz przed konfiguracją.
- STEP 2 us; profil XY 300 mm/s, natywne M220 i ustawienia prędkości/przyspieszeń.
- Pierwszy ekran stanu Klippera; menu Klipper / Zortrax M300 / Service / Tests.
- Zachowane księżyc/przygaszanie/wybudzanie, chłodzenie lokalne MCU i łączność.
- Odwracalna migracja hosta/konfiguracji z zachowaniem PID i kalibracji E.

GitHub Actions wykonuje czysty build ARM, 203 testów hosta, testy modeli
rejestrowych i 13 scenariuszy rzeczywistego Klippy FILEOUTPUT. W Artifacts
udanego przebiegu pobierz `m300-r14_5-host-r16_5-test-<commit>`. Zawiera M3B,
BIN/ELF/mapę/słownik, instalator Orange Pi R16, grupowanie Fluidd, raporty i sumy.
Wgrany MCU R14.5 może pozostać.

Źródła runtime: host/klippy/extras, szablony konfiguracji: host/config,
instalator/testy: host/update_template, MCU: mcu/SOURCE_MCU. CI składa paczki
z tych głównych plików i upstream sprawdzanego SHA-256. Dokumentacja jest
rozdzielona na docs/en i docs/pl. Nie publikujemy prywatnego dumpu fabrycznego
ani bootloadera.

FEATURES.md rozdziela potwierdzenia operatora i odbiór nowej iteracji.
Natywny homing przy 180C oraz timing 300 mm/s pod obciążeniem wymagają odbioru
tej wersji na drukarce. Maintenance/Material są w ZORTRAX M300; pojedynczy test
grzałki lub XYZ nie zatwierdza całego ich przebiegu.

R16.5 dodaje jedną próbę natywnego resetu MCU po starcie procesu hosta dla
starej uzbrojonej sesji lub zatrzasku heartbeat. Awarie sprzętu/M112 pozostają
do jawnego odzyskania. Zobacz [Cykl połączenia](docs/pl/CONNECTION.md).

R16.5 łączy wykonawcę M07 z natywnym ruchem oraz wspólnymi ekranami OLED/Fluidd; zobacz [Poziomowanie](docs/pl/LEVELING.md).

R16.3.1 poprawiło nazwy makr testowych. R16.5 naprawia pełne cofnięcie po rozwarciu styku M07, przywraca ostrzeżenie i potwierdzenie trzech śrub oraz oryginalny układ dialogów z czcionką 13 px. OLED i Fluidd korzystają z tych samych tekstów OEM. 85 ekranów wzorcowych zgadza się piksel po pikselu z modelem oryginału w pięciu językach; odbiór na drukarce pozostaje do wykonania. [Audyt ekranów i algorytmu](docs/pl/LEVELING.md). Aplikacja MCU pozostaje bez zmian.

R16.5 przywraca fabryczne nastawy procedur: kalibracja/poziomowanie 260°C, Load/Unload 240°C. Instalator aktualizuje także istniejące sekcje i makra z R16.3/R16.4. Zwykły G28 Z zachowuje osobne 180°C. Ręczne grzanie, PID oraz M600 z temperaturą pauzowanego wydruku zachowują dotychczasowe działanie. Status m300_calibration i m300_filament udostępnia procedure_temperature.

R16.5 dodaje oryginalny układ podmenu Maintenance/Material, Heat (260°C),
ruch stołu przez przytrzymanie oraz natywne Load/Unload (240°C). Sześć makr
znajduje się w ZORTRAX M300. OLED i Fluidd współdzielą teksty OEM; 110 ekranów
wzorcowych zgadza się z rendererem oryginału.
[Obsługa menu i odbiór](docs/pl/MAINTENANCE_MATERIAL.md).
