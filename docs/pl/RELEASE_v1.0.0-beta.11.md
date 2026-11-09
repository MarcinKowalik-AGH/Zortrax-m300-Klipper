# Zortrax M300 Classic — v1.0.0-beta.11: ekran OLED we Fluidd

Dodano **podgląd rzeczywistej klatki OLED bezpośrednio pod wykresem
temperatur** w karcie Temperature na Dashboard Fluidd. Widok ma szerokość
karty i proporcję 4:1 (oryginalne 256×64 px), zachowuje 16 stopni jasności
i można go zwinąć. Jest tylko do odczytu — brak sterowania drukarką.

Nie jest to symulacja menu: po stronie Klippera pobierana jest wyłącznie
**ostatnia kompletna klatka potwierdzona przez ACK**, zapisana w
`stream.previous`. Maksymalnie 2 razy na sekundę host koduje ją do
bezstratnego PNG z 4-bitową paletą i przekazuje przez istniejącą
subskrypcję statusu Moonraker. Nie wykonuje żadnych dodatkowych operacji
przez MCU, SPI czy UART. Nie wprowadza nowych portów, komend sterujących
ani dodatkowych zapytań do drukarki.

Jeżeli MCU przejdzie na własny awaryjny ekran podczas utraty połączenia,
Fluidd pokaże komunikat o niedostępnym podglądzie. Nie twierdzimy, że
podgląd stanowi fizyczny odczyt matrycy OLED.

**Kompresja RLE/PackBits, bloki różnicowe, DMA, ACK, prędkości komunikacji,
buzzer, wentylatory, bazowanie X/Y/Z i wszystkie zabezpieczenia pozostają
niezmienione. MCU nie wymaga ponownego wgrywania.**

Aktualizacja przy bezczynnej M300 i statusie Klipper Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Następnie odśwież Fluidd: Cmd+Shift+R.

Wydanie wymaga 699 testów hosta, testów nowego PNG/ACK/2Hz,
testów starych procedur, kompilacji STM32F103 i Fluidd,
weryfikacji TypeScript oraz pełnej walidacji GitHub Actions.
