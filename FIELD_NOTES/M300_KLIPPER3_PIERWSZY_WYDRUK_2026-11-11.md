# Zortrax M300 Classic / Klipper / OrcaSlicer — pierwszy wydruk i korekcja mesh Z (11.11.2026)

**Status:** użytkownik potwierdził rozpoczęcie drukowania po korekcie konfiguracji; zakończenie całego wydruku i jakość pierwszej warstwy nie zostały jeszcze potwierdzone. **Zakres:** kwalifikowany egzemplarz M300 Classic, Orange Pi i gałąź `orange-pi`. **Uwaga:** nie jest to bezwarunkowy domyślny zakres mechaniczny wszystkich M300.

## Diagnoza

OrcaSlicer połączył się z Moonrakerem. Plik `3DBenchy_M300_0p4_0p2.gcode` trafił do `gcodes`. `START_PRINT` nagrzał dyszę (210°C) i stół (50°C), wykonał homing w centralnym punkcie kontaktu, załadował zapisany `m300_pads` przez `MESH=AUTO`, po czym przeszedł do punktu startu purge `X3 Y10`. Tam wystąpił błąd:

```text
Move out of range: 3.000 10.000 -0.089 [0.000]
```

Zarejestrowany `GET_POSITION` w tym punkcie: `gcode Z=5.000000`, `toolhead Z=4.630914` — rzeczywista korekcja siatki `-0.369086 mm`. Wysokość purge `0.280000 mm` po korekcji daje `Z=-0.089086 mm`. Stary limit `position_min: 0` blokował skompensowany ruch. `BED_MESH_OUTPUT`: 61×61, min `-0.4497`, max `0.0965`, rozpiętość ok. `0.5462 mm`.

**Nie przesuwać linii purge, nie wyłączać siatki, nie zmieniać zera homingu.** Położenie XY i wysokość purge względem lokalnej powierzchni pozostają takie same.

## Użyta konfiguracja — konkretny egzemplarz po kwalifikacji

W istniejącej sekcji `[stepper_z]` odpowiedniego `.cfg`:

```ini
[stepper_z]
position_min: -0.5
```

W istniejącej sekcji `[m300_calibration]`:

```ini
[m300_calibration]
safe_z: 5
approach_distance: 6.5
probe_search_margin: 1
```

Względem wcześniejszych wartości: `position_min: 0 -> -0.5`, `approach_distance: 6.0 -> 6.5`; `safe_z` po krótkiej próbie z `3` został przywrócony do `5`. Warunek z `m300_calibration.py`:

```text
approach_distance >= safe_z + probe_search_margin - position_min
6.5 >= 5 + 1 - (-0.5) = 6.5   PASS
```

Po zmianie użytkownik zgłosił: **drukarka zaczęła drukować**. Przed tą próbą `CANCEL_PRINT` poprawnie zaparkował głowicę, a `STATUS` i `PRINT_CONTROL_STATUS` pokazały odpowiednio `Ready` i `IDLE`.

**Bezpieczeństwo:** `-0.5` zezwala na dodatkowe 0,5 mm ruchu platformy w stronę dyszy poniżej środowego kontaktowego Z=0. Na innym egzemplarzu M300 należy najpierw potwierdzić fizyczny zapas mechaniczny i kalibrację czujnika. Nie stosować `FORCE_MOVE`, nie wyłączać endstopów i nie dodawać offsetu do całego wydruku. Obecne uniwersalne szablony repozytorium zachowują ostrożne `position_min: 0`, `approach_distance: 6.0`; wariant `-0.5/6.5` jest opcjonalny.

## Homing a kalibracja M07

**To dwa różne ustawienia:**

- `[m300_motion] z_contact_clearance: 5`: wstępne odsunięcie stołu i potwierdzenie rozwarcia PC7 przed ruchem XY, z wymuszeniem `max(5., self.clearance)` w `ensure_xy_clearance()`. Nie zależy od `safe_z`.
- `[m300_calibration] safe_z: 5`: bezpieczna wysokość przejazdu między punktami sondowania M07, nie początkowe odsunięcie PC7.

Homing Z w środku stołu nadal ustala Z=0; aktywny `m300_pads` wyznacza poprawki w pozostałych współrzędnych. Zmiana `position_min` i `approach_distance` nie zmienia tej zasady.

## Odrębna obserwacja temperatur

`m300_print_control` czeka na obie temperatury w zakresie ±2°C przez minimum 2 s. W starszej próbie zadane 30°C stołu blokowało start, gdy stół był cieplejszy. W czasie przejęcia grzałek ręczne `SET_HEATER_TEMPERATURE` zostało odrzucone jako `OEM service owns heaters`. To oddzielna kwestia do ewentualnej poprawy w przyszłości.

## Walidacja i dalsze kroki

1. Potwierdzić zakończenie druku Benchy oraz jakość pierwszej warstwy/raftu, brak kolizji mechanicznych i prawidłową kompensację.
2. Po zakończeniu wydruku można odczytać `STATUS`, `PRINT_CONTROL_STATUS`, `GET_POSITION`, `BED_MESH_OUTPUT`.
3. W osobnym nadzorowanym teście sprawdzić cały homing, M07, zwolnienie PC7 i `CANCEL_PRINT` dla nowych limitów.
4. **Nie uruchamiać instalatora, restartu Klippera ani aktualizacji Orange Pi podczas trwającego wydruku.**

**Źródła:** logi użytkownika z 11.11.2026 oraz gałąź `orange-pi` pliki `M300_HOST_R16_12_NORMAL_UI/payload/m300_print_control.py`, `m300_native_motion.py`, `m300_calibration.py`. Uzupełniająca [łatka szablonów](./M300_KLIPPER3_PIERWSZY_WYDRUK_2026-11-11.patch) jest **tylko przykładem opt-in** — nie jest automatycznie nakładana przez instalator.
