# M300 Classic v1.0.0-beta.17 — szybszy odbiór menu i kwadratowe piksele OLED

Wersja zastępuje beta.16. Rewizja frontendu: `NAV-PIPELINE-2`.
API hosta pozostaje `NAV-EVENT-1`. Kod hosta i MCU, animacje, zwykłe statusy
Klippera/Fluidd, UART/SPI/RLE/ACK oraz procedury druku pozostają bez zmian.
Zachowano naprawy PAUSE/CANCEL, cztery linie START i obsługę zapisanej siatki.

## Równoległy odbiór i rysowanie

Po odebraniu zmiany zaznaczenia przeglądarka od razu rozpoczyna oczekiwanie
na następną, bez czekania na dekodowanie i narysowanie PNG. Nadal istnieje
najwyżej jedno oczekujące zapytanie. Dekoder ma jedną klatkę w trakcie pracy
i najwyżej jedną dodatkową — zawsze najnowszą. Nie odtwarza kolejki starych
zaznaczeń. Spóźniona klatka nie może przywrócić poprzedniego zaznaczenia.
Zwinięcie podglądu, rozłączenie i zamknięcie komponentu unieważniają obrazy.

To optymalizacja szybkiego przewijania, nie zwiększanie częstotliwości animacji.
Rzeczywisty zysk czasowy wymaga pomiaru na drukarce; nie podano niezmierzonej
obietnicy opóźnienia w milisekundach.

## Kwadratowe piksele

Każdy piksel obrazu 256 x 64 jest rysowany jako równy blok N x N pikseli
urządzenia. Wyłączono interpolację. Współczynnik N dobierany jest do gęstości
ekranu i powiększenia strony, blisko dawnej szerokości 344 px CSS. Początek
obrazu jest wyrównywany do siatki pikseli. Cienka ciemna osłona o szerokości
2 pikseli urządzenia oddziela właściwy obraz od wygładzania krawędzi elementu.
Proporcje właściwego obrazu pozostają 4:1.

**Stałe 344 x 86 px CSS ustępuje skalowaniu całkowitoliczbowemu.** Przy DPR 1
właściwy obraz ma 256 x 64 px CSS; przy DPR 2 ma 384 x 96 px CSS, czyli
768 x 192 piksele urządzenia. Do tego dochodzi cienka osłona. Powiększenie
strony zmienia rozmiar skokowo, razem w obu osiach. Samo zwężenie karty nie
zmniejsza obrazu — dostępne jest przewijanie poziome.

Gwarancja dotyczy mapowania rastra aplikacji oraz sprawdzonych zrzutów
przeglądarek. Nie obejmuje lupy systemowej, skalowania pulpitu zdalnego,
zmniejszania zrzutu przez inny program, przekształceń CSS dodanych przez
rozszerzenia ani przejściowego skalowania gestem powiększania.

## Aktualizacja

Na bezczynnej drukarce w stanie **Ready**:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Po instalacji odśwież Fluidd przez **Cmd+Shift+R**. Nie trzeba wgrywać MCU
ani zmieniać konfiguracji Moonrakera. Moduły hosta są identyczne z beta.16.
Element podglądu ma atrybut `data-preview-revision="NAV-PIPELINE-2"` oraz
`data-pixel-scale` z całkowitą skalą. `ZORTRAX_OLED_STATUS` nadal pokazuje
`NAV-EVENT-1` — interfejs hosta nie został zmieniony.

## Walidacja

Publikacja wymaga pełnego CI: 741 testów hosta, natywnego Klippy FILEOUTPUT,
API nawigacji, kompilacji ARM, testów frontendu, ESLint, TypeScript, kompilacji
Fluidd i sum kontrolnych. Dodatkowe testy sprawdzają równoległy odbiór,
serię 1000 aktualizacji bez rosnącej kolejki, nieaktualne dekodowanie, zmianę
DPI oraz zachowanie dotychczasowego rytmu odczytów okresowych.

Raport `REPORTS/OLED_PIXELS.json` porównuje każdy piksel właściwego obrazu
na rzeczywistych zrzutach Chromium i Firefoksa: 15 skal renderera i dwie
ułamkowe szerokości kolumny, łącznie 60 przypadków. Test nie zastępuje próby
na fizycznej drukarce. Po instalacji sprawdź szybkie przewijanie oraz zmianę
powiększenia strony; animacje i pozostałe statusy powinny działać jak wcześniej.
