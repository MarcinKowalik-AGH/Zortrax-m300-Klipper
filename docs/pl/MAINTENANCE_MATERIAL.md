# Menu 2. Maintenance i 3. Material — host R16.5

[English](../en/MAINTENANCE_MATERIAL.md) · [Instalacja](INSTALL.md) · [Autokalibracja](LEVELING.md)

Na OLED wybierz **Zortrax M300**. Katalog zachowuje kolejność Models,
Maintenance, Material, Settings, Information. Maintenance zawiera dokładnie:
Back, Autocalibration, Heat the extruder, Move the platform up,
Move the platform down. Material: Back, Unload the material, Load the material.
Back wraca przez historię menu. Pozostałe natywne kontrolki są w Klipper.

| Pozycja OLED | Makro w grupie Fluidd ZORTRAX M300 | Wykonawca |
|---|---|---|
| Autocalibration | `ZORTRAX_LEVEL` | M07, 260°C; wspólne potwierdzenia i korekty trzech śrub |
| Heat the extruder | `ZORTRAX_HEAT` | Nagrzewanie do 260°C; komunikat gotowości od 258°C; kliknięcie wyłącza grzanie |
| Move the platform up | `ZORTRAX_PLATFORM_UP DISTANCE=1 SPEED=1` | Natywny Z w kierunku ujemnym, stół do dyszy |
| Move the platform down | `ZORTRAX_PLATFORM_DOWN DISTANCE=1 SPEED=1` | Natywny Z w kierunku dodatnim, stół od dyszy |
| Unload the material | `ZORTRAX_UNLOAD` | 240°C → cofanie → potwierdzenie wyjęcia → grzanie wyłączone |
| Load the material | `ZORTRAX_LOAD` | 240°C → potwierdzenie wsunięcia → podawanie → grzanie wyłączone |

Po instalacji uruchom `python3 setup_fluidd.py --apply`, kiedy Klipper jest
Ready, i odśwież Fluidd. Skrypt przenosi istniejące makra do właściwej grupy,
zachowując ich widoczność, kolory i pozostałe ustawienia użytkownika.
Alias testowy `TEST_ZORTRAX_LEVEL` nadal działa w TEST M300.

## Obsługa

Autokalibrację obsługuj według [audytu M07](LEVELING.md). Heat/Load/Unload
otwierają ten sam dialog na OLED także wtedy, gdy wystartują z makra lub
konsoli. Krótkie naciśnięcie potwierdza widoczny etap, długie anuluje.
Przycisk Fluidd dotyczy tego samego etapu. Stare i podwójne potwierdzenia są
odrzucane. Po normalnym zakończeniu Heat wraca do Maintenance, a materiał
do Material. Load nie dodaje kolejnego pytania o purge.

W Maintenance zaznacz Move the platform up/down i **przytrzymaj przycisk**.
Zwolnienie zatrzymuje zlecanie następnych odcinków. To gest przycisku,
nie obrót enkodera. Długie zdarzenie enkodera jest częścią przytrzymania.
Potrzebny jest rzeczywiście zbazowany Z; polecenia nie bazują automatycznie.
OLED wymaga potwierdzonego wyświetlenia właściwej pozycji oraz nowego
naciśnięcia po zwolnieniu. Zmiana widoku lub brak świeżego panelu przez
0,75 s kończy przytrzymanie. W kolejce może pozostać jeden odcinek do 0,1 mm.
Makro Fluidd wykonuje skończony odcinek DISTANCE, domyślnie 1 mm, SPEED
w mm/s. Obie drogi korzystają z tego samego natywnego właściciela osi Z,
rzeczywistych krańców i konfiguracji `max_jog_distance`/`jog_speed`.

Load/Unload poruszają wyłącznie E. Nie wymagają ani nie wymyślają bazowania
XYZ. Zachowane są skonfigurowane długości i prędkości; domyślnie Load 130 mm,
Unload 110 mm, 2 mm/s, odcinki po maksymalnie 5 mm. Anulowanie odcina grzanie
i czeka na opróżnienie już przyjętego odcinka. M112 zachowuje natywne działanie.
Serwisy wymagają bezczynnego wydruku; nie służą do zmiany materiału w
pauzowanym natywnym wydruku. Dotychczasowa ścieżka M600/M02 nie jest tutaj
przebudowywana. PID, kalibracja E, czujniki, zakresy osi i MCU pozostają
pod swoimi istniejącymi właścicielami.

Podczas aktywnej procedury zewnętrzny ruch, zmiany układu współrzędnych i
dodatnie nastawy temperatury są odrzucane. Wyłączenie grzania anuluje usługę.
Po zakończeniu przywracane są oryginalne funkcje poleceń Klippera, ustawienia
parsera materiału i timeout bezczynności. Oprogramowanie nie odtwarza
przerwanego ruchu po restarcie. Kwalifikacja profilu programowego nie stanowi
pomiaru sprzętu: `hardware_qualified=false` pozostaje prawdziwe.

## Dowody z oryginału i granice zgodności

Źródło: dostarczona aplikacja M300 Classic 1.3.1,
SHA-256 `11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75`.
Zidentyfikowane węzły RAM: Maintenance `0x20000680`, Material `0x200007b0`;
Heat `0x200006c0`, Up `0x20000700`, Down `0x20000720`, Unload `0x200007d0`,
Load `0x200007f0`. Obsługa przytrzymania: `0x08015d1c`, kierunki `0x08015354`
i `0x08015324`. Heat: `0x08015ed0`, Load: `0x08014f24`, Unload: `0x08015004`.

| Etap | Tekst OEM | Deskryptor dialogu | Deskryptor rysunku |
|---|---:|---|---|
| Nagrzewanie | 123 | bezpośrednie wywołanie tabeli `0x0801b96c` | `0x0801c2b8` |
| Grzanie zakończone | 16 | `0x08021d38` | `0x0801c024` |
| Wysuwanie | 19 | `0x08021eac` | `0x0801cfb0` |
| Wsuń materiał, naciśnij przycisk | 20 | `0x08021eb8` | `0x0801d0b8` |
| Potwierdzenie usunięcia | 21 | `0x08021ec4` | `0x0801cfb0` |
| Ładowanie | 22 | `0x08021ea0` | `0x0801d0b8` |

Teksty, podziały wierszy, glify 13 px i rysunki pochodzą z binarnego źródła.
Fluidd używa tego samego opisu co renderer OLED, bez nazw stanów i numerów
sesji w treści OEM. Komunikaty anulowania i błędów portu są rozszerzeniami.

Nie kopiujemy bezpośredniego sterowania TIM/GPIO silników ze starego firmware.
Sterowanie ruchem, skala E/Z, krańce oraz kontrola temperatury pozostają
natywne. Długość fizycznego podania i szybkość przytrzymania wymagają odbioru
na drukarce; nie wywodzimy ich z samej liczby wywołań timera oryginału.

Walidacja programowa: 203 testy hosta, 9 kontraktów repozytorium, 13 procesów
rzeczywistego Klippy w FILEOUTPUT; 110 pełnych ekranów w pięciu językach
zgodnych bajtowo z wykonaniem odzyskanego renderera oryginału. Nowe testy
używają przypiętego parsera G-code i GCodeMove, pełnych sesji materiału,
rzeczywistego dispatchu OLED, blokad, anulowania i przywracania poleceń.
Granice grzałek, zegar i ruch fizyczny są w tych testach modelowane.
Próba na Orange Pi/drukarce pozostaje do wykonania.
