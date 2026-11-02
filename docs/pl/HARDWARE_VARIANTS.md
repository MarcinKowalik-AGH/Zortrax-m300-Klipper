# Rewizja sprzętu M300 i wariant osi Z

[English](../en/HARDWARE_VARIANTS.md)

MCU R14.5 i host R16 odczytują zachowaną fabryczną rewizję raz podczas
identyfikacji Klippy. Wybierają skalę natywnego Z przed konfiguracją i włączeniem
sterowania płytą. Funkcja nie dodaje cyklicznych zapytań, przechwytywania ruchu,
właścicieli GPIO/ADC ani zapisu Flash. PID-y, kalibracja ekstrudera, limity
prędkości i zapisana konfiguracja pozostają w dotychczasowych plikach.

## Dowody z oryginalnego firmware

Aplikacja M300 stock 1.3.1 ma 146392 bajty, adres bazowy 0x08008000 i SHA-256
`11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75`.
Bezpośredni disassembly ARM potwierdza poniższy łańcuch; uzupełnia on archiwalny
kontrakt M07:

| Adres | Znaczenie |
|---|---|
| 0x0800A428 | Odczyt rekordu z 0x0803F800 + 24 × ID |
| 0x080181E0 | Odczyt ID 3, wymagany jeden bajt, odjęcie 0xE0 |
| 0x200015F0 | Bajt rewizji sprzętu podczas pracy stock |
| 0x08015FB0 | Inicjalizacja M300: rodzina modelu 4 |
| 0x08018930 / 0x080189C4 | Wybór profilu M300 na podstawie rewizji |
| 0x080242F4 + 68 | Starszy profil: float 800.0 kroków/mm Z |
| 0x080243A4 + 68 | Nowszy profil: float 400.0 kroków/mm Z |

Nagłówek fabrycznego rekordu leży pod **0x0803F848**, bajt danych pod
**0x0803F84C**. Jednobajtowy rekord ID3 ma nagłówek **0xAABB0103**
(little endian: 03 01 BB AA). E4 oznacza HW04, E5 oznacza HW05.

| Odczytana rewizja | Skala Z OEM | Natywne rotation_distance przy 200 pełnych krokach × 16 mikrokroków |
|---|---:|---:|
| Poniżej 5 | 800 kroków/mm | 4 mm |
| Od 5 | 400 kroków/mm | 8 mm |

To reguła selektora, a nie wykaz wszystkich wyprodukowanych rewizji M300.
Obraz samej aplikacji nie zawiera zachowanego rekordu fabrycznego. Prywatny
backup sprawdzonego HW05 zawiera E5; numer seryjny, UID i pełny zrzut nie są
publikowane. Oficjalna konfiguracja Marlin M300_v5 również podaje Z=400:
https://github.com/Zortrax3D/MarlinConfigurationsZortraxM200/blob/12b32a9a2eb69c070f69a6cb4dfbd1a3fa74da22/config/examples/Zortrax/M300_v5/Configuration.h

## Zachowanie portu

MCU udostępnia odczyt `m300_factory_query`, ABI fabryczne 1. Zwraca surowy
nagłówek/bajt i rozkodowaną rewizję/skalę także przed konfiguracją i po shutdown.
Host niezależnie sprawdza rekord oraz zgodność rozkodowanych danych. Akceptuje
wyłącznie nagłówek 0xAABB0103 i bajt E0..FE. FF, skasowany rekord, błędny ID,
długość lub niespójne dane nie pozwalają na automatyczny wybór. To walidacja
ściślejsza niż bezwarunkowe zawijanie błędnego bajtu w kodzie OEM.

Domyślne `[m300_mcu] z_profile: factory` wymaga ABI 1 z MCU R14.5.
Poprawny rekord wybiera rotation_distance natywnego stepper_z przez istniejące
API Klippera podczas `klippy:mcu_identify`. Fabryczny Z wymaga lokalnego PB7,
16 mikrokroków, 200 pełnych kroków i braku gear_ratio. Przeliczenia M07 oraz
audyt konfiguracji ruchu korzystają z tej samej skali. Nie oznacza to fizycznej
kwalifikacji, bazowania ani wznowienia operacji. Dawna nazwa profilu testowego
pozostaje obsługiwana; jego warunki prześwitu, zakresu i termiki są zachowane.

Brak lub uszkodzenie rekordu powoduje opisowy błąd startu. Po wymianie śruby
albo dla świadomie skonfigurowanego egzemplarza można jawnie wybrać:

~~~ini
[m300_mcu]
z_profile: config
~~~

Ten tryb zachowuje skalę natywnego Z i M07 z konfiguracji. Rewizja jest raportowana,
jeśli MCU ją obsługuje, ale nie zmienia skali. Dotychczasowa matematyka M07
obsługuje 400 albo 800 kroków/mm. Tryb factory nie przepisuje rotation_distance
ani stock_steps_per_mm w plikach i nie dodaje danych do SAVE_CONFIG. Zapis PID
pozostaje natywny. Status oddzielnie podaje wartość z pliku i wartość używaną.

## Odczyt i walidacja

Użyj `ZORTRAX_HARDWARE_STATUS` albo pola `hardware` w `ZORTRAX_MCU_STATUS`.
Information na OLED pokazuje rewizję, używaną skalę Z i tryb wyboru. Status ruchu
również podaje używaną skalę. Moonraker udostępnia te dane jako
m300_mcu.hardware. Ponowne połączenie wykonuje świeży odczyt. FILEOUTPUT
jawnie raportuje FILEOUTPUT_NO_FACTORY_READ.

Testy publiczne obejmują 1792 przypadki dekodera C, testy hosta uszkodzonych
rekordów, trybu config, timeoutów i granic startu oraz rzeczywisty Klippy
FILEOUTPUT z syntetycznymi rekordami HW04/HW05. Natywny planowany ruch Z o
1 mm daje odpowiednio 800/400 kroków w solverze i zgodną skalę M07. Skasowany
rekord jest odrzucany przed konfiguracją MCU. To testy programowe, nie pomiary
na dwóch drukarkach. Pierwszy test fizyczny powinien potwierdzić raportowaną
rewizję i zmierzoną drogę Z; pełny zakres pozostaje osobnym pomiarem.

R16 używa normalnego natywnego G28/probe i usuwa dawną konfigurację
uruchomieniową z obsługi normalnej. Wybór fabryczny i jawny tryb config
pozostają zgodne z powyższym opisem. Zobacz FEATURES.md.
