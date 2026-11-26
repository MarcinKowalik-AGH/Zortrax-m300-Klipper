# Instrukcja codziennej obsługi

[Spis dokumentacji](../../README_PL.md) · [Obsługa](USER_GUIDE.md) · [Menu OLED](OLED_MENU_REFERENCE.md) · [Ilustrowane funkcje](OLED_FUNCTIONS.md) · [Parametry](TECHNICAL_REFERENCE.md)

> Dokumentacja dla **M300 Classic**, wydanie **1.0.4**. Historyczne ilustracje mają jawny punkt odniesienia beta.20. Nie dotyczy M300 Plus, M300 Dual ani Inventure.


## 1. Kontrola przed pracą

Sprawdź mocowanie płyty i hotendu, czystość dyszy oraz metalowych pól kontaktowych, prowadzenie filamentu, działanie chłodzenia i wolną przestrzeń ruchu. Rozgrzana dysza i stół mogą spowodować oparzenie; nie dotykaj ich podczas bazowania i pomiaru. Pierwsze próby po instalacji wykonuj pod nadzorem.

W Fluidd oczekuj stanu **Ready**. Do odczytu bez celowego ruchu i grzania służą:

```gcode
ZORTRAX_MCU_STATUS
ZORTRAX_LINK_STATUS
ZORTRAX_OLED_STATUS
ZORTRAX_HARDWARE_STATUS
PRINT_CONTROL_STATUS
M105
QUERY_ENDSTOPS
QUERY_PROBE
```

Stan krańcówek i PC7 musi odpowiadać fizycznej sytuacji. Sam napis Ready nie potwierdza wolnego toru ruchu, poprawności dyszy ani pomiaru temperatury zewnętrznym termometrem.

## 2. Fluidd i makra

[![Wydruk testu przepływu w zakładce Device OrcaSlicera](../img/m300-orcaslicer-fluidd-printing.png)](../img/m300-orcaslicer-fluidd-printing.png?raw=true)

*Zrzut operatora z 20.11.2026. Po lewej widać stan zadania i ruch, po prawej temperatury, OLED i konsolę. Na OLED i w konsoli widać nazwę siatki `m300_pads`.*

Dla nowej instalacji skorzystaj z [pełnego pakietu i procedury uruchomienia](FIRST_INSTALL.md). Działający port ma [osobną instrukcję aktualizacji](INSTALL.md). W przeglądarce i w zakładce Device używaj adresu Fluidd na porcie 4480. Makro `M300_MAIN_MENU` prowadzi do Models, Maintenance, Material, Settings i Information. Potwierdzenia z pokrętła i z Fluidd dotyczą tej samej operacji. Aby wrócić do jej okna, wybierz `M300_PROCEDURE`.

Grupa **ZORTRAX M300** zbiera funkcje specyficzne dla drukarki. **Klipper** zawiera m.in. START/END, CANCEL, BED_MESH i PID. Laboratoryjna grupa **TEST M300** nie jest częścią RC1. Odczyty daje `M300_DIAGNOSTICS`; OEM-owy test wentylatorów pozostaje w Maintenance. Jasność otwierają `M300_OLED_BRIGHTNESS` i `M300_LED_BRIGHTNESS`. Rozwijana strzałka przy makrze otwiera parametry; kliknięcie głównej części wykonuje wariant domyślny. [Pełny katalog](MACRO_REFERENCE.md).

W Settings osobno ustawiasz jasność OLED i LED (1–16) oraz czasy od ostatniego użycia pokrętła. Każdy z dwóch edytorów, **OLED dim time** i **OLED sleep time**, ma własny suwak 1–60 min. Skrócenie SLEEP poniżej wybranego DIM skraca efektywny DIM. Wydłużenie SLEEP przywraca zapamiętaną wartość DIM do wysokości nowego SLEEP. Zasada działa także podczas druku i pauzy. Po wyjściu zaznaczenie zostaje na edytowanej pozycji. [Zapis i odczyt nastaw z MCU](MCU_FIRMWARE_1.0.8.md).

<details>
<summary>Historyczny panel z 08.11.2026 — dlaczego część makr była „Uncategorized”</summary>

![Starszy panel makr przed poprawą grupowania](../img/macros_panel.png)

To stan wcześniejszej wersji, nie oczekiwany wygląd beta.20. `M300_HEAT_PLATFORM`, `M300_FULL_PLATFORM_PREHEAT` i START/END były wtedy widoczne jako nieprzypisane. Zrzut z 20 listopada na początku rozdziału pokazuje nowszy układ podczas druku. Zachowanie starych ustawień lokalnych lub pamięć przeglądarki może wymagać odświeżenia; nie usuwaj własnych kategorii bez sprawdzenia.

</details>

## 2a. Podgląd OLED i przyciski ×1/×2/×3

![Demonstracyjny układ beta.20: ×1](../img/fluidd_oled_beta20_x1.png)

*Render demonstracyjny w Chromium, z rzeczywistym CSS komponentu beta.20 i bitmapą OLED projektu. Nie jest zdjęciem sesji użytkownika.*

Po prawej pod HIDE znajdują się trzy przyciski. Wybrany jest podświetlony; zmiana wielkości nie wysyła poleceń do drukarki i nie steruje menu. OLED pozostaje wycentrowany względem całej karty, a wysokość całej kolumny przycisków odpowiada ×1. Gdy ×2/×3 nie mieści się w karcie, przewijaj tylko obraz. Wybór jest zapamiętywany osobno w przeglądarce. Kwadratowe piksele mają pierwszeństwo przed zachowaniem dokładnej wielkości CSS przy ułamkowym powiększeniu strony.

**HIDE/SHOW** dotyczy wyłącznie podglądu w Fluidd, nie wyłączenia fizycznego OLED. Strzałka przeładowania na górnym pasku Fluidd odświeża stronę także wewnątrz zakładki Device w OrcaSlicerze. [Pełny opis powiększenia](UPDATE_2026-11-10.md) i [co robi każdy ekran OLED](OLED_FUNCTIONS.md).

## 2b. Tune, All i Calibrate — trzy różne działania

| Działanie | Działanie w 1.0.4 |
|---|---|
| Wejście ikoną suwaków Tune | Odczytowy panel przygotowania, także w IDLE przed pierwszym pomiarem; bez ruchu i grzania |
| All w Tune | Wspólne M300_HOME_ALL; pokazuje postęp bazowania i temperatury, nie tworzy mesh |
| Calibrate w Tune | BED_MESH z przygotowaniem grzania i bazowania; nie trzeba osobno wykonywać All |

**Stały układ: schemat płyty/pól kontaktu nad heatmapą**, przed, podczas i po pomiarze. Jeżeli nie ma profilu, nie oczekuj kolorowej powierzchni; nie jest to powód do ponownego bazowania. [Pomiar, zapis i aktywacja](BED_MESH_AND_LEVELING.md).

## 3. Bazowanie i przygotowanie stołu

`M300_HOME_X`, `M300_HOME_Y`, `M300_HOME_XY`, `M300_HOME_Z` i `M300_HOME_ALL` uruchamiają wspólną logikę z OLED. Przy wspólnym XY kolejność jest **Y, następnie X**. Z wymaga odniesienia XY, odpowiedniej temperatury dyszy oraz sprawnego kontaktu PC7. Samo wybranie Home Z w menu nie usuwa wymogu wstępnego grzania.

Homing respektuje `z_contact_clearance`: domyślnie 5 mm, a na zakwalifikowanym egzemplarzu 2 mm; PC7 musi zostać rozwarty przed ruchem XY. Niezależna wysokość przejazdów M07 `safe_z` pozostaje 5 mm. Nie zastępuje to sprawdzenia, czy fizycznie jest miejsce na ruch. Z pozytywnym przyrostem Z platforma oddala się od dyszy. Po bazowaniu pozostaje bezpieczny odstęp.

Ordinary Z używa pięciu kolejnych kontaktów/zwolnień; końcowe odniesienie pochodzi z piątej krawędzi zwolnienia, nie ze średniej. M07 ma inną sekwencję. Nie zastępuj jej przypadkowym `samples: 5`. [Szczegóły](BED_MESH_AND_LEVELING.md).

## 4. Grzanie i pełne wygrzewanie platformy

**Ręczne temperatury w Thermals** to zwykłe zadania Klippera. **`M300_HEAT`** uruchamia procedurę OEM grzania ekstrudera (domyślnie 260°C) z komunikatem i zakończeniem potwierdzanym przez operatora. **`M300_HEAT_PLATFORM TEMP=60`** uruchamia wspólną procedurę stołu.

**`M300_FULL_PLATFORM_PREHEAT STATE=ENABLED`** zapisuje opcję następnego START. Nie zaczyna samodzielnie grzać. Włącza dodatkowy okres stabilizacji platformy, domyślnie 60 s, po osiągnięciu zadanych temperatur. `STATE=DISABLED` wyłącza tę opcję. START odczytuje ustawienie przy rozpoczęciu; zmiana w menu nie modyfikuje rozpoczętej już sesji.

## 5. Filament

`M300_LOAD` i `M300_UNLOAD` prowadzą operatora przez nagrzewanie i potwierdzenia. Domyślna temperatura proceduralna wynosi **240°C**, a nominalne długości LOAD/UNLOAD to **130/110 mm**. To parametry procedury portu, nie uniwersalne zalecenie temperaturowe dla każdego filamentu. Wariant wymiany w pauzie wykorzystuje 110 mm wycofania i 150 mm podania.

Podczas załadunku i rozładunku z OLED lub Fluidd może pozostać aktywna
natywna siatka stołu Klippera. Procedura porusza wyłącznie ekstruderem
i pozostawia profil aktywny po zakończeniu.

![Menu ładowania materiału](../img/oled/material_load@3x.png)

Po zmianie materiału zarówno temperatura zmierzona, jak i zadana muszą osiągać próg ekstruzji. Przy dyszy 230°C i celu 150°C wybierz **Reheat to check flow** na OLED lub **Resume** we Fluidd. Po dogrzaniu drukarka pozostanie w pauzie. Podaj materiał, sprawdź wypływ i wybierz **Confirm material flow** lub wpisz `FILAMENT_READY`. Każde przyjęte ręczne cofnięcie po potwierdzeniu ponawia pytanie o wypływ. Po kolejnym podaniu potwierdź wypływ ponownie, a następnie wybierz **Resume**.

W `[m300_filament]` pola `unload_temperature`, `unload_speed`, `load_temperature` i `load_speed` przyjmują osobno `auto` albo liczbę. W obu kierunkach `auto` oznacza 240°C i 2 mm/s. Po zakończeniu samego Load lub Unload ekstruder pozostaje gorący do wyłączenia grzania lub wystąpienia zwykłej bezczynności. Przy pytaniu o wypływ w pauzie możesz naciskać **Extrude** lub **Retract** w panelu Narzędzie. Dopiero po uzyskaniu czystego koloru potwierdź wypływ i wybierz **Resume**. [Procedura materiałowa](MAINTENANCE_MATERIAL.md).

Temperaturę dobierz w granicach materiału i konfiguracji, korzystając z obsługiwanych parametrów. Nie forsuj podawania, gdy materiał się zacina. Dalsza ekstruzja, potwierdzenie i anulowanie zależą od aktualnej fazy; stary przycisk nie jest zgodą na kolejną fazę. Zmiana podczas druku: PAUSE → `M300_CHANGE` → potwierdzenie prawidłowego przepływu → jawne RESUME.

## 6. START_PRINT i END_PRINT

Slicer powinien wywołać **jeden** `START_PRINT`, z temperaturami materiału, i **jeden** `END_PRINT`. Nie dokładaj równolegle drugiego bazowania, starego makra CR10S5 ani kolejnych linii czyszczących. Przykład *struktury wywołania* dla materiału, dla którego wcześniej dobrano 200/60°C:

```gcode
START_PRINT EXTRUDER_TEMP=200 BED_TEMP=60 MESH=m300_pads
```

Po nagrzaniu i stabilizacji Klipper cofa filament o 10 mm przed kontaktem
Z. Po bazowaniu aktywuje wybraną siatkę, dojeżdża do początku czyszczenia
na bezpiecznej wysokości i podaje 6 mm. Następnie wykonuje dwa długie odcinki
Y i dwa X bez dodatkowego odsunięcia Z między odcinkami. Ruch odbywa się na
zadanej wysokości 0,28 mm przy domyślnej konfiguracji, z natywną kompensacją
aktywnej siatki. Parametr `PURGE` określa żądaną długość, ograniczoną polem
ruchu, a dawka filamentu jest proporcjonalna do odcinka.
[Sekwencja i parametry START_PRINT](PRINT_CONTROL.md#kolejność-start_print).

W trybie Dynamic światło jest białe po zakończeniu `START_PRINT` dla
bieżącego pliku SD, także podczas przejścia od raftu do modelu.
Przygotowanie, pauza i błędy mają własne kolory.
[Odczyt fazy, siatki i stanu światła](PRINT_CONTROL.md#kontrola-i-odbiór).

`MESH=AUTO` wybiera zapamiętany profil płyty. Przy pierwszym użyciu może wybrać `m300_pads` lub jedyny zapisany profil. Brak wymaganego profilu zatrzymuje start. `MESH=m300_pads` wymaga profilu. `MESH=NONE` jawnie wyłącza siatkę. START nie mierzy mesh od nowa. Ustawienia i wcześniejsze tryby parsera są chronione; po sekwencji przywracane są m.in. tryby współrzędnych i mnożniki.

`END_PRINT` opuszcza stół o maksymalnie 300 mm od ostatniej pozycji, do limitu osi Z. Gdy stół się zatrzyma i prześwit jest wystarczający (domyślnie co najmniej 5 mm), głowica parkuje przy X300 Y305. Potem sterownik wyłącza cele grzałek i nawiew modelu. Po odczytaniu końca pliku OLED pokazuje **PRINTING DONE**. Chłodzeniem hotendu nadal steruje temperatura.

Źródła: [makra START/END](../../host/config/m300_operations.cfg), [kontroler druku](../../host/klippy/extras/m300_print_control.py).

## 7. PAUSE, RESUME i CANCEL

| Działanie | Oczekiwany przebieg |
|---|---|
| PAUSE z Fluidd lub OLED | Sterownik zapamiętuje pozycję druku. Po dokończeniu zaplanowanych ruchów wykonuje gorącą retrakcję i opuszcza stół domyślnie o 5 mm. Głowica pozostaje w bieżącym XY, silniki trzymają pozycję. |
| Wymiana materiału w pauzie | Głowica przejeżdża na odsuniętym stole do punktu serwisowego X300 Y305. Po zakończeniu wymiany operator potwierdza wypływ i wybiera RESUME. |
| Dłuższa pauza | Stół utrzymuje dotychczasowy cel; po 600 s domyślnie obniżenie celu dyszy do 150°C, po 1800 s wyłączenie celu dyszy |
| RESUME | Kontrola zgodności pliku i stanu, przywrócenie wymaganej temperatury, powrót i wznowienie; wymiana materiału może wymagać potwierdzenia przepływu |
| CANCEL_PRINT | Zatrzymanie pracownika SD, zamknięcie pliku, skasowanie pauzy oraz wyłączenie grzania i nawiewu modelu. Po opróżnieniu kolejki stół zjeżdża o maksymalnie 300 mm do limitu Z, potem głowica parkuje przy X300 Y305, jeśli prześwit pozwala. Ruch wymaga zachowanego XYZ; samo anulowanie nie czeka na zjazd |
| M112 | Awaryjny shutdown. Nie jest normalną pauzą; dalsza praca wymaga usunięcia przyczyny i świadomego restartu |

![Kontekstowe menu pauzy](../img/oled/pause@3x.png)

![Potwierdzenie zatrzymania z OLED](../img/oled/cancel_confirmation@3x.png)

Nie wyłączaj silników, nie wykonuj bazowania i nie przestawiaj osi ręcznie podczas pauzy, z której chcesz wznowić wydruk. Restart nie jest metodą wznowienia. Żądanie anulowania ma pierwszeństwo przed kontynuacją grzania lub parkowania. Nie traktuj czasu drenażu już zaplanowanych ruchów jako zgody na dodawanie nowych ręcznych przejazdów.

## 8. Aktualizacja i kontrola wersji

Poczekaj na stan Ready, zakończ wydruk i aktywne procedury oraz wyłącz cele
grzania. Użyj [instrukcji aktualizacji Klippera](INSTALL.md). Standardowa
aktualizacja obejmuje hosta i zachowuje stronę oraz ustawienia Fluidd. Dla
MCU 1.0.9 wystarczy aktualizacja hosta; starsze MCU zaktualizuj do 1.0.9 przed włączeniem jego wykresu temperatury. Numer hosta i MCU sprawdzisz poleceniem `ZORTRAX_INFO REFRESH=0`. W razie komunikatu o nieznanych
plikach zachowaj raport i porównaj lokalne zmiany.

W 1.0.4 `PRINT_CONTROL_STATUS` podaje rewizję `0.13.16.46-CANCEL-DROP`; `ZORTRAX_OLED_STATUS` pokazuje `NAV-EVENT-1` dla API hosta. Frontend podglądu ma `data-preview-revision="NAV-PIPELINE-2"` i `data-zoom-controls="OLED-ZOOM-2"`; Tune ma rewizję `TUNE-PREPARE-1`; nie oczekuj tej nazwy w rewizji MCU. Pole `navigation_delivered` powinno rosnąć przy kręceniu pokrętłem i widocznym podglądzie.

### Czas pracy drukarki

W konsoli odczytaj `ZORTRAX_HARDWARE_STATUS` oraz `ZORTRAX_INFO REFRESH=0`. Pierwsze polecenie pokazuje licznik MCU w minutach, stan banków oraz przyczynę oczekiwania. Drugie pokazuje też czas Klippera oczekujący na zapis. `CURRENT` i `factory_counter_pending: false` oznaczają rozliczenie pełnych minut. Po zwykłym wyłączeniu i ponownym włączeniu drukarki porównaj `factory_print_minutes`. [Stany licznika i trwałość](MCU_FIRMWARE_1.0.8.md).

## 9. Rozpoznawanie problemów

| Objaw | Co sprawdzić bez wymuszania ruchu |
|---|---|
| Nie można połączyć MCU | Zgodność baud, właściwy UART, brak konsoli Linux na porcie; `ZORTRAX_LINK_STATUS`, log Klippy |
| Podgląd OLED nie odpowiada menu | Wersję Fluidd po twardym odświeżeniu, `navigation_api`, widoczność karty, `data-navigation` event/fallback |
| Profil widoczny, ale „not active” | To normalny podgląd. Sprawdź `BED_MESH_OUTPUT`; wczytaj profilem albo START_PRINT |
| PC7 aktywny bez dotknięcia pola | Czystość styku, dyszy i przewodów. Nie powtarzaj bez końca kontaktowego bazowania |
| „Unknown runtime module” przy instalacji | Lokalna modyfikacja lub inny pakiet; porównaj SHA z oficjalnym wydaniem |
| Zacięcie materiału przy szybkim druku | Limit przepływu i temperaturę materiału, opory podawania i stan hotendu; nie zwiększaj automatycznie maksymalnej temperatury |
| Wentylator hotendu pracuje po CANCEL | Sprawdź temperaturę: to może być prawidłowe chłodzenie 50/45°C, nie pozostawiony wydruk |

W celu zebrania szczegółów ustaw `debug: True` w istniejącej sekcji `[m300_mcu]` i przeładuj Klipper na postoju. Po diagnozie przywróć `False`. Błędy są rejestrowane również przy wyłączonym debugowaniu.

Logi przydatne do zgłoszenia: `klippy.log`, `moonraker.log`, statusy powyżej i identyfikator wydania. Przed publicznym udostępnieniem usuń dane sieciowe, sekrety i identyfikatory niepotrzebne do diagnozy.

## 10. Komunikat o nieudanej kompilacji na GitHubie

Nie uruchamiaj aktualizacji na podstawie samej informacji, że powstał commit lub PR. Sprawdź końcowy przebieg dla właściwego commita, gotowe wydanie i BUILD_PROVENANCE.json gałęzi orange-pi. Nieudany wcześniejszy przebieg testowy pozostaje w historii nawet po poprawieniu kodu. Ponowienie bez poprawki pomaga przy chwilowej awarii sieci, nie naprawia błędu programu lub testu.

Publikacja wydania wymaga udanej budowy oraz kontroli paczki. Ta instrukcja **nie deklaruje stałego automatycznego naprawiania błędów** — funkcji tej nie dodają dzisiejsze zmiany frontendu. [Zakres weryfikacji](DOCUMENTATION_CHECK.md).

## Port Fluidd i ponawianie CI

Fluidd działa na porcie **4480**. Do zmiany plików strony służy osobna
[aktualizacja albo naprawa Fluidd](INSTALL.md#zaktualizuj-lub-napraw-fluidd).
[Automat CI](INSTALLATION_AND_CI.md) ponawia wyłącznie rozpoznane przejściowe
awarie, najwyżej dwa razy, i **nie deklaruje automatycznego naprawiania błędów kodu**. [Rejestr odbiorów](ACCEPTANCE_REGISTER.md) rozdziela potwierdzenia użytkownika i testy programowe. Aktualny opis START 2Y + 2X jest w [PRINT_CONTROL](PRINT_CONTROL.md).
