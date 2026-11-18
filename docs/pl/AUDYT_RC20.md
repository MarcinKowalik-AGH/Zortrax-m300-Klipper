# Audyt M300 Classic przed wersją 1.0

Marcin Kowalik <mkowalik@agh.edu.pl>

| Obszar | Ustalenie i zmiana | Weryfikacja |
|---|---|---|
| Wyświetlacz | Jeden próg obsługiwał zarówno przygaszanie, jak i przejście do uśpienia. Oba progi są teraz niezależne, liczone od ostatniej aktywności. Uwzględniono kontroler wydruku i pomiar siatki. | Ścieżka AWAKE → DIM → powiadomienie → OFF, budzenie, blokada uśpienia podczas pracy. |
| Pamięć MCU | Czasy OLED zachowują się jako jedna para. Dwie strony po 2 KiB zaczynają się za maksymalnym obszarem linkera. Znacznik ważności jest programowany na końcu, a identyczny zapis nie zużywa Flash. | Model dwóch stron, zapisy graniczne, utrata zasilania przy kasowaniu i programowaniu, ponowienie, ponowny odczyt. |
| Historia wydruków | Zakończenie starego zapytania do Moonrakera mogło zwolnić znacznik nowszego zapytania po reconnect. Tylko aktualna generacja kończy swój odczyt. | Testy historii i zmiany sesji. |
| Koszt odpytywania | Ustalenie zajętości nie wymaga budowania całej mapy punktów kalibracji ani szczegółowej odpowiedzi sterownika wentylatorów. | Lekkie odczyty stanu w obsłudze wyświetlacza i arbitrażu zasobów. |
| Logi | Szczegóły udanych operacji sondy, cofnięcia i odczytu sprzętu są konfigurowalne. Błędy i zabezpieczenia mają własne ścieżki raportowania. | Konfiguracja debug w sekcji m300_mcu. |
| Instalacja | Migracja rozpoznaje wcześniejsze skróty plików. Host i aktualizacja katalogu Fluidd mają osobne polecenia. | Sprawdzanie manifestu, testy instalacji, świeży build MCU i Fluidd, test serwowania zasobów. |

## Zakres regresji

Pakiet hosta obejmuje 947 testów. Próby pełnego procesu Klippy używają przypiętego źródła upstream i słownika skompilowanego MCU. Obejmują konwersję G-code i Z-code, druk i wznowienie, siatkę stołu, ograniczenia ruchu, sterowanie grzaniem, odczyt ustawień oraz dostępność obu makr OLED po migracji. Osobne modele C sprawdzają krokowce, ochronę MCU, chłodzenie, kartę SD, przyciski i oba dzienniki Flash. Test komponentu Fluidd sprawdza zakresy, blokadę błędnej kolejności i zapis dopiero po wybraniu Save.

Analiza statyczna modułów hosta i skryptów nie wykazała niezdefiniowanych nazw ani odwołań do niezainicjalizowanych zmiennych lokalnych w kontrolowanych regułach Ruff F821 i F823. Usunięto nieużywane importy, zbędny odczyt stanu filamentu oraz migrację wykonującą zamianę tekstu na ten sam tekst. Nagłówki kontaktowe dodano do źródeł projektu. Dane OEM, pliki porównawcze dla starszych wersji i materiały zewnętrzne zachowują własne pochodzenie.

## Odbiór na drukarce

Na HW05 w RC19 / MCU 1.0.6 operator potwierdził 289224 minuty po fizycznym wyłączeniu i włączeniu, znormalizowane banki i stan CURRENT. Dla RC20 zapisz DIM=1 i SLEEP=2. Poczekaj na SYNCED, sprawdź oba progi na biegu jałowym, pojedynczy gest budzenia i oba paski. Wyłącz drukarkę po potwierdzonym zapisie, włącz i porównaj parę odczytaną z MCU. Podczas druku i pauzy sprawdź czytelność OLED, a po zakończeniu odczytaj fabryczny licznik. Porównaj kontrolki w Fluidd na porcie 4480 z fizycznym panelem. Prób na RC20 na rzeczywistej drukarce jeszcze nie potwierdzono.
