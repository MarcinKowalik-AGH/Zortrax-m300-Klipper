# Audyt końcowy M300 Classic — 21.11.2026

Autor: Marcin Kowalik <mkowalik@agh.edu.pl>.

Wydanie źródeł **1.0.0**, MCU **1.0.8**. Punktem wyjścia jest RC34,
commit `38e1c70e5ed7c974c709b9923613e22994832e57`.
Zakres obejmuje klasyczne M300: procedury hosta, zgodność makr, OLED i Fluidd,
obsługę anulowania i błędów, konfigurację, pamięć oraz składanie i publikację
wydania. M300 Plus, Dual i obrazy A33 są odrębnymi celami.

**Wniosek:** przegląd wykrył i poprawił niedomkniętą granicę pomiędzy
odrzuceniem żądania wymiany filamentu a rozpoczęciem procedury oraz brakujące
rozpoznanie poprzedniego hosta w migracji. Pozostałe
sprawdzone scenariusze zachowują końcowy stan, właściciela zasobów i istniejące
zabezpieczenia. Pełnej poprawności fizycznej każdego przebiegu nie można
potwierdzić samym przeglądem źródeł. Otwarte odbiory pozostają w
[jedynym bieżącym rejestrze sprzętowym](ACCEPTANCE_REGISTER.md).

## Źródła i kolejność ich stosowania

| Materiał | Zastosowanie |
|---|---|
| Bieżące źródła RC34 i poprawki 1.0.0 | Właściciele zasobów, rzeczywiste polecenia, stan końcowy i warunki odrzucenia |
| `ZORTRAX_M300_ABCD_SPECYFIKACJA_DOWODY_2026-10-19.zip`, specyfikacja A–D i audyt pauzy | Odcięcie energii, temperatura przed każdym odcinkiem E, tożsamość pliku/pauzy, granice rekonstrukcji OEM |
| `ZORTRAX_M300_KLIPPER_AUDYT_WYTYCZNE_2026-10-23.pdf` | Mapa I/O, pamięć i rozdzielenie dowodów programowych od kwalifikacji egzemplarza; historyczny stan portu |
| [Audyt konfiguracji](../en/CONFIGURATION_AUDIT.md), [audyt błędów](../en/PROCEDURE_ERROR_AUDIT.md), [RC1](CODE_REVIEW_RC1.md), [RC20](AUDYT_RC20.md) | Zachowane wymagania migracji, sprzątania, sygnalizacji błędów i zapisów NVM |
| [Aktualny spis procedur](../en/PROCEDURE_INVENTORY.md), makra i ich testy | Zgodność wejść OLED, Fluidd i konsoli z tym samym kontrolerem |
| [Rejestr odbiorów](ACCEPTANCE_REGISTER.md) | Wyłączne źródło potwierdzonych wyników na drukarce; starsze obserwacje nie otrzymują nowej wersji |

Historyczne stwierdzenia o nieistniejącym jeszcze porcie lub bootloaderze nie
opisują obecnego stanu. Bieżący bootloader jest osobnym projektem; aktualizacja
hosta 1.0.0 nie wymaga jego ponownej instalacji. Profile Orca nadal wywołują
`START_PRINT ... MESH=AUTO`, `END_PRINT` i `PAUSE`.

## Sprawdzenie procedur

| Procedura | Zakończenie i sprzątanie | Główne regresje |
|---|---|---|
| Home X/Y/XY/Z/XYZ | Natywne limity i kontakt PC7; kontakt ma ograniczony zakres, utrata sesji odbiera prawo ruchu | `test_normal_operations`, `test_native_z_release`, `test_procedure_errors` |
| Autocalibration M07 | Potwierdzenia i terminy; zapis dopiero pełnej zaakceptowanej obserwacji; awaria wyłącza grzanie | `test_native_leveling`, `test_leveling_oem`, `test_procedure_return` |
| Bed Mesh, 25 kontaktów | Kontrola temperatury i otwarcia PC7 przed XY; błędna rama Z jest unieważniana; profil dopiero po pomiarze | `test_pad_mesh`, `test_pad_probe_window`, `test_pad_live_heights` |
| START_PRINT | Grzanie, retrakcja, bazowanie, wybór siatki, 2Y + 2X; oczekiwanie na opróżnienie kolejki przed plikiem | `test_print_control`, rzeczywisty Klippy FILEOUTPUT |
| END_PRINT | Opróżnienie kolejki, opuszczenie stołu w granicach Z, park, grzałki off, natywne EOF | `test_print_drain_purge`, `test_print_control`, `test_native_reprint` |
| PAUSE / RESUME | Ta sama tożsamość pliku i PAUSE_STATE, ważny homing i mesh; dogrzanie oraz kontrolowany powrót | `test_print_control`, `test_print_context` |
| Load / Unload / Change | Ograniczone odcinki E, aktualna temperatura, token i termin; sprzątanie stanu parsera i blokad | `test_native_oem_services`, `test_procedure_temperatures`, `test_print_control` |
| Extrude / Retract w pauzie | Ruch E przy stałym fizycznym XYZ; retrakcja unieważnia potwierdzenie wypływu | `test_print_control` |
| Cancel / restart / odłączenie | Cofnięcie prawa dalszego podawania i grzania; brak automatycznego Resume po utracie sesji | `test_lifecycle`, `test_restart_heartbeat`, `test_print_control` |
| Heat / platforma / przytrzymanie pokrętła | Ograniczone ruchy, lokalny stop MCU po puszczeniu przycisku, przywrócenie dzierżawy po opróżnieniu kolejki | `test_native_oem_services`, `test_native_maintenance_contract` |
| Wentylatory / PID | Chłodzenie ochronne ma pierwszeństwo; koniec testu oddaje sterowanie bieżącej polityce | `test_native_oem_services`, `test_status_lights`, modele MCU w CI |
| SD / G-code / Z-code / Reprint | Migawka pliku i token wyboru; jawny start; anulowanie importu; ponowny druk wyłącznie zweryfikowanego pliku | `test_native_models`, `test_unified_zcode`, `test_native_reprint` |
| NVM / liczniki / ustawienia | Atomowe transakcje i zgodność urządzenia; brak zmiany opublikowanego stanu po błędzie zapisu | `test_runtime_counter`, `test_counter_sync`, `test_settings_information`, modele Flash C |
| OLED / Fluidd / usypianie | Wspólny kontroler, ważność akcji i ACK; gest budzenia jest zużywany; błąd UI nie wznawia napędów | `test_macro_dispatch`, `test_oled_navigation`, `test_oem_sleep`, testy frontend |
| Instalacja / rollback / wydanie | Kontrola sum, praca na postoju, kopia i cofnięcie; publikacja po udanym CI z niezmiennego commitu | Testy instalatorów, `test_repository`, `test_publish_release` |

## Poprawki wykonane w 1.0.0

1. **Odrzucenie przed ruchem.** `M300_CHANGE TEMP=999` na RC34 potrafiło
   zaparkować głowicę, oznaczyć pauzę jako wymagającą wymiany i przejść do
   FAILED. Teraz wspólne `plan_request` sprawdza temperatury, długości i budżet
   przed pauzą lub parkowaniem. Błędna komenda pozostawia aktywny druk bez zmian.
2. **Pauza nie jest zmieniana przez nieprzyjęte żądanie.** `material_begin`
   następuje po kontroli parametrów, gotowości i czujnika. Odrzucona próba
   pozostawia dotychczasowe flagi i możliwość zwykłego Resume.
3. **Zmiana warunków podczas parkowania.** Jeżeli kontrola przed rozpoczęciem
   wymiany odrzuci żądanie po dojechaniu do naroża, kontroler podaje powód
   i pozostawia pauzę. Jeżeli wymiana została przyjęta i następnie zawiodła,
   nadal obowiązują wyłączenie grzania i ścieżka awarii. Wcześniej przerwana
   wymiana nadal wymaga prawidłowego dokończenia przed wznowieniem.
4. **Mniej powielonej walidacji.** Konsola, makra i interfejs korzystają z tego
   samego planowania żądania. Nie dodano odpytywania w pętli kroków ani nowych
   timerów. Nie deklaruje się zmierzonego przyspieszenia ruchu lub UART.
5. **Porządek wydania.** Spis procedur opisuje MCU 1.0.8 i aktualną diagnostykę,
   stare audyty mają datę i punkt odniesienia, odnośniki instalacji prowadzą do
   1.0.0. Publikator rozróżnia finalne wydanie od RC i nie nadpisuje tagów.
6. **Aktualizacja z RC34.** Lista rozpoznanych modułów otrzymała dokładne SHA-256
   trzech zmienionych plików RC34. Instalator przyjmuje wcześniejsze wydanie,
   zachowując odmowę nadpisania własnych zmian operatora. Nowa regresja wykonuje
   aktualizację, ponowny plan, dokładny rollback i odmowę po lokalnej edycji.
   Próba na zrzucie `20261121-095908.zip` zachowała 16 chronionych sekcji,
   wszystkie 41116 bajtów SAVE_CONFIG, brak duplikatów i idempotencję migracji.

## Walidacja i jej granice

Host obejmuje **989 testów**, w tym pięć nowych regresji granicy rozpoczęcia
wymiany i regresję aktualizacji z RC34. Pięć testów publikatora wykonuje rzeczywisty skrypt z lokalnie
modelowanymi odpowiedziami GitHuba: finalne wydanie, RC, istniejące wydanie,
nieudana kompilacja i tag wskazujący inny commit.

Pełny workflow kompiluje STM32F103, weryfikuje słownik i granice aplikacji,
wykonuje modele C ochrony, chłodzenia, kroków i obu dzienników Flash, testuje
hosta na przypiętym Klippym w FILEOUTPUT, migrację konfiguracji, frontend,
dokumentację oraz sumy gotowych paczek. Dokładny wynik jest przypisany do
commitu w [Actions](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/actions/workflows/build-m300.yml).
Publikacja wymaga zakończenia tego workflow z powodzeniem.

W tym audycie nie sterowano fizyczną drukarką. Do potwierdzenia na egzemplarzu
pozostają m.in. powtarzalność Z, pierwsza warstwa na całej płycie oraz pełny
przebieg wymiana → schłodzenie → dogrzanie → potwierdzenie wypływu → retrakcja
→ ponowne potwierdzenie → Resume na finalnej wersji. Dotychczasowe potwierdzenia
Benchy, parkowania i licznika zachowują dokładnie swój historyczny zakres.

[Wydanie i aktualizacja](RELEASE_v1.0.0.md) · [Aktualny rejestr](ACCEPTANCE_REGISTER.md).
