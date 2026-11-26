# Audyt menu OLED — R16.18

[Instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/7686081e457a6868d6730ddf1087f077d21e81ca/docs/pl/INSTALL.md) · [Makra](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/7686081e457a6868d6730ddf1087f077d21e81ca/docs/pl/MACRO_REFERENCE.md) · [Odbiory sprzętowe](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/7686081e457a6868d6730ddf1087f077d21e81ca/docs/pl/ACCEPTANCE_REGISTER.md) · [Pełny wykaz widoków i komend](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/7686081e457a6868d6730ddf1087f077d21e81ca/docs/reports/OLED_MENU_AUDIT.json)

Zakres: **M300 Classic, MCU 1.0.9, host R16.18**. Sprawdzono dostępne gałęzie
produkcyjnego menu, rejestrację komend w prawdziwym Klippy, uruchamianie procedur
z OLED, ich potwierdzenia i powroty. Testy nie sterowały fizyczną drukarką.
Nie wszystkie procedury mają odbiór sprzętowy; bieżący stan i historię podaje
[rejestr](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/7686081e457a6868d6730ddf1087f077d21e81ca/docs/pl/ACCEPTANCE_REGISTER.md). PASS testu programu nie zastępuje tego odbioru.

## Wykryte problemy i poprawki

1. Użytkownik zgłosił wyjście z **Fan test po przełączeniu pokrętłem na OLED**.
   Wspólny skrót do statusu kończył aktywny test, a spóźniony wynik innej
   procedury mógł przejąć jego widok. Aktywny Fan test ma teraz pierwszeństwo
   prezentacji, a zwykłe żądanie ekranu statusu nie kończy sesji. Oba mechanizmy
   sprawdzono w testach; do ustalenia konkretnego wywołania na drukarce potrzebna
   jest diagnostyka. Długi klik korzysta z bieżącego **Back** i wraca do zapisanej
   pozycji. Zwykłe przełączenie górnego lub dolnego wentylatora pozostaje w teście.
2. **Current procedure** otwierało okno Fluidd, ale nie przywracało widoku OLED.
   Teraz jawne wywołanie `M300_PROCEDURE` otwiera właściwy ekran obu interfejsów.
   Przywraca wyłącznie widok — nie powtarza ruchu, grzania ani potwierdzenia.
3. **Back** z błędu bazowania mógł wrócić do innego menu zamiast do ekranu,
   z którego uruchomiono procedurę. Powrót wykorzystuje teraz jej sesję i zapisany
   ekran. Stan FAULT oraz blokada MCU pozostają bez zmian.
4. Menu PID korzystało bezpośrednio z komend natywnych. Teraz prowadzi przez te
   same makra `PID_HOTEND`, `PID_BED` i `PID_SAVE`, które są dostępne we Fluidd.

## Powiązania funkcji

Nie każda pozycja potrzebuje makra: przejście między ekranami jest nawigacją,
informacje są odczytami, a przyciski potwierdzeń trafiają do aktualnego właściciela
procedury. Wykaz JSON zawiera wszystkie odczytane wiersze i ich rzeczywiste akcje.
Proces Klippy sprawdził **44 widoki, 582 wiersze oraz rejestrację 26 komend**.
Aktywne fazy i potwierdzenia procedur sprawdza osobny zestaw testów hosta.

| OLED | Makro / komenda / właściciel | Zakres sprawdzenia |
|---|---|---|
| Maintenance → Autocalibration | `M300_LEVEL` → `m300_calibration` | Przepływ OEM, fazy śrub, potwierdzenia, błędy i anulowanie |
| Home X / Y / Z / XY / XYZ w obu gałęziach | `M300_HOME_X`, `M300_HOME_Y`, `M300_HOME_Z`, `M300_HOME_XY`, `M300_HOME_ALL` | Wspólne bazowanie, osobne osie, widoki faz i powroty |
| Heat the extruder / platform | `M300_HEAT`, `M300_HEAT_PLATFORM` → `m300_maintenance` | Osiągnięcie progu w modelu, potwierdzenie, anulowanie, zwolnienie zasobów |
| Move the platform up / down | Fizyczny gest przytrzymania → `m300_maintenance`; we Fluidd `M300_PLATFORM_UP/DOWN` | Zatrzymanie po zwolnieniu, aktualny wiersz, natywne ograniczenia Z |
| Fan test | `M300_FAN_TEST_START`; `M300_FAN_UPPER`, `M300_FAN_LOWER`, `M300_FAN_TEST_END` | Oba przełączniki, Back, długi klik, zakończenie, błąd i zachowanie chłodzenia |
| Current procedure | `M300_PROCEDURE` | Ponowne pokazanie bieżącej sesji oraz widok bez aktywnej procedury |
| Material → Load / Unload | `M300_LOAD`, `M300_UNLOAD` → `m300_filament` | Fazy OEM, oczekiwanie na operatora, transport modelowany, powrót do wybranego wiersza |
| Change material w pauzie | `M300_CHANGE` → `m300_print_control` / `m300_filament` | Tylko właściwa pauza, potwierdzenie wypływu, brak samoczynnego RESUME |
| Klipper → Hotend TEMP / Bed TEMP / Heat | `SET_HEATER_TEMPERATURE` i natywni właściciele grzałek | Zakres nastawy, wspólny cel, zabezpieczenia i blokady procedur |
| Turn off heaters | `TURN_OFF_HEATERS` | Dostępna komenda natywna |
| Bed mesh | `BED_MESH` → `m300_pad_mesh` | Opcjonalna gałąź, 25 punktów, właściciel pomiaru i odrębne błędy styku |
| Move X / Y / Z | `SAVE_GCODE_STATE`, `G91`, `G1`, odtworzenie trybu bez ruchu | Natywne bazowanie i granice osi; brak FORCE_MOVE |
| Fans → Print speed | `M106` | Natywna regulacja dolnego wentylatora; górny zachowuje termostat |
| PID calibration | `PID_HOTEND TARGET=200`, `PID_BED TARGET=60`, `PID_SAVE` | Istniejące makra, blokada wyborów podczas druku i pauzy |
| Models → SD / Host files | `m300_browser` → `m300_models` → natywny `virtual_sdcard` | Tożsamość pliku, import, granice parsera, właściwe rozpoczęcie; SD zależy od konfiguracji |
| Pause / Resume / Stop / ponowny wydruk | `PAUSE`, `RESUME`, `CANCEL_PRINT`, `M300_REPRINT` i natywni właściciele druku | Bieżąca sesja, potwierdzenie Stop, przytrzymanie i potwierdzenie usunięcia modelu |
| Settings — wszystkie 10 pozycji | `m300_settings` / `m300_nvm`; makra `M300_LIGHT`, `M300_BUZZER`, `M300_SLEEP_MODE`, `M300_LANGUAGE`, `M300_MODELS_SORT`, `M300_FULL_PLATFORM_PREHEAT`, `M300_OLED_BRIGHTNESS`, `M300_LED_BRIGHTNESS`, `M300_OLED_TIMERS` | Nawigacja, zakresy, zapamiętanie wyboru, powroty i oba czasy OLED |
| Information / Help / Errors | `M300_INFORMATION`, `M300_HELP`, `m300_errors` | Odczyty, katalog 21 kodów, zachowanie przyczyny alarmu; Back nie kasuje blokady |
| Diagnostics | Istniejące odczyty płyty, temperatur, wejść, SD i łącza OLED | Same odczyty; brak niepodpiętych komend |

## Zgodność z OEM 1.3.1

Testy wykorzystują zachowane wyniki wykonania modelu instrukcji OEM:
`firmware131_procedures.json`, `firmware131_maintenance.json` i
`firmware131_settings.json` w `host/update_template/tests/reference`.
Ich źródło identyfikuje SHA-256
`11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75`.
Przyciski, grzałki i transport mechaniczny w tych wynikach mają jawne modele.
Porównanie nie jest nowym testem fizycznego firmware'u.

Atlas zawiera 66 struktur OEM: 58 opisano jako adaptowane, trzy nieodtworzone
struktury dotyczą osobnego ostrzeżenia o gorącej głowicy i ogólnych Yes/No,
a pięć to nieużywane wpisy/separatory. Potwierdzenia portu mają własne tożsamości
sesji. Nie jest to deklaracja identyczności wszystkich fabrycznych dialogów.
Historyczne ilustracje beta.20 nie definiują aktualnego menu: gałąź Service / Tests
jest wycofana, a funkcje Klippera i regulacja czasów OLED są rozszerzeniami portu.

## Granice walidacji i instalacja

Testy sprawdzają stan programu i wywoływane komendy. Rzeczywisty obrót wentylatora
nie jest potwierdzony odczytem RPM — nie ma zweryfikowanego wejścia tachometru.
Dokładność Z, temperatury, transport filamentu, pierwsza warstwa i długi wydruk
wymagają odpowiednich odbiorów na konkretnej drukarce.

Na istniejącym Orange Pi, gdy drukarka jest bezczynna i Ready:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

To aktualizacja modułów hosta i makr. Samo `--update-fluidd` nie instaluje poprawki
menu OLED. MCU 1.0.9 pozostaje wystarczające; ta poprawka nie wymaga jego wgrywania.
Instalator zachowuje istniejące PID, mesh, kwalifikowane ustawienia Z i opcjonalne
include temperatur. Nowy użytkownik korzysta z [pełnej instalacji](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/7686081e457a6868d6730ddf1087f077d21e81ca/docs/pl/FIRST_INSTALL.md).
Gałąź `orange-pi` zawiera gotowe pliki, zbudowany Fluidd i sumy kontrolne.
