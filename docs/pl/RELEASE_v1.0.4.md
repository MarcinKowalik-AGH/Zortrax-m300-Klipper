# M300 Classic 1.0.4 — poprawki OLED, opcjonalna kamera i wykresy temperatur

26 listopada 2026 r. **Host 1.0.4 / R16.19, MCU 1.0.9**. Wydanie zastępuje
pierwotną paczkę 1.0.3. Pełny ZIP zbiera poprawki publikowane wcześniej w gałęzi
`orange-pi`, aktualne instalatory i instrukcje oraz nowy zrzut operatora.
Zakres: M300 Classic z oryginalnym sterownikiem STM32F103.

## Co zmieniło się od paczki 1.0.3

- Opcjonalna kamera USB z osobnym `m300_camera.conf`, włączaniem i wyłączaniem,
  integracją Fluidd oraz trybem UV4L-MJPEG sprawdzonym w OrcaSlicerze 2.5.2.
- Niezależne opcjonalne krzywe **Host** i **MCU**. Oba include w `printer.cfg`
  są domyślnie zakomentowane; zakomentowanie wyłącza daną opcję. Inne strefy
  Orange Pi są odczytywane na żądanie przez `read-host-temperatures.py`.
- MCU 1.0.9 udostępnia temperaturę wewnętrzną z ADC16. Wykres oraz polecenie
  `M300_MCU_TEMPERATURE` korzystają z tego samego przybliżonego pomiaru STM32.
- Rozpoznany brak lub niestabilność kontaktu dyszy opuszcza stół o maksymalnie
  100 mm w znanym zakresie Z, unieważnia Z i prosi o czyszczenie. Nieznane Z
  nie uprawnia do ruchu w ciemno. Rzeczywiste błędy MCU i termiki zachowują shutdown.
- Poprawnie zakończone bazowanie Z rozwiązuje poprzedni komunikat błędu styku
  i jego sygnalizację kolorami, zachowując inne błędy.
- Natywne `check_gain_time: 40` uwzględnia zaobserwowane opóźnienie ponownego
  nagrzewania. Instalator zachowuje istniejącą własną sekcję użytkownika.
  Pozostają aktywne progi przyrostu, błędu skumulowanego, ADC, PID i zabezpieczenia MCU.
- Obserwator meshu nie przełącza automatycznie do Tune podczas druku ani pauzy.
  `START_PRINT ... MESH=AUTO` nadal ładuje zapisany profil.
- Fan test zachowuje swój widok podczas przełączania wentylatorów; spóźniony
  wynik innej procedury i żądanie statusu nie kończą go samoczynnie. Poprawiono
  długi klik Back, Current procedure, powroty po błędzie i wspólne makra PID.
- Pełna instalacja nowego hosta obsługuje Python 3.10–3.13, także Debian 13 Trixie.
  ZIP i klon Git dostarczają moduły diagnostyczne oraz pliki opcji temperatur.

W paczce pozostają również poprawki nadzoru przy planowanym restarcie, anulowania
meshu i liczników pracy. Aktualizacja zachowuje własny PID, mesh, kwalifikowane
ustawienia Z, UART i istniejące wybory konfiguracji.

## Instalacja i aktualizacja

Nowy host przygotuj według [pełnej instrukcji](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.4/docs/pl/FIRST_INSTALL.md). Publiczne
wydanie zawiera `Zortrax_M300_Klipper_v1.0.4.zip`, plik zewnętrznych sum SHA-256
oraz instrukcje pierwszej instalacji PL/EN. ZIP zawiera pełny zmodyfikowany
rdzeń Klippera, aplikację MCU na SD, gotowe Fluidd, konfigurację, instalatory i raporty.

Na działającym Orange Pi, przy bezczynnej drukarce w Ready i wyłączonych celach grzania:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Osobno zaktualizuj interfejs przez
`python3 install-orange-pi.py --update-fluidd --port 4480` i odśwież Fluidd.
**MCU 1.0.9 nie wymaga ponownego wgrywania.** Starszą wersję zaktualizuj przed
włączeniem temperatury wewnętrznej. [Instrukcja MCU](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.4/docs/pl/MCU_FIRMWARE_1.0.9.md).

## Walidacja i odbiory

Walidacja programu obejmuje 1055 testów hosta, prawdziwy proces Klippy FILEOUTPUT,
migracje i wycofanie zmian, pełną nową instalację na Pythonie 3.12 i 3.13 oraz
testy Fluidd. [Audyt OLED](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.4/docs/pl/OLED_MENU_AUDIT.md) obejmuje 44 widoki, 582 wiersze
i powiązania 26 komend. Testy nie sterują fizyczną drukarką.

Nowy zrzut potwierdza widoczny obraz kamery i wykresy Host/MCU u operatora.
Nie jest odbiorem każdej procedury ani dokładności czujników. [Rejestr sprzętowy](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.4/docs/pl/ACCEPTANCE_REGISTER.md)
zachowuje zgłoszone błędy i próby oczekujące. Atlas ilustracji OLED ma historyczny
punkt odniesienia **beta.20**. Pliki i tag poprzedniego wydania 1.0.3 pozostają niezmienione.
