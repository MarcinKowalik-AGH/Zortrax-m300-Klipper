# Instalator, port Fluidd i ograniczone ponawianie CI — beta.23

[Instrukcja główna](../../README_PL.md) · [START i druk](PRINT_CONTROL.md) · [Rejestr odbiorów](ACCEPTANCE_REGISTER.md)

## Wybór portu bez powrotu do błędu 4080

Obowiązującym portem M300 użytkownika jest **4480**. Aktualizacja nie przestawia
nginx, Moonrakera, UART ani drukarki. Wskazuje wyłącznie istniejący katalog
interfejsu, do którego zostanie wdrożony zweryfikowany Fluidd.

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Uruchom jako użytkownik klipper, nie jako root, wyłącznie przy bezczynnej
maszynie Ready. Wstrzymany wydruk również blokuje instalację. W razie konfliktu
lokalnych plików nie wykonuj reset --hard ani nie omijaj SHA256SUMS.

Po przejściu na beta.23 parametr można pominąć: instalator korzysta kolejno z
jawnego `--port`/`--fluidd-root`, sprawdzonego lokalnego zapisu, portu **4480**,
a gdy go brak — jednej jednoznacznej instalacji Fluidd wykrytej w nginx.
Istniejący pojedynczy serwer na 4080 lub 80 nie jest przenoszony. Przy dwóch
kandydatach lub niejednoznacznym katalogu następuje odmowa, nie losowy wybór.

Weryfikacja obejmuje zwykły katalog interfejsu, tytuł Fluidd w index.html,
porty listen i katalog root/alias. IPv4 i IPv6 dla tej samej instalacji nie
są dwiema drukarkami. Do trudniejszych konfiguracji nginx pozostaje jawne
`--fluidd-root /pełna/ścieżka --port 4480`; nadal trzeba wskazać prawdziwy
katalog Fluidd, a nie katalog źródeł Git czy konfigurację drukarki.

Po udanym wdrożeniu zapisywany jest plik **`.m300-installer.json` w katalogu
z aktywnym printer.cfg** (zwykle `~/printer_data/config`). Zawiera tylko wersję
schematu, port i ścieżkę katalogu, bez haseł. Powstaje atomowo po zakończeniu
aktualizacji. Nie należy dodawać go do repozytorium paczki. Kolejna instalacja
ponownie weryfikuje zapis względem nginx. Po świadomej zmianie portu wskaż nowy
`--port`; jawny wybór zastępuje stary zapis dopiero po sukcesie.

Także instalator pierwszego uruchomienia korzysta z tego samego wykrywania.
Próba planowania bez `--apply` nie zapisuje ustawień. Pierwsza instalacja KIAUH
na 80 pozostaje na 80, dopóki operator sam nie zmieni nginx.

Komunikat `FLUIDD_ENDPOINT_SELECTED` pokazuje wybrany katalog, port i źródło
wyboru. Wynik końcowy podaje lokalizację zapisu. Polecenie nie flashuje MCU.

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
Nie zwiększamy limitów pamięci MCU, by ukryć błąd linkowania. Udany build i
zgodny SHA pozostają warunkiem publikacji gałęzi orange-pi oraz ZIP-a.

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
