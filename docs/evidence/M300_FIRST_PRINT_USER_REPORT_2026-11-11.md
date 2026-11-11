# Zortrax M300 Classic + Klipper + OrcaSlicer — pierwszy start wydruku i korekcja Z

**Data testu:** 11 listopada 2026 r.  
**Projekt:** [Zortrax-m300-Klipper](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper), gałąź `orange-pi`.  
**Cel dokumentu:** przenieść ustalenia do rozmowy „Klipper 3” i zachować zweryfikowaną konfigurację egzemplarza M300 Classic.  
**Zakres potwierdzenia przez użytkownika:** po zmianach drukarka nagrzała się, wykonała homing, rozpoczęła drukowanie. Nie potwierdzono jeszcze ukończenia całego Benchy ani jakości pierwszej warstwy.

## 1. Środowisko i ścieżka wydruku

- M300 Classic (nie Plus ani Dual), Orange Pi + Klipper, Fluidd, OrcaSlicer.
- Z OrcaSlicer przesyłać G-code do zasobu Moonrakera **`gcodes`**, nie `config`.
- Testowy plik: `3DBenchy_M300_0p4_0p2.gcode`; temperatura startowa w diagnostyce nieudanego drugiego podejścia: **dysza 210°C, stół 50°C**.
- Kontroler wydruku: `0.13.16.38-PRINT-DRAIN-XY-PURGE`.
- Start używa `MESH=AUTO`, który wybrał zapisany profil siatki **`m300_pads`**. Nie należy go wyłączać jako obejścia problemu.

## 2. Pierwsze niepowodzenie — limit Z, nie błąd homingu ani OrcaSlicer

Po poprawnym nagrzaniu i homingu głowica podjechała do punktu rozpoczęcia purge **X=3, Y=10**. Następnie Klipper odrzucił ruch:

```text
Move out of range: 3.000 10.000 -0.089 [0.000]
```

W kodzie `m300_print_control.py` linie purge są generowane przy wysokości `purge_height = 0.28 mm`; pierwsza pozycja to X=3, Y=10. **Nie trzeba przenosić linii purge w inne miejsce.**

Pomiary i stan z `GET_POSITION` w tym punkcie:

```text
gcode:    X:3.000 Y:10.000 Z:5.000000
toolhead: X:3.000 Y:10.000 Z:4.630914
```

Różnica to **−0,369086 mm**. Korekcja dla docelowego Z=0,280 mm daje:

```text
Z ruchu po korekcji = 0.280000 - 0.369086 = -0.089086 mm
```

To dokładnie zgadza się z błędem. Siatka `m300_pads` ma 61×61 punktów, `min=-0.4497 mm`, `max=0.0965 mm` (rozpiętość ok. 0,5462 mm). Jest odniesiona do punktu kontaktu homingu Z=0 w środkowej części platformy. Ujemna współrzędna po transformacji nie dowodzi błędnej siatki; błąd wynikał z ówczesnego programowego `position_min: 0`.

## 3. Konfiguracja zastosowana w testowanym egzemplarzu

Zmiany w istniejących sekcjach właściwych plików `.cfg` — **nie dodawać drugi raz sekcji o tej samej nazwie**:

```ini
[stepper_z]
position_min: -0.5

[m300_calibration]
safe_z: 5
approach_distance: 6.5
probe_search_margin: 1
```

Zmiany w stosunku do wcześniejszego ustawienia: `position_min: 0 -> -0.5` oraz `approach_distance: 6.0 -> 6.5`; `safe_z` został przywrócony z próby `3` do **`5`**. Dalsze parametry pozostają bez zmian.

Kontrola zależności dla natywnej kalibracji M07:

```text
approach_distance >= safe_z + probe_search_margin - position_min
6.5 >= 5 + 1 - (-0.5) = 6.5  [PASS]
```

**Wynik sprzętowy:** użytkownik potwierdził, że po zapisaniu tych nastaw drukarka **rozpoczęła druk**. To dowód udanego przejścia przez poprzednio odrzucany etap; nie dowód pełnej poprawności mechaniki, siatki lub całego wydruku.

**Ważne ograniczenie bezpieczeństwa:** `position_min: -0.5` dopuszcza ruch platformy o 0,5 mm dalej w kierunku dyszy niż punkt zerowy homingu. Jest to nastawa **dla egzemplarza z potwierdzonym fizycznym zapasem ruchu**, a nie bezwarunkowy standard dla każdej drukarki M300. Nie wyłączać kontroli krańców, nie stosować `FORCE_MOVE`, nie zmieniać `position_endstop` ani offsetu Z dla obejścia błędu. Przed przeniesieniem konfiguracji na inną drukarkę zweryfikować fizyczny zakres i kalibrację kontaktową.

## 4. Dwie różne wysokości bezpieczeństwa — nie mylić

- `[m300_motion] z_contact_clearance: 5`: procedura `ensure_xy_clearance()` zapewnia **minimum 5 mm** wstępnego odsunięcia platformy oraz potwierdza rozwarcie styku PC7 **przed ruchem XY podczas homingu**. Kod wymusza `max(5.0, z_contact_clearance)`.
- `[m300_calibration] safe_z: 5`: wysokość przejazdu pomiędzy punktami **kalibracji M07**. Parametr ten **nie steruje wstępnym odsunięciem PC7 w homingu**.
- `probe_search_margin: 1`: wewnętrzny margines sesji sondowania M07. Zmiana `position_min` z 0 na −0,5 bez podniesienia `approach_distance` z 6,0 na 6,5 powodowała błąd weryfikacji geometrii kalibracji.

## 5. Zachować dotychczasowe zachowanie

- Homing Z poprzez kontakt w centralnym punkcie stołu: **Z=0**; bez sztucznego przesuwania zera.
- Zachować profil `m300_pads`, transformację `bed_mesh`, położenie i wysokość linii purge (X=3, Y=10, Z=0,28), oraz mechaniczne zabezpieczenia.
- `CANCEL_PRINT` zadziałał: głowica zaparkowała, po anulowaniu `STATUS` pokazał `Klipper state: Ready`, a `PRINT_CONTROL_STATUS` `state: IDLE`, `busy: false`.
- `RESUME` po awarii startu nie działa, ponieważ był to stan `FAILED`, a nie `PAUSED`.

## 6. Dodatkowa obserwacja: oczekiwanie na temperatury

Poprzednia próba, w której stół miał temperaturę wyższą od zadanego 30°C, czekała na osiągnięcie temperatur docelowych. Kod `m300_print_control` wymaga od obu grzałek odchyłki nie większej niż ±2°C przez co najmniej 2 s. Jest to **odrębny problem projektowy** (czekanie na naturalne stygnięcie), niepowiązany z błędem ujemnego Z. Nie zmieniać temperatury ręcznie, gdy procedura startu przejęła kontrolę grzałek (`OEM service owns heaters`).

## 7. Dalsza walidacja po zakończeniu bieżącego wydruku

1. Ocenić rzeczywistą jakość pierwszej warstwy/raftu i upewnić się, że platforma nie koliduje z dyszą przy pełnej korekcji.
2. Po zakończeniu wydruku i wyłączeniu grzania sprawdzić `STATUS`, `PRINT_CONTROL_STATUS`, ewentualnie `GET_POSITION` i `BED_MESH_OUTPUT` (odczyt bez ruchu).
3. W oddzielnym teście potwierdzić, że pełna procedura M07, początkowe zwolnienie PC7, Cancel, parkowanie i ponowny start zachowują poprawną geometrię.
4. Nie uruchamiać `RESTART`, instalatora ani aktualizacji na Orange Pi podczas drukowania.

## 8. Repozytorium i zakres zapisu

Te ustalenia są **udokumentowanym wariantem kwalifikowanym dla konkretnego M300 Classic**. Globalne szablony `m300_classic_base.cfg` (`position_min: 0`) oraz `m300_classic_services.cfg` (`safe_z: 5`, `approach_distance: 6.0`) mogą pozostać ustawieniami ostrożnymi dla nowych egzemplarzy. Jeśli wymagane będzie automatyczne zastosowanie wariantu `−0.5 / 6.5`, powinno ono nastąpić dopiero po jawnej kwalifikacji mechanicznej konkretnej drukarki i testach instalatora. Nie należy automatycznie zastępować konfiguracji działającego hosta.

**Źródła kodu:** `M300_HOST_R16_12_NORMAL_UI/payload/m300_print_control.py`, `m300_native_motion.py`, `m300_calibration.py` w gałęzi `orange-pi`. **Źródło danych:** logi Klippera i siatka dostarczone podczas testu 11.11.2026.
