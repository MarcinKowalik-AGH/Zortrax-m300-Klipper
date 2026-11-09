# Zortrax M300 Classic — pierwsza instalacja

[Wydanie v1.0.0-beta.13](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.0-beta.13) ·
[Instalacja od pustego Raspberry Pi / Orange Pi](docs/pl/FIRST_INSTALL.md) ·
[Pełny opis projektu po angielsku](README.md)

**Beta.13:** Podgląd OLED odświeża się szybciej przez osobny,
wyłącznie odczytowy odczyt statusu Moonraker WebSocket, niezależny
od subskrypcji aktualizowanej co około 250 ms. Nie wysyła równoległych
zapytań, a po zwinięciu lub ukryciu przeglądarki przerywa odświeżanie.
Obraz jest teraz rysowany na canvas 256×64 i pozostaje widoczny do
czasu dekodowania następnej klatki, bez pustych miejsc w trakcie
animacji. Szerokość podglądu 50% nie zmienia się. Bez zmian w transmisji
RLE/DMA/UART/SPI i MCU.
[Dokumentacja beta.13](docs/pl/RELEASE_v1.0.0-beta.13.md).

**Beta.12:** Podgląd OLED w karcie temperatur zmniejszono do **50% jej
szerokości** i wyśrodkowano. Zlikwidowano dodatkowe oczekiwanie na ACK
całej klatki: Fluidd otrzymuje ostatni obraz wyrenderowany na Orange Pi.
Obrazy są scalane bez kolejki, publikowane z interwałem co najmniej 125 ms;
wykorzystywana jest szybka, bezstratna kompresja PNG. Fizyczny OLED nadal
korzysta z niezmienionej kompresji RLE/DMA i potwierdzeń ACK. Podgląd hosta
może nieznacznie wyprzedzać fizyczny OLED.
[Opis i aktualizacja](docs/pl/RELEASE_v1.0.0-beta.12.md).

**Beta.11:** Fluidd ma podgląd ostatniej potwierdzonej przez ACK klatki OLED
(256×64, 16 poziomów jasności) bezpośrednio pod wykresem temperatur,
na szerokość karty. Podgląd można zwinąć; w razie utraty łącza informuje,
że lokalny ekran MCU nie jest dostępny. Dane idą przez już istniejący
status Moonraker, bez dodatkowych odczytów MCU, do 2 razy na sekundę.
Kompresja RLE, DMA, UART, SPI, bazowanie, grzałki i buzzer bez zmian.
[Instrukcja aktualizacji](docs/pl/RELEASE_v1.0.0-beta.11.md).

Beta.10 wyrównuje grubość i jasność obrysów ikon do grafiki oryginalnego firmware 50×50; usuwa animowany element pod platformą ikony Klippera, zachowując ruch głowicy i pełny trójtonowy znak z napisem „klipper”. MCU zachowuje natywny format 4bpp i ma dodatkową walidację poziomów 7/11/15. Nie zmieniano buzzera, jego czasu ani konfiguracji. Beta.9 dodaje osobne bazowanie Home X i Home Y przez wspólne procedury OLED/Fluidd, zachowuje zaznaczoną pozycję w menu oraz wprowadza pełne logo z napisem „klipper” wewnątrz ikony drukarki (trzy poziomy jasności OLED). Home Z wymaga zbazowanych X i Y, które można uzyskać osobno lub przez Home XY. Zachowano zabezpieczenia Z i odstęp 5 mm. Wersja beta.8 zastępuje literę K w ikonie Klippera właściwym znakiem V/dyszy, wprowadza krótki sygnał 35 ms przy wejściu i zwykłym wyjściu oraz dłuższy 140 ms przy Back. Wyłączenie buzzera działa także podczas sygnału. Zawiera wszystkie poprawki beta.7. Wcześniejsza beta.7 poprawia instalator: rozpoznaje zweryfikowane pliki beta.4 i beta.5, które beta.6 błędnie odrzucała jako nieznane. Nadal chroni przed nadpisaniem własnych zmian i wymaga bezczynnej drukarki w stanie Ready. Zawiera również wszystkie zmiany ikon/menu z beta.6 i siatki stołu z beta.5.
[Zmiany i aktualizacja działającej drukarki po polsku](docs/pl/RELEASE_v1.0.0-beta.10.md).
Poprawka odzyskiwania ACK ekranu z beta.4 pozostaje zawarta.
