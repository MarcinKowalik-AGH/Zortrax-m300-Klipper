# M300 — aktualna obsługa START, PAUSE, RESUME, CANCEL i END

[Instrukcja główna](../../README_PL.md) · [Rejestr odbiorów](ACCEPTANCE_REGISTER.md) · [Mesh](BED_MESH_AND_LEVELING.md)

**Kontroler w RC34.** [Kod kontrolera](../../host/klippy/extras/m300_print_control.py)
i [makra](../../host/config/m300_operations.cfg) określają kolejność startu
oraz parametry ruchu.

Opis starszego kontrolera `.29`, pojedynczej linii 40 mm i dawnych wartości
znajduje się w [archiwum](PRINT_CONTROL_LEGACY_R16_29.md). **Nie należy już
kopiować go jako aktualnej konfiguracji.**

## Aktualizacja działającej instalacji

Przy bezczynnej drukarce **Ready**, bez pauzy ani aktywnej procedury,
wyłącz cele grzania. Wykonaj na Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Polecenie aktualizuje hosta Klippera. [Instrukcja aktualizacji](INSTALL.md)
opisuje sprawdzenie MCU oraz osobne polecenie Fluidd dla istniejącej witryny
na porcie 4480.

## Jedno wywołanie START z OrcaSlicera

```gcode
START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single] MESH=AUTO
```

Końcowy G-code:

```gcode
END_PRINT
```

Nie powielaj w profilu slicera dodatkowego G28, grzania i czterech linii, gdy
wywołujesz wspólny START_PRINT. Dla świadomego wymagania konkretnej siatki użyj
`MESH=m300_pads`; dla świadomego druku bez kompensacji `MESH=NONE`.

## Kolejność START_PRINT

1. Sprawdzenie temperatur, dostępności profilu i braku konkurencyjnej procedury.
2. Przygotowanie pliku oraz nagrzewanie dyszy i stołu. Włączone Full platform
   preheating dodaje ustawioną stabilizację stołu, domyślnie 60 s.
3. Po osiągnięciu temperatur i stabilizacji Klipper cofa filament o 10 mm
   i czeka na zakończenie ruchu przed kontaktem Z.
4. Wspólne bazowanie M300. Bazowanie Z korzysta z procedury kontaktowej
   i minimum 180°C, z zachowaniem wyższego celu drukowania.
5. Po bazowaniu Klipper aktywuje zapamiętany profil płyty. Przy pierwszym wyborze
   `AUTO` może użyć domyślnego `m300_pads` albo jedynego zapisanego profilu.
   Brak wymaganego profilu lub niejednoznaczny wybór zatrzymuje start przed ruchem.
   Jawną nieistniejącą nazwę odrzuca przed rozpoczęciem operacji.
6. Klipper dojeżdża do początku czyszczenia na wysokości bezpiecznej,
   podaje 6 mm filamentu i przechodzi na wysokość czyszczenia.
7. Wykonuje cztery długie odcinki z ekstruzją, dwa w osi Y i dwa w osi X
   (2Y + 2X). Na końcach par są przejścia o 0,5 mm bez ekstruzji. Pierwszy odcinek X
   rusza z końca powrotnego odcinka Y. Wszystkie odcinki pracują na jednej
   zadanej wysokości Z.
   Po ostatnim odcinku Klipper odsuwa Z, odtwarza stan parsera i przekazuje
   wykonanie do właściwego pliku modelu.

Natywny G-code stosuje wybraną kompensację mesh podczas czyszczenia. Stała
zadana wysokość pozwala siatce nadal korygować fizyczne położenie Z.
Rozruch używa G90, M83 i mnożników M220/M221 = 100%. Klipper odtwarza
poprzednie tryby parsera także przy przerwaniu. Cykl cofnięcia i podania
10/6 mm należy do `START_PRINT`. Samodzielne Home Z i Bed Mesh cofają gorący filament o 10 mm i po poprawnym zakończeniu podają z powrotem 10 mm.

### Domyślna geometria w kodzie, nie nakaz nadpisania własnych nastaw

| Parametr | Wartość domyślna i znaczenie |
|---|---|
| `purge_length` | 250 mm; odniesienie do długości i obliczenia dawki |
| `purge_filament` | `20 × purge_length / 350`, czyli około 14,286 mm filamentu dla 250 mm odniesienia |
| `purge_height` | 0,28 mm |
| `PURGE` w komendzie | Żądana długość, dalej ograniczana do rzeczywistego pola osi |
| Początek pary Y | `X_min+3`, `Y_min+10`; powrót z przesunięciem X o 0,5 mm |
| Początek pary X | `X_min+3,5`, `Y_min+10` na końcu drugiego odcinka Y; powrót z przesunięciem Y o −0,5 mm |
| Daleka krawędź | Nie bliżej niż 5 mm od rzeczywistego maksimum osi |
| Bezpieczna wysokość Z | 5 mm przy dojeździe do początku i po ostatnim odcinku |
| Cofnięcie i podanie przed czyszczeniem | 10 mm cofnięcia i 6 mm podania z prędkością `retract_speed`, domyślnie 2 mm/s |

Dawka jest proporcjonalna do **faktycznej długości każdego odcinka** po
ograniczeniu do pola ruchu. Przy domyślnych granicach i `purge_length=250`
odcinki Y mają po 260 mm, a odcinki X po 250 mm. Zmniejszone pole ruchu lub
własne nastawy mogą skrócić odcinki.

## Pauza, wznowienie, zakończenie

| Wywołanie | Zachowanie |
|---|---|
| PAUSE / M25 / M601 / przycisk Fluidd lub OLED | Dokończenie zaplanowanych ruchów, zapamiętanie pozycji i pozostawienie głowicy w bieżącym XY. Stół opuszcza się domyślnie o 5 mm, silniki trzymają pozycję. |
| RESUME | Przywrócenie celów, dogrzanie, bezpieczny powrót i odtworzenie stanu tego samego pliku; brak automatycznego G28 nad modelem |
| CANCEL_PRINT | Przerwanie operacji i wyłączenie celów grzania; zamknięcie zatrzymanego pliku i usunięcie pauzy **nie czekają na parkowanie**; parkowanie jest etapem warunkowym |
| END_PRINT | Po ostatnim ruchu modelu stół opuszcza się o 300 mm lub do limitu Z. Po zakończeniu tego ruchu głowica parkuje w prawym tylnym rogu przy dostatecznym prześwicie. Następuje wyłączenie grzania i nawiewu modelu, odczyt końca pliku i komunikat PRINTING DONE. |
| M600 / M300_CHANGE | Po odsunięciu stołu głowica parkuje w miejscu serwisowym. Przy wymianie wybranej podczas zwykłej pauzy dojeżdża tam na już osiągniętej wysokości. Po wymianie potwierdź wypływ i wybierz RESUME. |

W pauzie poczekaj, aż drukarka zakończy ruch. Przy zmianie koloru poczekaj na pytanie o wypływ. W panelu **Narzędzie** we Fluidd lub w zakładce **Device** w OrcaSlicerze ustaw długość i prędkość filamentu. **Extrude** podaje go, a **Retract** cofa. Możesz powtarzać ruchy przed potwierdzeniem wypływu. Wydruk wznowisz osobno przyciskiem **Resume**.

Po zmianie materiału zarówno temperatura zmierzona, jak i zadana muszą osiągać próg ekstruzji. Przy dyszy 230°C i celu 150°C wybierz **Reheat to check flow** na OLED lub **Resume** we Fluidd. Po dogrzaniu drukarka pozostanie w pauzie. Podaj materiał, sprawdź wypływ i wybierz **Confirm material flow** lub wpisz `FILAMENT_READY`. Każde przyjęte ręczne cofnięcie po potwierdzeniu ponawia pytanie o wypływ. Po kolejnym podaniu potwierdź wypływ ponownie, a następnie wybierz **Resume**.

Domyślny narożnik to X300 Y305. Ruch stołu jest względny i ograniczony do `position_max` osi Z. Przy Z250 i limicie Z300 stół może zjechać jeszcze o 50 mm. Jeżeli dostępny ruch jest mniejszy od `min_park_clearance` (domyślnie 5 mm), głowica pozostaje w XY. Gorąca retrakcja ma domyślnie 2 mm.
Pauza zachowuje stół i pozycję; domyślnie po 600 s obniża wyższy cel dyszy do
150°C, a po 1800 s wyłącza jej cel. To parametry konfigurowalne, nie obietnica
nieskończonego bezpiecznego pozostawiania rozgrzanej drukarki bez nadzoru.

Wyłączenie silników, zmiana pliku, restart lub utrata pozycji unieważniają
bezpieczne wznowienie. Nie odblokowuj go przez ręczne nadpisywanie PAUSE_STATE.
Zabezpieczenia grzania, autonomiczne chłodzenie MCU i sygnalizacja błędów
pozostają niezależne od wyłączenia nawiewu modelu.

## Światło podczas druku

W trybie Dynamic światło jest białe od zakończenia `START_PRINT` dla
bieżącego pliku SD. Zmiany temperatur, w tym przejście od raftu do modelu
w tym samym pliku, nie zmieniają koloru na czerwony. Sygnały
przygotowania, pauzy i błędów wynikają z osobnych stanów pracy drukarki.
Wybór Disabled i ustawiona jasność obowiązują zgodnie z polityką światła.
[Kolory i ustawienia](../en/SETTINGS_INFORMATION.md).

## Kontrola i odbiór

Te polecenia odczytu pomagają ustalić przyczynę zmiany koloru lub ruchu Z:

```gcode
PRINT_CONTROL_STATUS
ZORTRAX_MAINTENANCE_STATUS
ZORTRAX_ERROR_STATUS
BED_MESH_OUTPUT
```

Sprawdź rewizję `0.13.16.44-FLOW-CHECK`, fazę i aktywną siatkę. W RC17
`model_print_ready: true` potwierdza zakończenie czyszczenia w bieżącym
pliku SD. Rewizja
`0.13.16.38-PRINT-DRAIN-XY-PURGE` miała dodatkowe odsunięcie do Z5 pomiędzy
parami Y i X. Od `0.13.16.39-PRINT-PREP` przejście Y→X utrzymuje zadaną
wysokość czyszczenia, domyślnie Z0,28. Aktywna siatka nadal koryguje
fizyczne Z w zależności od XY. `BED_MESH_OUTPUT` odczytuje siatkę bez
sondowania, a kolorowy podgląd zapisanego profilu we Fluidd sam nie potwierdza
aktywnej kompensacji.

Przy czerwonym świetle odczytaj `status_led.state` i `status_led.rgb` z
`ZORTRAX_MAINTENANCE_STATUS`. Stan `HEATING` oznacza grzanie, a
`ERROR` wskazuje sygnalizację błędu. `ZORTRAX_ERROR_STATUS` pokazuje
bieżące zdarzenie i stan raportowany przez MCU.
[Rejestr prób](ACCEPTANCE_REGISTER.md).

Programowe testy i udana kompilacja nie są odbiorem ruchów ani pierwszej warstwy
na Twojej drukarce. Wpis bez potwierdzenia użytkownika pozostaje oczekujący.
Nie przypisujemy tu nowych wyników testów sprzętowych.


## Ujemne Z po transformacji mesh — kwalifikowany egzemplarz

Dla zgłoszonego pierwszego startu Z0,28 po korekcji -0,369086 dawało -0,089086 mm.
[Dodatek beta.24](RELEASE_v1.0.0-beta.24.md) opisuje jawny profil position_min=-0,5,
safe_z=5, approach_distance=6,5 oraz homing clearance=2. Nie usuwa mesh i nie
przenosi purge. Zwykła aktualizacja nie narzuca ujemnego zakresu innym drukarkom.
