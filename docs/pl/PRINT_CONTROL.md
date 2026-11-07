# Druk M300: Start, pauza, wymiana filamentu, wznowienie i End

Zmiana hosta `0.13.16.28-NATIVE-PRINT-CONTROL`. Obowiązuje natywny Klipper
przypięty w projekcie do `ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`.
MCU pozostaje `0.13.14.18-OEM-ERRORS-UART8`; ta aktualizacja nie wymaga
ponownego wgrywania firmware do drukarki.

## Instalacja

Gdy drukarka nie drukuje, na Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --organize-config
```

Instalator dodaje `[m300_print_control]` i brakujące makra. Istniejące własne
makra `START_PRINT`/`END_PRINT` pozostają zachowane; wtedy trzeba świadomie
włączyć do nich `ZORTRAX_PRINT_START`/`ZORTRAX_PRINT_END` zamiast powielać ruchy.
Dotychczasowe pliki G-code z własnym startem nadal wykonują swoje polecenia.

## Kolejność pracy

| Wywołanie | Działanie |
|---|---|
| `PAUSE`, `M601`, `M25`, przycisk Fluidd, przytrzymanie OLED 10 s | Natywny zapis `PAUSE_STATE`, zatrzymanie odczytu pliku i opróżnienie kolejki. Retrakcja 2 mm tylko przy gorącej dyszy, odsunięcie stołu o Z+5 mm i parkowanie X300 Y305. |
| Pauza 10 minut | Dysza przechodzi do 150°C, jeżeli jej cel jest wyższy. Stół zachowuje temperaturę wydruku; silniki nie są zwalniane przez bezczynność. |
| Pauza 30 minut | Cel dyszy 0°C. Stół i pozycja pozostają utrzymane. |
| `RESUME` | Przywrócenie pierwotnych celów dyszy i stołu, oczekiwanie na stabilizację, powrót XY na podniesionym Z, następnie powrót Z, odtworzenie retrakcji i natywnego stanu parsera, wznowienie tego samego pliku. |
| `M600` / `ZORTRAX_CHANGE` | Najpierw wspólna pauza i parkowanie, potem dotychczasowa procedura CHANGE: 110 mm wycofania, potwierdzenie włożenia i 150 mm ładowania. Zachowane tokeny, fazy i ograniczenia transportu. |
| `FILAMENT_READY` | Po udanej wymianie i sprawdzeniu wypływu odblokowuje osobne `RESUME`. Wymiana sama nie wznawia pliku. Jeśli dysza ostygła, `RESUME` najpierw ją dogrzewa i zatrzymuje się przy potwierdzeniu wypływu. |
| `END_PRINT` | Opróżnienie kolejki, bezpieczne parkowanie, grzałki OFF i natywne `M107`. Natywny czytnik dochodzi do rzeczywistego EOF; zachowane zakończenie i ponowny wydruk. |
| `CANCEL_PRINT` | Unieważnienie oczekujących operacji, zakończenie aktywnego transportu filamentu, grzałki OFF, zamknięcie pliku po zatrzymaniu czytnika, nawiew OFF i parkowanie przy ważnej pozycji. Anulowanie nie oznacza ukończenia wydruku. |

Na M300 **Z+ odsuwa stół od dyszy**. Przy końcu zakresu Z, gdy zabraknie
pełnych 5 mm prześwitu, ruch XY jest pomijany; wymiana filamentu wymaga
bezpiecznego parkowania. Skonfigurowany punkt poza zakresem osi nie jest
po cichu przesuwany: pauza pozostaje w miejscu i pokazuje przyczynę.

Podczas pauzy blokowane są ruchy ręczne, sondowanie, zmiana siatki, bazowanie,
przestawienie współrzędnych i obejście wznowienia przez `M24`. Wyłączenie
silników, zmiana pliku, nadpisanie `PAUSE_STATE`, zmiana geometrii/siatki lub
restart unieważniają możliwość wznowienia. Nie ma automatycznego G28 w pauzie.
Anulowanie trwającego natywnego homingu zachowuje istniejące zatrzymanie
Klippera — po przerwanym bazowaniu nie zakłada się ważnej pozycji.

## OrcaSlicer

W startowym G-code drukarki użyj jednej procedury:

```gcode
START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single]
```

W końcowym G-code:

```gcode
END_PRINT
```

Start nagrzewa oba elementy jednocześnie, wykonuje dotychczasowy natywny
homing M300 (minimum 180°C, zachowanie wyższego celu), ładuje **zapisaną**
siatkę `m300_pads` po homingu, a następnie wykonuje linię 40 mm z 3 mm
filamentu na wysokości 0,3 mm. Ruchy linii przechodzą przez natywny Bed Mesh.
M220/M221 dla tej linii wynoszą 100%, po niej przywracany jest poprzedni stan.
Nie wykonuje się 25 pomiarów przed każdym wydrukiem.

Brak profilu jest zgłaszany przed startem; nie tworzy się fikcyjnej siatki.
Świadome pominięcie kompensacji:

```gcode
START_PRINT EXTRUDER_TEMP=220 BED_TEMP=60 MESH=NONE
```

Geometria linii jest sprawdzana względem natywnych granic. Profil Orca może
mieć dodatkowe własne ruchy; usuń z jego startu/końca powielone bazowanie,
grzanie, parkowanie i linię rozruchową, jeżeli zastępujesz je tymi makrami.

## Parametry i odczyt

Sekcja trafia do `m300_services.cfg` przy porządkowaniu konfiguracji:

```ini
[m300_print_control]
park_x: 300
park_y: 305
pause_z_hop: 5
min_park_clearance: 5
park_speed: 100
z_lift_speed: 5
pause_retract: 2
retract_speed: 2
pause_standby_after: 600
pause_standby_temperature: 150
pause_heater_off_after: 1800
heat_timeout: 1800
move_timeout: 120
purge_length: 40
purge_filament: 3
purge_height: 0.3
```

`PRINT_CONTROL_STATUS` lub `PAUSE_TEMP_STATUS` pokazują fazę, pierwotne cele,
czas pauzy, wymóg potwierdzenia filamentu i ostatnią przyczynę odmowy.
Nie dodawaj drugiej sekcji, jeśli instalator już ją utworzył.

## Audyt zgodności

| Obszar | Wynik przeglądu |
|---|---|
| Odczyt pliku | Jeden natywny `virtual_sdcard`; brak nowego podajnika i ponownego uruchomienia silnika M02/M08. Stopień wykonania pliku ustala natywny czytnik. |
| Pauza i powrót | Natywny `pause_resume` jest właścicielem `PAUSE_STATE`. Zachowane tryby osi/E, przepływ i prędkość; powrót dopiero po dogrzaniu i sprawdzeniu tej samej sesji. |
| Start/End | Usunięta kolizja nazw ze starym M02 w trybie natywnym. Makra kierują do jednego właściciela procedur. |
| Models / SD / Z-code / reprint | Sprawdzany ten sam otwarty plik lub niezmienna kopia wykonawcza, pozycja pliku oraz metadane deskryptora. Zachowane kryterium rzeczywistego EOF i opróżnienia kolejki przed reprint. |
| Filament | Zachowana oryginalna maszyna stanów, limity E, tokeny i fazy; własny target wydruku przywracany także po standby/OFF. Potwierdzenie wypływu jest osobnym krokiem. |
| Bezczynność | Dotychczasowe skrypty pozostają w gałęzi poza chronioną pauzą; w pauzie/Start/End nie wyłączają stołu ani silników. |
| Bed Mesh | Zapisaną siatkę ładuje natywny menedżer profili. Linia startowa używa transformacji; podczas pauzy identyfikator i offset siatki są sprawdzane. Pomiar padów i oryginalna Autocalibration pozostają osobnymi funkcjami. |
| OLED / Fluidd | Wspólne komendy i stan; zachowane przytrzymania 10 s i potwierdzenia wyświetlonej klatki. Podczas przygotowania używany jest standardowy ekran temperatur/statusu, a po wymianie pojawia się potwierdzenie wypływu. |
| LED | Prawdziwa pauza i wznowienie: fiolet. Grzanie: czerwony. Bariera czytnika w Start/End nie udaje pauzy. Gotowość: zielony; praca: biały; rzeczywiste błędy: dotychczasowe RGB co 5 s. |
| Termika i MCU | Bez zmian ADC, PID, PWM, watchdogów, progów termostatu 50/45°C, lokalnych zatrzasków i jawnego ARM. Błąd wyłączenia grzałek żąda natywnego shutdown. |
| Napędy i komunikacja | Bez zmian MCU, timerów XY, próbkowania pokrętła, UART, OLED DMA i ograniczeń osi. Planowanie pozostaje natywne. |
| Instalacja | Nowy moduł i jego zależność geometrii w faktycznej paczce; listy bazowych sum obejmują poprzednią wersję. Zachowane migracje i wycofanie instalacji. |

Sprawdzenia obejmują testy hosta, istniejący zestaw regresji i rzeczywiste
procesy przypiętego Klippera w FILEOUTPUT, w tym pełny plik z wymianą
filamentu, anulowanie, import Z-code i reprint. W FILEOUTPUT modelowane są
temperatury/ADC, upływ czasu MCU i brak fizycznych potwierdzeń OLED. To
walidacja oprogramowania, **nie potwierdzenie ruchów ani temperatur na sprzęcie**.

Po instalacji pierwszą krótką próbę wykonaj bez modelu: sprawdź odsunięcie Z,
parkowanie, zatrzymanie pliku, cele w pauzie, powrót i anulowanie. Następnie
krótki wydruk z wymianą, widocznym wypływem i osobnym Resume. Nie powtarzaj
homingu nad wydrukiem po utracie pozycji. Raport zbiorczy testów buduje GitHub
Actions; jego wersja jest związana z SHA opublikowanego commitu.

Natywne zasady komend: [Klipper G-Codes](https://www.klipper3d.org/G-Codes.html).
