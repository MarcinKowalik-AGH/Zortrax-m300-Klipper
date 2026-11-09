# M300 Classic v1.0.0-beta.15 — naprawa PAUSE/CANCEL i cztery linie startowe

Wersja zastępuje beta.14. Moduł sterowania wydrukiem: `0.13.16.38-PRINT-DRAIN-XY-PURGE`.
Bez zmian: firmware MCU, OLED, kompresja RLE, UART/SPI, limity ruchu, zabezpieczenia termiczne i frontend Fluidd.

## Przyczyna blokady

Poprzednia funkcja `_drained()` wywoływała `get_last_move_time()` co 250 ms. W używanej wersji Klippera ta funkcja nie jest biernym odczytem: przy bezczynnej kolejce ustawia czas ruchu co najmniej 250 ms w przyszłości. Kolejne wywołania przesuwały ten czas bez końca. PAUSE mógł pozostać w WAIT_PAUSE bez parkowania, a CANCEL w WAIT_CANCEL z nadal wstrzymanym wydrukiem.

Poprawka opróżnia tylko faktycznie oczekujące ruchy, a potem sprawdza zakończenie kolejki bez ponownego przesuwania zegara. Nowy test korzysta z czterech niezmienionych metod czasu z przypiętego Klippera i odtwarza poprzednią blokadę. Dawny prosty model testowy nie odtwarzał tego skutku ubocznego.

CANCEL zamyka teraz plik i kasuje natywną pauzę po zatrzymaniu jego wykonawcy, jeszcze przed oczekiwaniem na zakończenie ruchów. Cele temperatur są wyłączane od razu. Parkowanie pozostaje zależne od znanej pozycji i dostępnego prześwitu; brak możliwości parkowania nie pozostawia otwartego, wstrzymanego wydruku.

PAUSE zachowuje punkt X300 Y305, odsunięcie Z o 5 mm w granicach dostępnego zakresu, retrakcję przy gorącej dyszy, utrzymanie stołu i silników oraz terminy 600/1800 s. RESUME dogrzewa do zapisanych temperatur i przywraca pozycję oraz stan wydruku. Nie przeniesiono współrzędnych X509/Y515 z większego CR-10 S5.

## START_PRINT

Dodano wzór z CR-10 S5: dwa odcinki z ekstruzją wzdłuż Y, następnie dwa wzdłuż X, rozstawione o 0,5 mm. Domyślna wysokość to 0,28 mm, długość PURGE to 250 mm. Przejście między parami odbywa się po odsunięciu Z. Żądanie `PURGE=350` jest ograniczane do zakresu M300 z marginesem 5 mm przy dalszej krawędzi; dawka filamentu zależy od rzeczywistej długości odcinka.

Makro przekazuje PURGE i odczytuje temperatury zadane wcześniej przez slicer, o ile nie podano ich jawnie. Zachowano natywne bazowanie M300 i dotychczasową obsługę zapisanej siatki. Nie dodano BLTouch ani Z_TILT_ADJUST. Tryby współrzędnych, prędkość i mnożnik ekstruzji są przywracane również po błędzie linii startowej.

## Aktualizacja

Na bezczynnej drukarce w stanie Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Instalator rozpoznaje moduł beta.14 i aktualizuje tylko znaną fabryczną postać makra START_PRINT. Nie nadpisuje własnych makr ani nieznanych zmian w modułach. Ponowne wgrywanie MCU nie jest potrzebne.

Po instalacji `PRINT_CONTROL_STATUS` powinno pokazać `0.13.16.38-PRINT-DRAIN-XY-PURGE`. Nie aktualizuj podczas wydruku. Zablokowaną starą sesję trzeba bezpiecznie zakończyć przed aktualizacją; restart nie zachowuje możliwości wznowienia tego wydruku.

## Weryfikacja

721 testów hosta, w tym 19 nowych testów zegara kolejki, wywołań używanych przez Fluidd, anulowania, czterech linii i migracji. Publikacja wymaga dodatkowo pomyślnego pełnego przebiegu GitHub Actions: kontroli repozytorium, kompilacji ARM, natywnego Klippy FILEOUTPUT, frontendu oraz sum kontrolnych paczki.

Testy programowe nie zastępują próby na fizycznej drukarce. Pierwszy krótki wydruk należy obserwować: cztery linie startowe, park po PAUSE, powrót po RESUME i zakończenie po CANCEL. Żadne zabezpieczenia ruchu ani grzania nie zostały wyłączone.
