# M300 — aktualna obsługa START, PAUSE, RESUME, CANCEL i END

[Instrukcja główna](../../README_PL.md) · [Rejestr odbiorów](ACCEPTANCE_REGISTER.md) · [Mesh](BED_MESH_AND_LEVELING.md)

**Stan instrukcji: beta.24, ustalenia testu z 11 listopada 2026.** Kontroler druku pozostaje
`0.13.16.38-PRINT-DRAIN-XY-PURGE`; niniejsza aktualizacja porządkuje opis,
nie zmienia ruchów drukarki. [Kod kontrolera](../../host/klippy/extras/m300_print_control.py)
i [makra](../../host/config/m300_operations.cfg) są źródłem parametrów.

Opis starszego kontrolera `.29`, pojedynczej linii 40 mm i dawnych wartości
znajduje się w [archiwum](PRINT_CONTROL_LEGACY_R16_29.md). **Nie należy już
kopiować go jako aktualnej konfiguracji.**

## Aktualizacja działającej instalacji

Przy bezczynnej drukarce **Ready**, bez pauzy ani aktywnej procedury, na Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Beta.23 preferuje port 4480 i zapisuje zweryfikowany wybór w katalogu konfiguracji,
w `.m300-installer.json`, poza repozytorium i jego sumami. Następne wywołanie bez
`--port` odczytuje ten zapis i ponownie sprawdza nginx. Nie zmienia portu nginx.
Nie trzeba wgrywać MCU: pozostaje `0.13.14.19-TONED-OLED-UART8`. Instalator hosta
nie programuje MCU. Nie obchodź odmowy nadpisania nieznanych zmian.

## Jedno wywołanie START z OrcaSlicera

```gcode
START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single] MESH=AUTO
```

Końcowy G-code:

```gcode
END_PRINT
```

Nie powielaj w profilu slicera dodatkowego G28, grzania i czterech linii, gdy
wywołujesz wspólny START_PRINT. Dla świadomego wymagania konkretnej siatki użyj
`MESH=m300_pads`; dla świadomego druku bez kompensacji `MESH=NONE`.

## Obecna kolejność START_PRINT: dwie linie Y i dwie X

1. Sprawdzenie temperatur, dostępności profilu i braku konkurencyjnej procedury.
2. Przygotowanie natywnego pliku oraz nagrzewanie dyszy i stołu do zadanych celów.
   Włączone Full platform preheating dodaje skonfigurowaną stabilizację (domyślnie
   60 s); nie jest pomiarem temperatury każdego miejsca powierzchni stołu.
3. Wspólne bazowanie M300. Z korzysta z dotychczasowej procedury kontaktowej i
   minimum 180°C, nie obniżając wyższego celu drukowania.
4. **Po bazowaniu** załadowanie i aktywacja wybranego profilu bed_mesh. `AUTO`
   oznacza `m300_pads`, gdy profil istnieje; przy jego braku **NONE, bez kompensacji**.
   Jawna nieistniejąca nazwa jest odrzucana przed rozpoczęciem operacji.
5. **Cztery odcinki z ekstruzją: Y tam i z powrotem, następnie X tam i z powrotem
   (2Y + 2X).** Pomiędzy parami wykonywane jest uniesienie/odsunięcie Z.
6. Odtworzenie trybów parsera, mnożników i wznowienie wykonania właściwego pliku.

Ruchy rozruchowe przechodzą przez natywny G-code i aktywną transformację mesh.
To nie jest obejście kompensacji przez bezpośrednie manual_move. Podczas rozruchu
używane są G90, M83 i mnożniki M220/M221 = 100%; wcześniejszy stan parsera jest
odtwarzany również przy przerwaniu. Nowy pomiar 25 pozycji **nie jest wykonywany
przy każdym wydruku**.

### Domyślna geometria w kodzie, nie nakaz nadpisania własnych nastaw

| Parametr | Wartość domyślna i znaczenie |
|---|---|
| `purge_length` | 250 mm; odniesienie do długości i obliczenia dawki |
| `purge_filament` | `20 × purge_length / 350`, czyli około 14,286 mm filamentu dla 250 mm odniesienia |
| `purge_height` | 0,28 mm |
| `PURGE` w komendzie | Żądana długość, dalej ograniczana do rzeczywistego pola osi |
| Początek pary Y | `X_min+3`, `Y_min+10`; powrót z przesunięciem X o 0,5 mm |
| Początek pary X | `X_min+3`, `Y_min+20`; powrót z przesunięciem Y o 0,5 mm |
| Daleka krawędź | Nie bliżej niż 5 mm od rzeczywistego maksimum osi |
| Z przed przemieszczeniem | 5 mm w układzie użytym przez procedurę; dodatnie Z odsuwa stół |

Dawka jest proporcjonalna do **faktycznej długości każdego odcinka**, a nie
stała po skróceniu do granic M300. `PURGE=350` nie robi z M300 stołu CR-10 S5.
Początek Y i odniesienie końca Y różnią się o 10 mm, dlatego nie należy obiecywać
czterech odcinków dokładnie po 250 mm. Istniejące własne nastawy pozostają
w konfiguracji; ta aktualizacja dokumentacji ich nie zmienia.

## Pauza, wznowienie, zakończenie

| Wywołanie | Zachowanie |
|---|---|
| PAUSE / przycisk Fluidd / odpowiednik OLED | Zatrzymanie czytnika, zapis PAUSE_STATE, opróżnienie rzeczywistej kolejki, gorąca retrakcja, odsunięcie i parkowanie |
| RESUME | Przywrócenie celów, dogrzanie, bezpieczny powrót i odtworzenie stanu tego samego pliku; brak automatycznego G28 nad modelem |
| CANCEL_PRINT | Przerwanie operacji i wyłączenie celów grzania; zamknięcie zatrzymanego pliku i usunięcie pauzy **nie czekają na parkowanie**; parkowanie jest etapem warunkowym |
| END_PRINT | Opróżnienie kolejki, zakończenie, parkowanie w granicach ważnej pozycji, grzałki i nawiew modelu OFF |
| M600 / ZORTRAX_CHANGE | Wspólna pauza, wymiana, potwierdzenie wypływu i dopiero osobne RESUME |

Domyślne parkowanie to X300/Y305, odsunięcie Z o 5 mm i gorąca retrakcja 2 mm.
Przy braku bezpiecznego prześwitu nie należy wymuszać przejazdu nad modelem.
Pauza zachowuje stół i pozycję; domyślnie po 600 s obniża wyższy cel dyszy do
150°C, a po 1800 s wyłącza jej cel. To parametry konfigurowalne, nie obietnica
nieskończonego bezpiecznego pozostawiania rozgrzanej drukarki bez nadzoru.

Wyłączenie silników, zmiana pliku, restart lub utrata pozycji unieważniają
bezpieczne wznowienie. Nie odblokowuj go przez ręczne nadpisywanie PAUSE_STATE.
Zabezpieczenia grzania, autonomiczne chłodzenie MCU i sygnalizacja błędów
pozostają niezależne od wyłączenia nawiewu modelu.

## Kontrola i odbiór

`PRINT_CONTROL_STATUS` podaje bieżącą fazę i cele. `BED_MESH_OUTPUT` pozwala
odczytać aktywną siatkę bez nowego sondowania. Sam kolorowy podgląd profilu we
Fluidd nie jest dowodem włączenia kompensacji. Rejestrowanie rzeczywistych prób
odbywa się w [rejestrze](ACCEPTANCE_REGISTER.md): start, pauza, wznowienie,
anulowanie w różnych fazach, wymiana i zakończenie mają osobne pozycje.

Programowe testy i udana kompilacja nie są odbiorem ruchów ani pierwszej warstwy
na Twojej drukarce. Wpis bez potwierdzenia użytkownika pozostaje oczekujący.
Nie przypisujemy tu nowych wyników testów sprzętowych.


## Ujemne Z po transformacji mesh — kwalifikowany egzemplarz

Dla zgłoszonego pierwszego startu Z0,28 po korekcji -0,369086 dawało -0,089086 mm.
[Dodatek beta.24](RELEASE_v1.0.0-rc.1.md) opisuje jawny profil position_min=-0,5,
safe_z=5, approach_distance=6,5 oraz homing clearance=2. Nie usuwa mesh i nie
przenosi purge. Zwykła aktualizacja nie narzuca ujemnego zakresu innym drukarkom.
