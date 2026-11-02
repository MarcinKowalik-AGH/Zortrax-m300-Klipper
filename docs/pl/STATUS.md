# Stan — iteracja testowa R16

[English](../en/STATUS.md) · [Funkcje i odbiór](FEATURES.md)

MCU R14.5 + host R16, Klipper ee2c6fb6b00b2b5d097ef70d0868df7d74943b51.
Operator potwierdza natywną termikę/wentylatory, XYZ/E, OLED i łączność.
R16 porządkuje te ścieżki w obsłudze normalnej, oddzielając niedokończone
procedury OEM. Zastępuje dawny adapter uruchomieniowy przez natywny G28/probe
z punktem kontaktu M300, minimum 180C i końcowym odstępem 5 mm.
Powtórny homing nie dodaje odstępu do poprzedniej pozycji Z299.

Normalny ruch nie ma bramki deklaracji na 60 sekund, zakresu Z30 ani nakładki
zasobów na G1. Zachowano natywne granice Cartesian, verify_heater, ochronę
zimnej ekstruzji, guard MCU i niezależne chłodzenie. Zachowano odczyt ID3 i wybór
Z400/Z800 oraz zapisane PID-y i kalibrację ekstrudera.

Przygaszanie/wygaszanie/wybudzanie OLED oraz księżyc/Entering sleep mode są
zachowane. idle_timeout urządzenia pozostaje dotychczasowym ustawieniem
natywnym. Sen ekranu nie oznacza przywracania targetów ani pozycji silników.

Testy programowe: 112 hosta, 8 kontraktów repozytorium, 6720 przypadków STEP,
52 chłodzenia, 1792 dekodera, start/timery i 13 scenariuszy rzeczywistego Klippy
FILEOUTPUT. Obejmują 180C przy XYZ/powtórnym Z, planowanie 300 mm/s,
M220=150%, ACCEL=3000 i granice Z299/Z300.

Pozostały odbiór fizyczny zmienionego homingu, pomiar timingu przy dużej
prędkości/pełnym obciążeniu i dokładności czujników oraz pełne procedury
M03/M07/M08. Nastawa 2 us i PASS FILEOUTPUT nie są pomiarem 300 mm/s na MCU.
Inventure pozostaje osobnym projektem F207; jego geometria/pliki nie są tu instalowane.
