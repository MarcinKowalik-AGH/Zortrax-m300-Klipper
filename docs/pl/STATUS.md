# Stan i granica potwierdzenia

[English](../en/STATUS.md)

Ta baza obejmuje MCU R14.4 i host R15.6. Zachowuje natywnych właścicieli
Klippera i kontrakt osobnego bazowania R15.5. R15.6 naprawia regresję menu,
rejestrację akcji M11, kontrast startowy i komunikat usypiania OEM.
Nie instaluje nowych limitów prędkości, nastaw termiki ani geometrii.

Zwykły ekran stanu, transport, renderer i enkoder pozostają istniejącymi
implementacjami. Oryginalny księżyc ma 50×50 i jedną klatkę, deskryptor
0x0801D908 z M300 1.3.1. Napis Entering sleep mode jest pod 0x080266F0.
Procedura 0x08015FC8 wskazuje ten tekst i księżyc, następnie czeka 10 000 ticków
przed fizycznym sleep. Adaptacja obrazu ma jawne dziesięć sekund potwierdzonego
wyświetlania. Nie kopiuje grzania stołu do 70°C przy wybudzaniu ani innych
skutków dla urządzeń wykonawczych.

Publiczne testy obejmują 71 przypadków hosta, 8 kontraktów repozytorium,
6720 przypadków STEP, 52 przypadki chłodzenia autonomicznego, odrzucenia
chronionych pinów, guard snapshot, epoki startowe, terminy timerów oraz natywną
kontrolę grzania. Rzeczywisty Klippy FILEOUTPUT sprawdza pięć scenariuszy ze
świeżym słownikiem. To dowód programowy, nie pomiar UART, impulsów i temperatur.

Chłodzenie bez hosta pozostaje w MCU: hotend około 50°C ON / 45°C OFF,
nadmuch modelu OFF, błąd/próbka nieważna — chłodzenie awaryjne. Przy host
pozytywny target grzałki LUB temperatura powyżej progu uruchamia heater_fan.

W tej historycznej gałęzi ruchu nadal otwarte są:

- Skala i pełny zakres Z: przykład R15.5 ma rotation_distance=8 i testowe Zmax=30.
- Etapowe prędkości/przyspieszenia Z oraz deklaracja prześwitu.
- 220°C przy bazowaniu zamiast później żądanych 180°C.
- Bezwzględna kalibracja czujnika hotendu i timing przy jednoczesnym obciążeniu.
- Pełny odbiór wszystkich M03/M07/M08 na obecnej natywnej gałęzi; dawne audyty
  LAB same go nie potwierdzają.
- Przeniesienie rozwiązań na Inventure, czyli osobny F207/CoreXY.

tests/fixtures/printer_r15_5_test.cfg jest tylko wejściem syntetycznego CI.
Nie jest instalowany ani wydawany jako zamiennik printer.cfg. Aktualizacja
hosta zachowuje bieżące wartości użytkownika.
