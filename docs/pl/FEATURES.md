# R16 — obsługa normalna i odbiór

[English](../en/FEATURES.md)

R16 porządkuje potwierdzoną przez operatora termikę/wentylatory, XYZ, ekstruder,
OLED i łączność. Wcześniejsze źródła R15.7 nadal zawierały testowy zakres Z30,
220C przy kontakcie i bramkę deklaracji prześwitu na 60 sekund. R16 usuwa te
ograniczenia normalnej obsługi przez jawną, odwracalną migrację konfiguracji.
Wcześniejsze wyniki PASS programowe nie stanowiły pomiaru osiągów sprzętu.

| Funkcja | Właściciel / obsługa normalna | Potwierdzenie |
|---|---|---|
| Grzanie, PID i SAVE_CONFIG | Natywny Klipper; grupa Klipper | Relacja operatora + testy właścicieli i zachowania PID |
| Wentylatory hotendu/modelu | heater_fan / fan, suwaki Fluidd i menu Klipper | Relacja operatora + natywni właściciele |
| Chłodzenie bez hosta/awaryjne | MCU R14.5: termostat hotendu, model OFF; błędny stan — chłodzenie ochronne | Dotychczasowe 52 przypadki C i relacja operatora; polityka MCU zachowana |
| RGB i buzzer | Dotychczasowy obserwator OEM i output_pin | Relacja operatora; właściciele zachowani |
| Przygaszanie/wygaszanie/wybudzanie | Dotychczasowy kontroler i księżyc OEM | Regresje hosta; wybudzenie ekranu nie porusza drukarką |
| Rozłączenie/restart/waiting OLED | Dotychczasowa dzierżawa MCU i lifecycle hosta | Testy startu/guard oraz relacja operatora |
| XYZ i skalibrowany E | Natywny planner Cartesian; obsługa Klipper | Relacja operatora; kalibracja ekstrudera zachowana |
| Homing | Natywny G28/probe; punkt M300, minimum 180C i końcowe 5 mm | Nowe testy jednostkowe i rzeczywisty Klippy FILEOUTPUT; odbiór fizyczny nowego adaptera |
| Z400/Z800 | ID3 przed konfiguracją, wspólna skala natywnego Z/M07 | 1792 przypadki C i syntetyczne HW04/HW05 w rzeczywistym Klippy |
| Procedury OEM M03/M07/M08 | Service / Tests oraz TEST M300 | Do dalszej walidacji procesów; test grzania/XYZ nie zatwierdza całej procedury |

## Podział menu i Fluidd

Pierwszym ekranem pozostaje natywny stan Klippera. Klik otwiera Klipper /
Zortrax M300 / Service / Tests. Back jest pierwszy; zachowano ograniczone
przewijanie i kierunek pokrętła. Stałe wiersze tytułu/wersji nie zabierają menu.

Klipper zawiera homing, ruch, temperatury, natywne wentylatory, PID oraz stan
wydruku/pauzę/wznowienie. Zortrax M300 zawiera ustawienia OEM i informacje.
Service / Tests zawiera diagnostykę i niedokończone procedury OEM: filament,
kalibrację oraz widoki sprawdzanego druku/SD. Test temperatury lub ręcznego
wytłaczania nie zatwierdza wszystkich etapów tych automatów.

Po instalacji i starcie hosta wykonaj setup_fluidd.py --apply. Skrypt ustawia
przez Moonrakera grupy Klipper, ZORTRAX M300 i TEST M300. Zachowuje pozostałe
ustawienia i widoczność makr, zapisuje kopię do cofnięcia. Może być potrzebne
odświeżenie przeglądarki. Sam komentarz w cfg nie tworzy kategorii Fluidd.

## Ruch i timing

Wspólna migracja instalatora i CI ustawia STEP **0.000002 s (2 us)** dla XYZ/E,
profil XY co najmniej 300 mm/s, Z 25 mm/s i przyspieszenie Z 50 mm/s².
Zachowuje przyspieszenie XY, ustawienia naroży, skalibrowane rotation_distance
E, PID-y, definicje czujników i zapisane dane kalibracji. Tylko rozpoznane
tymczasowe Zmax=30 zmienia na użytkowe Zmax=300; inne świadome wartości
geometrii pozostają. Nie ma odrzucania M220=150% ani dodatkowego limitera G1.
Natywne SET_VELOCITY_LIMIT pozostaje dostępne.

Oficjalna konfiguracja Zortrax Marlin M300_v5, commit
12b32a9a2eb69c070f69a6cb4dfbd1a3fa74da22: XY=300, Z=25 mm/s,
maksymalne przyspieszenia 3000/3000/50/4000 i domyślne przyspieszenie
wydruku/przejazdów 700 mm/s². Mechaniczny Zmax w Marlinie wynosi 312 mm;
port zastępuje testowe 30 mm użytkową wysokością 300 mm, nie tym większym przejazdem.
Źródło: https://github.com/Zortrax3D/MarlinConfigurationsZortraxM200/blob/12b32a9a2eb69c070f69a6cb4dfbd1a3fa74da22/config/examples/Zortrax/M300_v5/Configuration.h

Przy 640 krokach/mm XY prędkość 300 mm/s wymaga 192000 impulsów STEP/s na
jednej osi; przekątna 300 mm/s to około 271529 impulsów/s łącznie. Nastawa
2 us nie jest pomiarem wydajności całego harmonogramu MCU. FILEOUTPUT sprawdza
rzeczywisty planner przy 300, M220=150 i ACCEL=3000, również z poleceniami
grzałek, wentylatorów i OLED; nie wykonuje tych zdarzeń na F103.

## Odbiór nowej iteracji na drukarce

1. Sprawdź STATUS, ZORTRAX_HARDWARE_STATUS i ZORTRAX_MOTION_STATUS: wariant
   fabryczny, tryb native i temperaturę bazowania 180C.
2. Sprawdź XY bez grzania, następnie Z i pełne XYZ. Powtórz bazowanie Z:
   końcowy odstęp ma pozostawać 5 mm od świeżo ustalonego kontaktu, bez
   sumowania opuszczenia i bez żądania Z304.
3. Użyj natywnego grzania/wentylatorów we Fluidd; porównaj RGB, chłodzenie
   lokalne i odzyskiwanie połączenia z potwierdzonym zachowaniem. Natywne
   verify_heater i ochrona MCU pozostają aktywne.
4. Przy fizycznym prześwicie i zbazowanych XY wykonaj TEST_M300_XY SPEED=200,
   później SPEED=250 i SPEED=300. Test porusza tylko XY: nie grzeje, nie bazuje,
   nie rusza Z/E i nie zmienia nastaw prędkości/przyspieszeń. Przed odbiorem
   300 mm/s sprawdź ruch, gubienie kroków i timing przy rzeczywistym obciążeniu.
5. Sprawdź przygaszanie, księżyc/wygaszenie, wybudzenie i nawigację grup.
   M03/M07/M08 odbieramy osobno w TEST podczas dopracowywania procesów.

Wydanie obejmuje 112 testów hosta, 8 kontraktów repozytorium, 6720 przypadków
STEP, 52 chłodzenia, 1792 dekodera fabrycznego, testy startu/timerów i 13
scenariuszy rzeczywistego Klippy FILEOUTPUT. CI nie programuje ani nie porusza drukarki.
