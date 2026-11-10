# M300 Classic beta.22 — ostre ikony menu na OLED i we Fluidd

Wersja zastępuje beta.21. Domyślny wygląd menu: **SHARP-HOST-1**.
To odwracalna zmiana prezentacji po stronie Orange Pi; aplikacja MCU pozostaje
**0.13.14.19-TONED-OLED-UART8**. Nie trzeba ponownie jej wgrywać.

## Co się zmienia

- Wszystkie **24 dodatkowe ikony aktywności (96 klatek)** wracają na ekranie
  dokładnie do ostrych bitmap sprzed cieniowania, bez poświaty i półtonów.
- **37 zestawów OEM (61 klatek)** wyświetla się w wariancie dwupoziomowym:
  wartości 0–7 stają się 0, a 8–15 stają się 15. To progowanie, nie filtr rozmycia.
- Pliki odzyskane z firmware oraz ich sumy kontrolne pozostają nienaruszone.
  Ostry obraz jest osobną, buforowaną reprezentacją; kanoniczne źródła dalej
  przechodzą oryginalne testy zgodności z firmware.
- Home/Move zachowują dotychczasowe jasności migających osi, a logo Klippera
  pozostaje trzytonowe. Są to oznaczenia funkcjonalne, nie dodana poświata.

Tekst, grubość fontu, rytm animacji, wybór ikon, szybki kanał nawigacji,
przyciski ×1/×2/×3, Tune, mesh, ruch, grzanie i procedury druku nie zmieniają się.
Przekształcenie dotyczy tylko bitmapy 50×50. Cache ma limit 64 klatek;
ponowny odczyt tej samej klatki nie przelicza pikseli od nowa.

## Instalacja przez Git — port Fluidd 4480

Przy bezczynnej drukarce w stanie **Ready**, na Orange Pi jako użytkownik klipper:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Odśwież Fluidd przez **Cmd+Shift+R**. W konsoli uruchom `ZORTRAX_UI_STATUS`;
wartość `icon_style` powinna wynosić `SHARP-HOST-1`. W `BUILD_PROVENANCE.json`
paczki ma być beta.22. Aktualizacja używa właściwych sum pakietu i rozpoznaje
poprzednie moduły; **nie nadpisuj ręcznie plików JSON starszym ZIP-em testowym**.
Takie nadpisanie unieważnia manifest i instalator powinien je odrzucić.

Nowy wygląd dotyczy fizycznego OLED przy działającym połączeniu z Klipperem
oraz podglądu Fluidd. **Samodzielne ekrany oczekiwania i błędów MCU nie są
zmienione w tym wydaniu** — zachowują wygląd R14.19. Host nie flashuje MCU.
Nie ma potrzeby wymiany bootloadera, kasowania konfiguracji ani nowego mesh.

## Porównanie z poprzednią wersją bez ponownego wgrywania

W istniejącej sekcji `[m300_menu_ui]` konfiguracji można dodać:

```ini
sharp_icons: False
```

Po zapisaniu i `RESTART` (tylko przy bezczynnej drukarce) wracają źródłowe
odcienie beta.21. `sharp_icons: True` lub brak tego wpisu włącza ostry wariant.
Nie twórz drugiej sekcji o tej samej nazwie. Zmiana jest wyłącznie wizualna.

## Walidacja i granice

Kontrola obejmuje wszystkie 157 klatek, oryginalne hashe OEM, dokładne
odtworzenie 96 klatek beta.20, rozmiar i czas animacji, bezstratny transport,
limit cache, integrację z rzeczywistym rendererem hosta w harnessie testowym,
741 regresji hosta, migrację instalatora i pełną kompilację CI.
Testy programowe nie są oceną wyglądu fizycznego wyświetlacza. Jasne kontury
mogą być bardziej schodkowe na ukośnych liniach — to zamierzony skutek
rezygnacji z półtonów. Oceniaj przede wszystkim przy ×1 na drukarce.

Instrukcja 65 ekranów pozostaje oznaczonym punktem odniesienia beta.20;
działania funkcji nie zmieniają się. Ten dodatek opisuje nowy wariant grafiki.
