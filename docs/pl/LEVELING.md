# Poziomowanie M07 — R16.3, odbiór na drukarce

[Instalacja](INSTALL.md) · [English](../en/LEVELING.md)

R16.3 łączy odtworzony algorytm M300 z natywnym ruchem R16 oraz jednym widokiem
OLED/Fluidd. Wymaga hosta R16.3; MCU R14.5 pozostaje zgodny. Testy programowe
nie zastępują odbioru tej procedury na fizycznej drukarce.

## Przyczyna zgłoszonych problemów

`PROBE_ACCURACY` jest osobnym poleceniem Klippera. Nie uruchamia właściciela
M07 ani jego ekranów. Przy `position_min=0` i `probe.z_offset=0` jego poszukiwanie
może zakończyć się na Z0 tuż przed próbkowaniem styku. Następne polecenie może
już wykryć styk aktywny przed ruchem. Jest to odtworzony w modelu przypadek;
sam komunikat nie rozstrzyga sprawności kontaktu i okablowania.

W R16.2 wykonawca i wspólny presenter procedur pomijały uruchomienie w trybie
native. M07 zależał też od flagi kwalifikacji starego M02. R16.3 uruchamia M07
na własnym profilu, zachowując osobną blokadę niedokończonego M02/M03/M08.

## Jeden start i jeden przebieg

Z menu OLED: **Service / Tests → TEST: platform calibration**.
We Fluidd: **TEST M300 → TEST_ZORTRAX_LEVEL**, albo w konsoli:

```gcode
TEST_ZORTRAX_LEVEL
```

Równoważne polecenie właściciela:

```gcode
ZORTRAX_PROCEDURE_START OP=LEVEL TEMP=180
```

Kolejność: przygotowanie dyszy i metalowych miejsc kontaktu → potwierdzenie
operatora → utrzymanie dyszy przy 180°C → bazowanie XYZ → pomiar narożników
0, 1, 4, 3 → instrukcje tylnych i przedniej śruby z kierunkiem i liczbą obrotów
→ potwierdzenia i ponowne pomiary → pomiar środka → przegląd wyniku → osobne
potwierdzenie zapisu. Każdy punkt ma trzy próbki; dopuszczalny rozrzut 0,05 mm.
Środek jest raportowany operatorowi. Algorytm, współczynnik 0,51, zaokrąglanie
do ćwierci obrotu i skala Z400/Z800 są wspólne z odtworzonym M07.

OLED automatycznie otwiera bieżącą procedurę również po starcie z konsoli.
Ikony pochodzą z atlasu OEM: przygotowanie, nagrzewanie, pomiar, odpowiednia
śruba/kierunek regulacji, wynik i anulowanie. Fluidd pokazuje ten sam etap i
te same informacje. Potwierdzenie dotyczy wyświetlonej sesji i fazy; stary lub
podwójny klik nie uruchamia następnego etapu.

## Zakres sondowania i zapis

Profil testowy: `safe_z=5`, `probe_search_margin=1`, `approach_distance=6`,
`release_distance=1`, temperatura 180°C. Po własnym G28, przy znanej pozycji,
M07 przesuwa wyłącznie swój układ pomiarowy o 1 mm. Pozwala to szukać styku
do 1 mm poniżej odniesienia kontaktu, nadal przez natywne zatrzymanie PC7.
Wyniki są przeliczane z powrotem. Zwykłe `position_min=0`, Z315 oraz limity XY
pozostają bez zmian; podczas sesji ruch z innych poleceń jest zablokowany.

Po zakończeniu lub spokojnym anulowaniu wraca zwykły układ współrzędnych
i natywni właściciele poleceń. Awaria lub przerwanie podczas ruchu powoduje
shutdown; po restarcie konieczne jest ponowne bazowanie. Nie zapisuje się
częściowych wyników. Zapis obejmuje pełną obserwację i potwierdzenia w NVM
hosta; nie zmienia PID, kalibracji E, `probe.z_offset` ani nie tworzy bed_mesh.

Jeżeli po poprzednim sondowaniu kontakt pozostaje aktywny przy zbazowanym Z,
odsuń stół o 2 mm dodatniego Z i sprawdź `QUERY_PROBE` przed startem M07.
Przy aktywnym styku M07 odmówi startu bez ruchu. Odmowa lub brak kontaktu
w granicach poszukiwania wymaga sprawdzenia przyczyny, nie zwiększania zakresu.

## Co potwierdzić fizycznie

Odbierz kolejno: widok przygotowania na OLED i Fluidd, grzanie 180°C, własne
bazowanie, poprawne miejsca kontaktu, trzy próbki na punkt, wskazanie właściwej
śruby i zgodność kierunku obrotu, oczekiwanie na potwierdzenie, ponowny pomiar,
przegląd i zapis. Potwierdź odsunięcie oraz zwykłe współrzędne po zakończeniu.
Pełny odbiór obejmuje również anulowanie i późniejszą pierwszą warstwę.

R16.3.1 stosuje nazwy poleceń bez cyfr w środku, ponieważ natywny parser rozcinał stary segment M300. Na zainstalowanym R16.3 polecenie `ZORTRAX_PROCEDURE_START OP=LEVEL TEMP=180` już uruchamia ten sam M07. Poprawka makr nie wymaga nowego MCU.
