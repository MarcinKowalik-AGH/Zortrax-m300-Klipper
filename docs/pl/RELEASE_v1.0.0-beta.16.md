# M300 Classic v1.0.0-beta.16 — szybka aktualizacja zaznaczenia menu

Wersja zastępuje beta.15. Rewizja API podglądu: `NAV-EVENT-1`.

## Co poprawiono

Poprawka dotyczy opóźnienia między obrotem fizycznego pokrętła a zmianą
zaznaczonego wiersza w podglądzie Fluidd. Nie zwiększa liczby klatek animacji.
Zachowano ikony, animacje, rozmiar 344 × 86 px, fizyczny OLED, MCU, UART,
SPI, RLE, potwierdzenia ACK, limity ruchu i zabezpieczenia termiczne.
Wszystkie poprawki PAUSE/CANCEL oraz cztery linie START z beta.15 pozostają.

Po przygotowaniu nowego widoku przez istniejący renderer Orange Pi budzi
osobne, wyłącznie odczytowe żądanie `m300/oled_preview/wait`. Fluidd utrzymuje
jedno takie oczekujące żądanie przez swoje dotychczasowe, autoryzowane
połączenie WebSocket z Moonrakerem. Odpowiedź przychodzi po zmianie menu,
a nie dopiero przy okresowym odczycie statusów co 250 ms. Omija też
buforowanie zwykłych powiadomień o statusie we Fluidd.

Nie jest to kolejne częste odpytywanie. Bez zmian w menu żądanie czeka
maksymalnie 10 sekund, po czym jest odnawiane. Po zmianie pozycji kończy się
od razu. Następne żądanie rozpoczyna się po obsłużeniu obrazu przez
przeglądarkę. Nie potrzeba nowej usługi, portu, komponentu Moonrakera,
zmian konfiguracji sieci ani wyłączenia uwierzytelniania.

Przy szybkim przewinięciu od pierwszej do ostatniej pozycji zachowywany jest
najnowszy stan, bez odtwarzania kolejki starych zaznaczeń. Pojedynczy przeskok
nie czeka na zakończenie obracania pokrętłem. Nie pomija się kliknięć ani
nie zmienia dotychczasowych zabezpieczeń wyboru funkcji na drukarce.

Nowa pozycja omija limit pamięci podręcznej obrazu 125 ms, ale wykorzystuje
dokładnie te same piksele już przygotowane na hoście. Animacje nadal używają
dotychczasowego rytmu aktualizacji. Numer obrazu i identyfikator sesji
chronią przed cofnięciem zaznaczenia przez starszy status lub poprzednią
sesję Klippera. Spóźnione dekodowanie PNG nie może nadpisać nowszego obrazu.
Zwinięcie podglądu lub ukrycie karty przerywa jej oczekiwanie; ponowne
połączenie otrzymuje nowy identyfikator. Host dopuszcza maksymalnie osiem
oczekujących żądań. W razie niedostępności szybkiej ścieżki pozostaje
podgląd okresowy.

Sprostowanie wcześniejszego opisu beta.13: zapytania wykonywane co 85 ms
nie omijały wspólnego cyklu statusów Klippera. Beta.16 używa osobnego
punktu API właśnie po to, by usunąć to oczekiwanie dla nawigacji.

## Aktualizacja

Na bezczynnej drukarce w stanie **Ready**:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Następnie odśwież Fluidd skrótem **Cmd+Shift+R**. Nie trzeba wgrywać MCU.
Instalator rozpoznaje zweryfikowane moduły OLED z beta.15. Nadal odmawia
nadpisywania nieznanych lokalnych modyfikacji.

W konsoli Fluidd polecenie `ZORTRAX_OLED_STATUS` powinno pokazać wewnątrz
`oled_preview` pole `navigation_api` o wartości `NAV-EVENT-1` oraz liczniki
`navigation_waiters` i `navigation_delivered`. Przy widocznym podglądzie
obracanie pokrętłem powinno zwiększać `navigation_delivered`. Atrybut HTML
`data-navigation` sekcji podglądu ma wartość `event` dla działającego kanału
zdarzeniowego albo `fallback` dla ścieżki okresowej. To informacja
techniczna, nie dodatkowy przycisk. Rewizja sterowania wydrukiem nie zmienia
się względem beta.15.

## Testy i ograniczenia

Zestaw hosta obejmuje **741 testów**, w tym 20 nowych testów nawigacji,
szybkiego przewijania, wolnego odbiorcy, anulowania oczekiwania, starych
stanów, niezmienności renderera i zgodności aktualizacji. Osobny test
wykorzystuje rzeczywisty reaktor i parser WebRequest przypiętej wersji
Klippera: pojedynczy przeskok, serię pierwsza–ostatnia i ukrycie podglądu.
Raport znajduje się w `REPORTS/OLED_NAVIGATION.json`. Podane tam czasy
mierzą wyłącznie przekazanie zdarzenia do odpowiedzi w środowisku testowym,
a nie opóźnienie od fizycznego pokrętła do przeglądarki.

Testy frontendu sprawdzają m.in. brak dodatkowego interwału po przeskoku,
jedno oczekujące żądanie, wolne rysowanie, ponowne połączenie, odrzucanie
starych stanów i spóźnionych PNG, ukrywanie podglądu oraz stały rozmiar.
Pełna publikacja wymaga także przejścia TypeScript, ESLint, kompilacji
produkcyjnej Fluidd, kompilacji MCU ARM, natywnego Klippy FILEOUTPUT oraz
kontroli sum paczki. Pełne budowanie uruchamia się również przed scaleniem
pull requestu.

CI nie obsługuje fizycznej drukarki ani Twojej przeglądarki. Po instalacji
należy sprawdzić pojedynczy szybki przeskok, przewinięcie od pierwszej do
ostatniej pozycji, zatrzymanie na końcu i obrót połączony z kliknięciem,
najpierw na postoju, następnie podczas krótkiego nadzorowanego wydruku.
Wygląd i rytm animacji powinny pozostać takie same.
