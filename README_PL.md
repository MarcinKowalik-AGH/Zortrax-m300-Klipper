# Zortrax M300 Classic — Klipper R16.2

[English](README.md) · [Instalacja](docs/pl/INSTALL.md) · [Funkcje / odbiór](docs/pl/FEATURES.md) · [Kompilacja](docs/pl/BUILD.md)

Iteracja testowa: **MCU R14.5 + host R16.2**, Klipper
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`, STM32F103, Cartesian M300 Classic.

- Natywne grzanie, wentylatory, PID, SAVE_CONFIG, XYZ/E i obsługa druku Klippera.
- Natywny G28/probe z punktem M300, minimum 180C przy Z i końcowym odstępem 5 mm.
- Fabryczna rewizja wybiera Z400/Z800 raz przed konfiguracją.
- STEP 2 us; profil XY 300 mm/s, natywne M220 i ustawienia prędkości/przyspieszeń.
- Pierwszy ekran stanu Klippera; menu Klipper / Zortrax M300 / Service / Tests.
- Zachowane księżyc/przygaszanie/wybudzanie, chłodzenie lokalne MCU i łączność.
- Odwracalna migracja hosta/konfiguracji z zachowaniem PID i kalibracji E.

GitHub Actions wykonuje czysty build ARM, 131 testów hosta, testy modeli
rejestrowych i 13 scenariuszy rzeczywistego Klippy FILEOUTPUT. W Artifacts
udanego przebiegu pobierz `m300-r14_5-host-r16_2-test-<commit>`. Zawiera M3B,
BIN/ELF/mapę/słownik, instalator Orange Pi R16, grupowanie Fluidd, raporty i sumy.
Wgrany MCU R14.5 może pozostać.

Źródła runtime: host/klippy/extras, szablony konfiguracji: host/config,
instalator/testy: host/update_template, MCU: mcu/SOURCE_MCU. CI składa paczki
z tych głównych plików i upstream sprawdzanego SHA-256. Dokumentacja jest
rozdzielona na docs/en i docs/pl. Nie publikujemy prywatnego dumpu fabrycznego
ani bootloadera.

FEATURES.md rozdziela potwierdzenia operatora i odbiór nowej iteracji.
Natywny homing przy 180C oraz timing 300 mm/s pod obciążeniem wymagają odbioru
tej wersji na drukarce. Procedury M03/M07/M08 pozostają w TEST; pojedynczy test
grzałki lub XYZ nie zatwierdza całego ich przebiegu.

R16.2 dodaje jedną próbę natywnego resetu MCU po starcie procesu hosta dla
starej uzbrojonej sesji lub zatrzasku heartbeat. Awarie sprzętu/M112 pozostają
do jawnego odzyskania. Zobacz [Cykl połączenia](docs/pl/CONNECTION.md).
