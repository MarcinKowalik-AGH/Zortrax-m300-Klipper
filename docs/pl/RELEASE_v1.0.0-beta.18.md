# M300 Classic v1.0.0-beta.18 — Tune przed pomiarem i wspólne bazowanie

Wydanie zastępuje beta.17. Rewizja panelu Tune: `TUNE-PREPARE-1`.
Podgląd OLED pozostaje `NAV-PIPELINE-2`, interfejs hosta `NAV-EVENT-1`.

## Co poprawiono

| Działanie | Zachowanie beta.18 |
|---|---|
| Wejście ikoną Tune (suwaki) | Panel przygotowania działa już w początkowym `IDLE`, przed pierwszym pomiarem. Otworzenie strony nie wysyła poleceń ruchu, grzania, pomiaru, zapisu ani aktywacji profilu. |
| All w Tune | Wywołuje wspólne `ZORTRAX_HOME_ALL` i pokazuje postęp bazowania oraz temperatury rzeczywiste/zadane. Nie rozpoczyna nowego mesh. |
| Calibrate w Tune | Wywołuje `BED_MESH`, tak jak działające makro. Dotychczasowy backend zapewnia przygotowanie grzania i bazowania; osobne kliknięcie All nie jest wymagane. |
| Kolejność grafik | Zawsze schemat płyty/pól kontaktowych u góry, a kolorowa heatmapa poniżej. Kolejność nie zmienia się po pomiarze, zapisaniu lub wczytaniu profilu. |

Stan `IDLE` nie otrzymuje fikcyjnego identyfikatora pomiaru i nie pozwala na zapis
nieistniejącego wyniku. Zachowano blokady wywołań podczas druku, pauzy, zajętości
lub braku Ready. Inne drukarki zachowują standardowe G28 i BED_MESH_CALIBRATE.

Zmiana dotyczy Fluidd. Nie zmieniono kodu wykonawczego hosta ani MCU, procedur
ruchu i termiki, profili mesh ani START/PAUSE/RESUME/CANCEL. Szybka nawigacja OLED,
kwadratowe piksele oraz rytm animacji i standardowych statusów są zachowane.
Starszy zrzut dokumentacyjny z heatmapą na górze przedstawia poprzedni układ.

## Aktualizacja standardowej beta.17

Na Orange Pi, wyłącznie przy bezczynnej drukarce w stanie **Ready**:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Następnie odśwież Fluidd skrótem **Cmd+Shift+R**. Nie trzeba wgrywać MCU,
resetować konfiguracji, ponawiać pomiaru mesh ani zmieniać Moonrakera.
Nie instaluj wcześniejszego ZIP-a ze źródłami na drukarce i nie wymuszaj
nadpisania nieznanych lokalnych zmian.

Plik `BUILD_PROVENANCE.json` w gałęzi instalacyjnej ma wskazywać
`v1.0.0-beta.18`. `ZORTRAX_OLED_STATUS` nadal zgłasza `NAV-EVENT-1`, ponieważ
protokół hosta nie został zmieniony.

## Weryfikacja

Warunkiem publikacji jest pełny zgodny przebieg CI: testy hosta i natywnego
Klippy, kompilacja ARM, dotychczasowe testy Fluidd/OLED, testy komponentów Tune,
ESLint, kontrola typów, porównanie pikseli w Chromium/Firefoksie, produkcyjny
build Fluidd oraz sprawdzenie integralności pakietu.

Nowe testy obejmują wejście w IDLE bez poleceń, odrzucenie uszkodzonego statusu,
All i Calibrate, samodzielne bazowanie, blokady konkurencyjnych poleceń,
zachowanie innych drukarek oraz stały układ kart. Dane drukarki są symulowane;
testy nie wykonują ruchów i grzania na fizycznym urządzeniu.

Po aktualizacji najpierw otwórz Tune bez uruchamiania procedury: ma być widoczny
panel przygotowania i schemat nad heatmapą. Próbę All wykonaj pod zwykłym
nadzorem mechanicznym; powinien pojawić się postęp bazowania bez tworzenia
nowej siatki. Testy programowe nie zastępują potwierdzenia na drukarce.
