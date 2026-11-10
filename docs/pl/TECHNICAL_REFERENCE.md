# Parametry drukarki, komunikacja i odzyskane mapy temperatur

[Spis dokumentacji](../../README_PL.md) · [Obsługa](USER_GUIDE.md) · [Menu OLED](OLED_MENU_REFERENCE.md) · [Ilustrowane funkcje](OLED_FUNCTIONS.md) · [Parametry](TECHNICAL_REFERENCE.md)

> Dokumentacja dla **M300 Classic**, stan kodu **v1.0.0-beta.20**, commit `4828a9da9d5fd8b0b93eb2ac267732ee7e49d506`. Nie dotyczy M300 Plus, M300 Dual ani Inventure.


## 1. Co jest parametrem fabrycznym, a co ustawieniem portu

| Parametr | Wartość / interpretacja | Źródło |
|---|---|---|
| Model | Zortrax M300 **Classic**, bez Plus/Dual | Zakres tego repozytorium |
| Nominalny obszar roboczy | 300 × 300 × 300 mm | Specyfikacja producenta |
| Typowy oryginalny filament / dysza | 1,75 mm / 0,4 mm | Specyfikacja i profil bazowy |
| Układ | Jedna głowica, platforma grzana i perforowana | Specyfikacja |
| Sterownik portu | STM32F103, zegar MCU 72 MHz | Konfiguracja kompilacji portu |
| Host | Linux na Orange Pi; pakiet obsługuje też właściwie przygotowany Raspberry Pi | Instrukcja instalacji |
| Frontend / serwer API | Zmodyfikowany Fluidd 1.37.7 / Moonraker | Przypięta kompilacja |
| Klipper upstream | `ee2c6fb6b00b2b5d097ef70d0868df7d74943b51` | `PORT.json` |
| Wersja aplikacji MCU | `0.13.14.18-OEM-ERRORS-UART8` | Manifest beta.20 |
| Adres aplikacji MCU | `0x08008000`, kontener M300APP.M3B | Pakiet i bootloader |
| Host / kontroler druku | R16.12 / `0.13.16.38-PRINT-DRAIN-XY-PURGE` | Manifest i moduł druku |
| OLED / szybki podgląd | 256 × 64, 4 bity/piksel, 16 poziomów; NAV-EVENT-1 / NAV-PIPELINE-2 | Kod hosta i frontendu |

Źródła fabryczne: [M300 — producent](https://zortrax.com/3d-printers/m300-/), [specyfikacje serii M](https://support.zortrax.com/m-series-specification/). Parametry portu: [PORT.json](../../PORT.json), [konfiguracja sprzętu](../../host/config/m300_classic_base.cfg). Wymiary granic osi w konfiguracji nie są obietnicą większego niż fabryczny pola drukowania.

## 2. Limity nowej instalacji i zachowanie kalibracji

| Ustawienie w profilu bazowym | Wartość |
|---|---:|
| Kinematyka | `cartesian` |
| `max_velocity` | 300 mm/s |
| `max_accel` | 700 mm/s² |
| `square_corner_velocity` | 2 mm/s |
| `max_z_velocity` / `max_z_accel` | 25 mm/s / 50 mm/s² |
| X | 0…300 mm |
| Y | 0…305 mm |
| Z | 0…300 mm w szablonie nowej instalacji |
| X/Y: mikrostepy / obrót | 128 / 40 mm przy 200 pełnych krokach/obrót |
| X/Y: wynikowa skala | 640 impulsów STEP/mm |
| Minimalny czas impulsu STEP | 0,000002 s = 2 µs |
| E: mikrostepy / początkowe `rotation_distance` | 128 / 26,133 mm |
| Ruch wyłącznie E: limit długości / prędkości | 50 mm / 45 mm/s filamentu |
| Homing XY / Z w bazowym pliku | 20 / 4 mm/s; procedury natywne mogą narzucać własne wolniejsze etapy |
| Punkt odniesienia Z | Typowo X150/Y158 |
| Odstęp przed ruchem XY w procedurach kontaktowych | 5 mm |

To **wartości szablonu**, nie nakaz nadpisania aktualnego `printer.cfg`. Instalator zachowuje świadomie zmienioną geometrię, PID i kalibrację E. Odczytaj efektywną konfigurację po uruchomieniu i odpowiednie statusy. Ustawień z innej drukarki nie wklejaj w całości.

### Oś Z: fabryczne warianty

W trybie `z_profile: factory` port odczytuje zachowany rekord identyfikacji płyty i wybiera właściwą skalę:

| Rewizja fabryczna | Skala Z | Efektywny `rotation_distance` przy 16 mikrostepach |
|---|---:|---:|
| HW04 / rewizja niższa niż 5 | 800 STEP/mm | 4 mm |
| HW05 i nowsza obsługiwana przez tę regułę | 400 STEP/mm | 8 mm |

Nie wystarczy zobaczyć liczbę 4 lub 8 w starym pliku, aby uznać skalę za właściwą. Rozróżniaj wartość zapisaną i efektywną po identyfikacji. Gdy identyfikacja jest nieprawidłowa, należy rozwiązać problem, nie zgadywać rewizji. Tryb jawnej konfiguracji jest przewidziany dla świadomie zmienionej mechaniki. Audyt: [HARDWARE_VARIANTS](../en/HARDWARE_VARIANTS.md), kod [m300_native_z.py](../../host/klippy/extras/m300_native_z.py).

## 3. Trzy różne łącza

| Połączenie | Parametry w dokumentowanym wdrożeniu | Znaczenie |
|---|---|---|
| Linux ↔ MCU | UART 3,3 V, `/dev/ttyS1` w testowanym Orange Pi; zalecane 750000 baud, 8N1 | Komendy planera, telemetria i obsługa sprzętu |
| MCU ↔ OLED | SPI2, `spi_speed: 4500000`, porcje hosta `chunk_interval: 0.002` | Fizyczny ekran; kompresja RLE, DMA i ACK pozostają |
| Przeglądarka ↔ Moonraker ↔ Klippy | Istniejący autoryzowany WebSocket; beta.20 zachowuje osobny endpoint zdarzeń menu z beta.16 oraz pipeline z beta.17 | Obraz z pamięci hosta, nie odczyt ekranu z MCU |

Parametr `refresh_interval: 0.2` jest ustawieniem modułu OLED w konfiguracji bazowej. Nie oznacza sztywnego okresu wszystkich zdarzeń i nie zastępuje odrębnych terminów renderera. Standardowe statusy Klippera pozostają w dotychczasowym cyklu; nie zwiększono częstotliwości wszystkich temperatur i wykresów tylko dla podglądu.

### UART: wybór i diagnostyka

750000 baud jest domyślnym zaleceniem publikowanej instrukcji pierwszej instalacji. R14.18 rozszerza obsługę również o 1500000; lista przyjmowana przez moduł hosta obejmuje 19200, 57600, 115200, 250000, 500000, 750000, 1000000 i 1500000. **Lista akceptowana przez host nie oznacza, że każde ustawienie znajduje się w każdym menu bootloadera lub zostało zakwalifikowane na każdym SBC.**

W projekcie były testy 1500000, ale instrukcja tej bety zaleca 750000 ze względu na stabilny udokumentowany przebieg i retransmisje w jednym z testów szybszego łącza. Działającego łącza nie przełączaj tylko dlatego, że liczba jest większa. Wartości hosta i MCU muszą się zgadzać; instalator nie zmienia automatycznie UART w drukarce.

```gcode
ZORTRAX_LINK_STATUS
ZORTRAX_MCU_STATUS
ZORTRAX_OLED_STATUS
```

Porównaj `host_baud`, `baud` i wynik dopasowania. Przy analizie logu oceniaj przyrosty retransmisji, błędów i odrzuconych danych w konkretnym teście, a nie tylko brak błędu przy starcie. Szczegóły: [CONNECTION](../en/CONNECTION.md), [FIRST_INSTALL](FIRST_INSTALL.md).

UART: TX hosta → RX MCU, RX hosta ← TX MCU, wspólne GND; poziomy 3,3 V, nie RS-232 ani 5 V. MCU korzysta z USART1: **PA9 TX, PA10 RX**. To nazwy sygnałów procesora, nie numeracja złącza DEBUG. Piny fizyczne sprawdź dla posiadanej płyty, nie używaj numerów P4 z Inventure. Wyłącz konsolę serial/getty na używanym porcie Linux. Krótkie, poprawnie odniesione do masy przewody są ważniejsze niż samo zwiększenie baud.

Dla ilustracji 32 bajty przy 8N1 zajmują na przewodzie około 0,427 ms przy 750000 oraz 0,213 ms przy 1500000; nie obejmuje to protokołu, kolejek, planowania i sieci. Opóźnienie podglądu rozwiązano omijając cykl statusów, nie redukując pozycji menu do czterech bitów.

### Podgląd w beta.20

Host zna menu po interpretacji pokrętła i tworzy obraz. Odbiorca oczekuje na zmianę przez `m300/oled_preview/wait`; 10 s to limit bezczynnego oczekiwania, nie opóźnienie reakcji. Po odebraniu obrazu frontend od razu uzbraja następne oczekiwanie, niezależnie od dekodowania PNG. Jedna dekodowana klatka i jedna zastępowalna najnowsza nie tworzą kolejki starych menu. Przed wysyłką do MCU obraz może być już dostępny w przeglądarce; podgląd nie potwierdza optycznego wyświetlenia ani ACK danej klatki.

## 4. Odzyskane mapy temperatur z oryginalnego firmware

**W ramach prac nad portem wyodrębniono z oryginalnego oprogramowania Zortrax charakterystyki konwersji pomiaru ADC na temperaturę.** Są wykorzystywane w [m300_classic_sensors.cfg](../../host/config/m300_classic_sensors.cfg). Nie zastąpiono oryginalnych torów pomiarowych przypadkowym ogólnym modelem termistora i nie chodzi tutaj jedynie o wartości 180/240/260°C w makrach.

| Tor | Odtworzona reprezentacja | Jak rozumieć |
|---|---|---|
| Hotend | `M300_HOTEND_STOCK_LINEAR_LAB`: 0°C przy 0 V, 250°C przy 1,25 V | Liniowo 200°C/V, czyli 5 mV/°C dla toru w dokumentowanej konfiguracji |
| Platforma | `M300_BED_STOCK_TABLE_LAB`: **205 par temperatura–napięcie** | Nieliniowa tabela oryginalnego toru; Klipper interpoluje pomiędzy parami |
| Skala ADC | `adc_voltage: 3.270` i przeliczenie 12-bitowe `V = ADC × 3.270 / 4095` | Zależne od rzeczywistego analogowego toru M300; nie przenosić do innej elektroniki |

W tabeli występują skrajne wartości, m.in. 28048 oraz ujemne temperatury. To zachowane wartości charakterystyki i stanów skrajnych ADC, **nie dopuszczalne temperatury pracy**. Ich obecność nie upoważnia do rozszerzania limitów grzałek. Nazwy zawierające `LAB` są identyfikatorami kompatybilności w konfiguracji, nie deklaracją nowej kalibracji metrologicznej wykonanej podczas pisania instrukcji.

Odtworzenie map jest odrębne od sprawdzenia czujnika, kontaktu termicznego, napięcia odniesienia oraz strojenia PID na konkretnej drukarce. Zmiana hotendu/czujnika wymaga zgodnej charakterystyki; zachowanie oryginalnego czujnika nie automatyzuje oceny maksymalnej mocy nowej grzałki. Nie udostępniamy tutaj pełnego prywatnego dumpu fabrycznego firmware, numeru seryjnego ani danych konta. Źródła i audyt projektu: [PROVENANCE](../en/PROVENANCE.md), [CONFIGURATION_AUDIT](../en/CONFIGURATION_AUDIT.md).

## 5. Temperatury procedur a limity bezpieczeństwa

| Zastosowanie | Domyślne ustawienie portu |
|---|---:|
| Homing Z — minimum dla hotendu | 180°C; respektuje wyższy roboczy cel |
| Autokalibracja M07 / Heat the extruder | 260°C |
| Load/Unload/Change materiału | 240°C |
| Mesh: domyślny cel hotendu / stołu | 260°C / 60°C; niższy dopuszczalny parametr hotendu 180°C |
| Kontrola ekstruzji | `min_extrude_temp: 170` |
| Granice konfiguracji hotendu | 5…270°C |
| Granice konfiguracji stołu | 5…120°C |
| Chłodzenie hotendu | 50°C ON / 45°C OFF |

**Limity konfiguracji nie są zaleceniami temperatury druku ani nową specyfikacją sprzętu.** Producent podaje dla platformy M300 maksymalną temperaturę 105°C; wpis `max_temp: 120` w porcie jest progiem ochrony/konfiguracji, a nie potwierdzeniem bezpiecznej długiej pracy przy 120°C. Dla hotendu specyfikacja producenta i limit portu również nie są tą samą liczbą. Nie podnoś limitów, aby ominąć błąd. Temperaturę roboczą dobieraj do oryginalnego/zmodyfikowanego układu i materiału.

PID hotendu i stołu ma własne parametry. `PID_HOTEND`, `PID_BED`, `PID_SAVE` uruchamiają i zapisują natywną kalibrację; nie wykonuj ich w trakcie wydruku. Wyłączenie celu grzałki po END/CANCEL nie powinno odcinać chłodzenia gorącego hotendu. MCU zachowuje lokalne zabezpieczenia oraz politykę chłodzenia niezależną od życzenia wentylatora modelu.

## 6. OLED, stany i ograniczenia sprzętowe

Fizyczny OLED pozostaje przy MCU; ekran nie jest przełączany bezpośrednio na SPI Orange Pi. Obraz hosta ma 8192 bajty w formacie 4bpp. Podgląd w przeglądarce wykorzystuje PNG z tej samej pamięci renderera, nie drugi niezależny system menu. Na błędzie/utracie połączenia lokalny MCU może wyświetlać własny ekran, którego podgląd hosta nie potrafi wiarygodnie odwzorować; wtedy pokazuje stan niedostępności.

W beta.20 użytkownik wybiera **×1 / ×2 / ×3**, czyli docelowo 256×64, 512×128 albo 768×192 piksele CSS samej treści przy DPR 1 i 2. Helper mapuje każdy piksel na całkowity kwadrat N×N pikseli urządzenia, więc przy ułamkowym DPR rozmiar CSS może się nieznacznie zmienić. Do treści dochodzi ramka 2 pikseli urządzenia z każdej strony. Nie obowiązuje już bezwarunkowe 344×86 CSS.

Ekran jest centrowany względem całej karty z symetrycznymi marginesami, a przyciski są przy prawej krawędzi pod HIDE. **Cała kolumna przycisków ma wysokość podglądu ×1**: np. 68 CSS przy DPR 1, 66 CSS przy DPR 2, niezależnie od aktualnego ×2/×3. Wąski panel przewija tylko obraz. Kolory należą do palety PNG: #16A1FE tekst, #0A436C obrys, #0C588E zaznaczenie, #020610 tło. To odwzorowanie cyfrowe, nie pomiar barwy fizycznego panelu.

Skala jest zapamiętywana w przeglądarce; jej zmiana przerysowuje ostatnio zdekodowany obraz bez pobierania nowej klatki. HIDE/SHOW ukrywa/otwiera podgląd. MCU, UART/SPI, animacje i normalny cykl statusów nie są przyspieszane przez tę funkcję. Lupa systemowa, pulpit zdalny i chwilowe skalowanie gestem są poza kontrolą rastra aplikacji. [Rendery układu i tabela aktualizacji](UPDATE_2026-11-10.md).

## 7. Rewizje a numer wydania

| Warstwa | beta.20 |
|---|---|
| Dystrybucja | v1.0.0-beta.20; źródło `4828a9da` |
| Interfejs hosta podglądu | NAV-EVENT-1 |
| Pipeline przeglądarki | NAV-PIPELINE-2 |
| Sterowanie i układ powiększenia | OLED-ZOOM-2 |
| Tune | TUNE-PREPARE-1 |

Numer dystrybucji nie oznacza zmiany wszystkich warstw. [PORT.json](../../PORT.json) jest źródłem identyfikatorów. Nie oczekuj OLED-ZOOM-2 w komunikacie MCU.
