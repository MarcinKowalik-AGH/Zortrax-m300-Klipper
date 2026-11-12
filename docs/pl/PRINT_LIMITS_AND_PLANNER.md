# Planer ruchu oraz rzeczywiste ograniczenia prędkości druku

[Spis dokumentacji](../../README_PL.md) · [Obsługa](USER_GUIDE.md) · [Menu OLED](OLED_MENU_REFERENCE.md) · [Ilustrowane funkcje](OLED_FUNCTIONS.md) · [Parametry](TECHNICAL_REFERENCE.md)

> Dokumentacja dla **M300 Classic**, wydanie **1.0.0-rc.1**. Historyczne ilustracje mają jawny punkt odniesienia beta.20. Nie dotyczy M300 Plus, M300 Dual ani Inventure.


## 1. Podział odpowiedzialności

Klipper na Orange Pi interpretuje G-code, przygotowuje ruchy, analizuje kolejne odcinki (*look-ahead*) oraz oblicza przebieg prędkości z przyspieszeniem i ograniczeniami kinematyki. MCU wykonuje wcześniej zaplanowane w czasie impulsy STEP i czynności sprzętowe. Szybkość odświeżania Fluidd nie wyznacza częstotliwości wykonywania kroków.

Port **nie zastępuje całego planera Klippera nowym planerem Zortrax**. Dodaje konfigurację i procedury M300 oraz kwalifikowane użycie sprzętowych timerów dla odpowiednich bloków X/Y. Obsługa homingu, styku, OLED i zasobów jest częścią integracji, ale nie unieważnia natywnych limitów Klippera.

Źródła: [Kinematics](https://www.klipper3d.org/Kinematics.html), [Code overview](https://www.klipper3d.org/Code_Overview.html), [przypięty toolhead.py](https://github.com/Klipper3d/klipper/blob/ee2c6fb6b00b2b5d097ef70d0868df7d74943b51/klippy/toolhead.py), [konfiguracja M300](../../host/config/m300_classic_base.cfg).

## 2. Co oznaczają 300 mm/s i 700 mm/s²

W profilu bazowym `max_velocity=300`, `max_accel=700`, `square_corner_velocity=2`. To granice planowania ruchu, nie gwarancja stałej prędkości każdej ścieżki. Krótki odcinek może skończyć się zanim maszyna osiągnie prędkość zadaną. Zakręty, zmiana kierunku, dopuszczalna prędkość narożna, ograniczenia Z/E i geometria modelu obniżają rzeczywistą prędkość.

Dla prostego przykładu od spoczynku do 300 mm/s przy 700 mm/s²:

```text
s_przyspieszania = v² / (2a) = 300² / (2 × 700) = 64,29 mm
przyspieszanie + symetryczne hamowanie = około 128,57 mm
```

To obliczenie dla jednego odcinka bez prędkości wejściowej/wyjściowej, nie symulacja konkretnego G-code. Look-ahead może utrzymywać prędkość między zgodnymi segmentami; zmiana kierunku może wymusić jej ograniczenie.

Przy 640 impulsach STEP/mm dla X/Y, prędkość osi 300 mm/s odpowiada 192000 impulsów/s na tej osi. Przy przekątnej 300 mm/s składowe osi zależą od kierunku; nie należy liczyć automatycznie po 300 mm/s na obu osiach. Impuls 2 µs i ten rachunek nie stanowią dowodu, że wszystkie kombinacje prędkości, segmentów i obciążenia są dopuszczalne.

## 3. Ekstruder i hotend: główne praktyczne ograniczenie szybkiej ekstruzji

**Dla długich przejazdów z odkładaniem materiału istotnym, często dominującym ograniczeniem jest wydajność układu ekstruder–hotend–dysza.** Silnik musi podać filament, a hotend stopić go przy wymaganym przepływie i ciśnieniu. Ruch jałowy 300 mm/s nie potwierdza możliwości drukowania 300 mm/s z każdą warstwą i dyszą.

Nie twierdzimy, że ekstruzja jest jedynym możliwym ograniczeniem. Przy krótkich ścieżkach dominować może przyspieszenie; przy ostrych zmianach kierunku — jakość i drgania; przy problemie komunikacji lub zbyt złożonym strumieniu — zdolność przetwarzania. Stan mechaniki, masa głowicy, chłodzenie modelu i przyczepność pierwszej warstwy nadal mają znaczenie.

W repozytorium nie ma pomiaru ustalającego jeden uniwersalny `max_volumetric_speed` dla fabrycznego M300 i wszystkich materiałów. Wartości w przykładzie poniżej są **rachunkiem zapotrzebowania**, nie wynikami testu przepływu hotendu.

## 4. Rachunek przepływu

Praktyczne przybliżenie:

```text
Q [mm³/s] ≈ szerokość ścieżki [mm] × wysokość warstwy [mm] × prędkość [mm/s]
v_max ≈ zmierzony stabilny Q_max / (szerokość × wysokość)
```

Slicer może stosować dokładniejszy model przekroju ścieżki. Ilustracja dla szerokości 0,45 mm i warstwy 0,20 mm:

| Prędkość | Zapotrzebowanie Q |
|---:|---:|
| 50 mm/s | 4,5 mm³/s |
| 100 mm/s | 9,0 mm³/s |
| 150 mm/s | 13,5 mm³/s |
| 200 mm/s | 18,0 mm³/s |
| 300 mm/s | 27,0 mm³/s |

Gdyby **zmierzony na danym zestawie** stabilny limit wyniósł 10 mm³/s, z powyższego przybliżenia otrzymalibyśmy około 111 mm/s. Liczba 10 jest przykładem, **nie deklarowanym limitem M300**. Dla innej warstwy, szerokości i materiału wynik będzie inny.

Pole `max_extrude_only_velocity: 45` dotyczy mm/s ruchu filamentu przy samej ekstruzji. Nie jest prędkością drukowania XY ani limitem 45 mm³/s. Także mnożnik Speed 150% nie oznacza, że slicer ponownie przeliczył bezpieczny przepływ dla materiału. Zmiana parametru w Fluidd nie zastępuje kalibracji.

## 5. Jak dobierać prędkość bez zgadywania możliwości hotendu

Najpierw doprowadź do powtarzalnej pierwszej warstwy, właściwego podawania i stabilnej temperatury. Następnie testuj przepływ dla konkretnego materiału, temperatury i dyszy, obserwując niedoekstruzję, ślizganie/klikanie podajnika, odchylenia masy i jakość ścieżki. Ustaw w slicerze limit przepływu z zapasem względem zaobserwowanej granicy. Nie kompensuj każdej utraty podawania podwyższaniem temperatury ani docisku.

Osobno dobierz prędkości ścian zewnętrznych, mostów i pierwszej warstwy. Kalibracja pressure advance i input shaping to oddzielne czynności, zależne od sprzętu i pomiaru. Samo występowanie suwaka Pressure Advance we Fluidd nie dowodzi dostrojenia; na dostarczonym zrzucie widoczna jest wartość 0. Nie wpisuj wartości z innej maszyny jako uniwersalnej.

## 6. Udokumentowane testy ruchu a realny druk

Historyczny opis projektu dokumentuje suchy przebieg HW05 przy 750000 baud, 6054 ruchy, w tym cztery segmentowane przekątne zadane na 400 mm/s, oraz próbkę łącza 201,6 s bez retransmitowanych i odrzuconych bajtów. To dowód określonego testu ruchu/łącza, **nie kwalifikacja 400 mm/s z ekstruzją** i nie zmiana bazowego limitu 300 mm/s.

Testy CI sprawdzają modele kroków, kompilację ARM, rzeczywisty parser/planer Klippy w trybie FILEOUTPUT i zabezpieczenia. Nie mierzą temperatury filamentu, siły podawania, drgań mechaniki ani jakości wydrukowanej części. Zakres wyników: [BUILD](../en/BUILD.md), [opis projektu](../../README.md), [kontrola dokumentacji](DOCUMENTATION_CHECK.md).

## 7. UI i łącze nie powinny być „przyspieszane globalnie”

W beta.16/17 przyspieszono jedynie dostarczanie zmian zaznaczenia OLED do przeglądarki. Temperatura, wykresy i zwykły status zachowały dotychczasowy rytm. Fizyczny OLED, UART, SPI i kod ruchu nie były zmieniane przez tę poprawkę frontendu.

Odpowiednio działające i zakwalifikowane łącze umożliwia przesyłanie zaplanowanych zdarzeń z wyprzedzeniem. Nie jest jednak prawdą, że przepustowość i jakość UART nigdy nie mają znaczenia: błędy, retransmisje i niewydolna konfiguracja mogą doprowadzić do przestojów lub shutdown. Rozróżniaj diagnostykę transportu od oceny przepływu materiału.
