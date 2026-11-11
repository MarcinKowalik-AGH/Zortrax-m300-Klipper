# M300 beta.24 — pierwszy wydruk, ujemne Z z mesh i odsunięcie styku 2 mm

[Instrukcja główna](../../README_PL.md) · [Źródłowa notatka użytkownika](../evidence/M300_FIRST_PRINT_USER_REPORT_2026-11-11.md) · [Rejestr odbiorów](ACCEPTANCE_REGISTER.md)

## Źródło i zakres potwierdzenia

Podstawą jest notatka z testu **11 listopada 2026**. Po nagrzaniu i homingu
purge X3/Y10 został odrzucony przy Z=-0,089 mm. GET_POSITION pokazał różnicę
między G-code Z5 a toolhead Z4,630914: **-0,369086 mm**. Dla purge Z0,28 daje
to **-0,089086 mm**, poniżej dotychczasowego position_min=0. Nie zmieniamy
początku purge ani nie wyłączamy profilu m300_pads, aby ukryć ten problem.

Użytkownik potwierdził rozpoczęcie druku po zmianie granicy na -0,5 i geometrii
M07 na 5/6,5/1. Potwierdził też CANCEL po nieudanym starcie: parkowanie,
Ready oraz IDLE/busy=false. Nie potwierdził ukończenia Benchy, jakości pierwszej
warstwy ani wszystkich scenariuszy pauzy/wznowienia. Dane pochodzą z notatki;
nie wykonano nowego pomiaru drukarki podczas tej aktualizacji.

**Późniejsza dyspozycja użytkownika:** odsunięcie kontaktu podczas homingu
ma wynosić **2 mm zamiast 5 mm**. Oryginalna notatka opisuje wcześniejszy kod
z wymuszonym minimum 5 mm; zachowujemy ją bez zmian jako dokument źródłowy,
a poniżej opisujemy aktualizację, nie udajemy, że zapis źródłowy mówił o 2 mm.

## Jeden jawnie wybierany profil egzemplarza

```ini
[stepper_z]
position_min: -0.5

[m300_motion]
z_contact_clearance: 2

[m300_calibration]
safe_z: 5
approach_distance: 6.5
probe_search_margin: 1
```

**Nie dodawaj zdublowanych sekcji.** Instalator aktualizuje istniejące sekcje,
także w dołączonych plikach, i zachowuje SAVE_CONFIG, siatkę, PID, skalę osi,
UART, limity X300/Y305 oraz parametry purge. Wymóg geometrii nadal obowiązuje:
`approach_distance >= safe_z + probe_search_margin - position_min`, zatem
`6.5 >= 5 + 1 - (-0.5)`. Ustawienie safe_z=2 zamiast 5 nie jest tą poprawką.

**Ujemny limit dotyczy tylko mechanicznie sprawdzonego egzemplarza.** Pozwala
platformie zbliżyć się o 0,5 mm ponad odniesienie z homingu. Nie stanowi zgody
na ruch dowolnej M300 w tym zakresie. Szablony pierwszej instalacji pozostają
ostrożne: position_min=0, safe_z=5, approach_distance=6 i clearance=5.
Nie przesuwamy zera, krańcówki ani probe.z_offset. Nie dodajemy FORCE_MOVE.

Kod respektuje teraz skonfigurowany z_contact_clearance (minimum 2, domyślnie
5 mm) dla początkowego odsunięcia, dodatkowego rozwarcia przed drugim przebiegiem
kontaktu i końcowego odsunięcia. Każdy dotychczasowy odczyt PC7, limit zakresu,
unieważnianie pozycji i zatrzymanie przy nierozwartym styku pozostają.
Przy 2 mm i nadal zwartym styku operacja kończy się błędem — nie rozpoczyna XY.
Wysokość przejazdów M07 safe_z=5 jest oddzielna i nie zostaje obniżona.
Nie zmieniono pięciu referencji Z, wewnętrznego kroku zwolnienia sondowania,
czterech linii START ani ich wysokości 0,28 mm.

## Aktualizacja przez Git na Orange Pi (Fluidd 4480)

Dopiero po zakończeniu wydruku, przy bezczynnej drukarce **Ready**, jako
użytkownik klipper:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480 --qualified-first-print-z
```

Flaga jawnie wybiera powyższy profil egzemplarza i oznacza potwierdzenie jego
mechanicznego zakresu. Bez flagi aktualizacja nie zmienia position_min ani
z_contact_clearance. Już zapisane -0,5/6,5/2 pozostają również przy późniejszych
zwykłych aktualizacjach. Plan sprawdza rozpoznane wartości poprzednie i nowe;
nie nadpisuje innych własnych nastaw. Stosowane są kopia i wycofanie istniejącego
instalatora. Nie omijaj SHA256SUMS ani odmowy nadpisania nieznanej lokalnej zmiany
kodu. Przeróbki samego pliku Python wymagają osobnego porównania, nie reset --hard.

Domyślny plan bez zapisu, np. do sprawdzenia listy zmienianych plików:

```bash
python3 "$HOME/m300-orange-pi/M300_HOST_R16_12_NORMAL_UI/install.py" --qualified-first-print-z
```

Po aktualizacji odśwież Fluidd. Wykonaj odczyt `ZORTRAX_MOTION_STATUS`:
`z_contact_clearance_mm` i `z_initial_clearance_mm` powinny wynosić 2.
Rewizja modułu ruchu to `0.13.16.24-QUALIFIED-Z-CLEARANCE`.
Aplikacja MCU pozostaje **0.13.14.19-TONED-OLED-UART8**; nie wgrywaj ponownie
`MCU/M300_R14_19_SD.zip` dla tej zmiany. Aktualizator hosta sam nie flashuje MCU.

## OrcaSlicer, oczekiwanie i zachowane ustawienia

Pliki przesyłaj do zasobu Moonrakera **gcodes**, nie config. START zachowuje
MESH=AUTO i m300_pads. Temperatura 210/50°C w notatce jest zapisem próby,
nie nową globalną temperaturą profilu. W notatce nie ma pełnych plików profili
Orca; ta aktualizacja nie deklaruje ich dodatkowej walidacji ani podmiany.

Oczekiwanie na ochłodzenie stołu do celu to odrębna kwestia: nadal obowiązuje
pasmo ±2°C i co najmniej 2 s stabilizacji. Nie zastępuj tego ręcznymi zmianami
celów w trakcie START. Nowsza polityka temperatur M300305/105, obecna w gałęzi
przed tą poprawką, jest zachowana bez zmian; nie jest nowym ustaleniem z notatki.

## Testy i granice

Regresje sprawdzają zarówno domyślne 5 mm, jak i jawne 2 mm, zwarty PC7,
ograniczenia osi, drugi przebieg kontaktu, M07 dla -0,5/6,5, idempotencję,
konfigurację w include, odmowę nieznanych wartości, kopię/rollback i zachowanie
siatki. Pełny CI musi potwierdzić host, natywnego Klippy, ARM, Fluidd i pakiet.
Testy są programowe, nie odbiorem pierwszej warstwy. Manual 65 ekranów nadal
ma jawny wizualny punkt odniesienia beta.20; wygląd OLED się nie zmienia.
