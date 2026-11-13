# Instalator M300, port Fluidd i ponawianie CI

[Instrukcja główna](../../README_PL.md) · [Pierwsza instalacja](FIRST_INSTALL.md) · [Aktualizacja](INSTALL.md) · [Rejestr odbiorów](ACCEPTANCE_REGISTER.md)

## Port Fluidd 4480

M300 używa **4480**. Instalator wdraża Fluidd do katalogu wskazanego przez
istniejącą konfigurację nginx. Na nowym hoście ustaw port 4480 w KIAUH
zgodnie z [instrukcją pierwszej instalacji](FIRST_INSTALL.md#2-kiauh-i-przygotowanie-usług).

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Uruchom z konta Klippera, przy bezczynnej maszynie Ready i wyłączonych celach
grzania. Wstrzymany wydruk również blokuje instalację. W razie konfliktu
lokalnych plików zachowaj je i sprawdź komunikat przed ponowną próbą.

Instalator sprawdza porty `listen`, katalog `root` lub `alias` i tytuł Fluidd
w `index.html`. IPv4 i IPv6 prowadzące do tego samego katalogu są jednym
wyborem. Jeśli niestandardowej konfiguracji nginx nie można odczytać
automatycznie, wskaż `--fluidd-root /bezwzględna/ścieżka --port 4480`.
Ścieżka musi prowadzić do katalogu aktywnego Fluidd.

Po udanym wdrożeniu instalator zapisuje **`.m300-installer.json`** obok
aktywnego `printer.cfg`, zazwyczaj w `~/printer_data/config`. Plik zawiera
wersję schematu, port i katalog. Gdy polecenie pomija jawny wybór, instalator
weryfikuje ten zapis względem nginx. Bez zapisu sprawdza port 4480, a
następnie szuka jednego jednoznacznego Fluidd. Obsługuje także konfiguracje
legacy na innych portach.

`FLUIDD_ENDPOINT_SELECTED` pokazuje katalog, port i źródło wyboru.
Wynik `INSTALLED_M300_HOST` podaje także ścieżki potwierdzeń i kopii,
jeśli zmieniono hosta lub Fluidd. Przy pierwszej instalacji polecenie bez
`--apply` wyświetla plan bez zapisu ustawień. Aktualizacja MCU jest osobnym
krokiem opisanym w [instrukcji firmware](MCU_FIRMWARE_1.0.5.md).

## Retry GitHub Actions: tylko awarie przejściowe

Workflow **Retry recognized transient M300 failures** reaguje na zakończony
niepowodzeniem pełny build lub publikację wersji. Korzysta z kodu **zaufanej
gałęzi domyślnej**, nie z kodu pobranego z nieudanego PR ani z jego artefaktów.
Logi są danymi: nie są uruchamiane jako skrypt. Uprawnienia ograniczono do
odczytu źródeł oraz actions:write niezbędnego do ponowienia.

Najwyżej **3 próby tego samego przebiegu łącznie**: początkowa i dwa automatyczne
ponowienia. Przerwy to 30 i 60 s. Ponawiane są nieudane zadania i ich zależności
przez oficjalny endpoint rerun-failed-jobs. Poprzednie nieudane próby i ich
maile nie znikają; raport wskazuje źródłowy SHA i numer próby.

| Zdarzenie | Decyzja |
|---|---|
| Rozpoznany DNS, reset połączenia, HTTP 429/500/502/503/504 w dopuszczonym kroku sieciowym | Możliwe ograniczone ponowienie |
| Błąd testu, TypeScript/ESLint, kompilatora, linkera, sumy, podpisu, uprawnień, brak miejsca | Bez ponowienia; poprawa przyczyny |
| Nieznany błąd, brak pełnego logu, niejasna faza, timeout całego zadania lub anulowanie | Bez automatycznego ponowienia |
| PR z forka, zamknięty PR, nowszy commit lub już ponawiana próba | Odmowa |

Każdy nieudany krok musi kwalifikować się do ponowienia. Błąd testu ma
pierwszeństwo nawet wtedy, gdy w tym samym kroku jest też komunikat sieciowy.
Nie ma `continue-on-error`, usuwania testów ani automatycznego edytowania kodu.
Budowanie i weryfikacja MCU sprawdzają limity linkera oraz granicę obszaru
aplikacji w mapie Flash. Udany build i zgodny SHA są warunkiem publikacji
gałęzi `orange-pi` oraz ZIP-a.

Decyzja jest zapisywana jako `CI_RETRY_DECISION.json`, w podsumowaniu i
artefakcie workflow. Błąd samej klasyfikacji kończy się **bez ponowienia**.
Automat nie ponawia sam siebie. Forki i duże/niedostępne logi wymagają oceny
operatora. Mechanizm zaczyna działać dla nowych zdarzeń dopiero po scaleniu
pliku workflow na domyślną gałąź.

Testy polityki używają symulowanej odpowiedzi API i sprawdzają także
niewysyłanie tokenu do serwera pobierania logów, nowszy commit w trakcie
oczekiwania i brak POST w trybie domyślnym. Nie wymuszają rzeczywistej awarii
sieci ani nie wywołują testowych restartów drukarki.

Podstawa API: [ponawianie nieudanych zadań](https://docs.github.com/en/rest/actions/workflow-runs#re-run-failed-jobs-from-a-workflow-run),
[zasady workflow_run](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run).

## Uzupełnienie RC2: aktualizacje Moonrakera i systemu

[Ocena dokładnego commita Moonrakera i pakietów zgłoszonych 12 listopada](RELEASE_v1.0.0-rc.2.md) rozdziela aktualizację portu M300, Moonrakera i sprzętowej części Armbiana. Nie używaj Update All. Samo `klipper {}` ze skróconego odczytu nie potwierdza aktualności repozytorium.
