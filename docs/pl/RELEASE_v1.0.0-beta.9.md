# M300 Classic v1.0.0-beta.9 — Home X i Home Y oraz pełne logo Klippera

Naprawiono problem, przez który po wybraniu `Home X` lub `Home Y` na
ekranie OLED zaznaczenie przeskakiwało na `Back`.
Obie opcje działają teraz przez te same procedury co makra we Fluiddzie:
`ZORTRAX_HOME_X` → `G28 X` oraz `ZORTRAX_HOME_Y` → `G28 Y`.
Zachowano również `Home XY`, `Home Z` i `Home XYZ`.

**Ważne:** możesz bazować najpierw X, później Y albo odwrotnie.
Po zbazowaniu obydwu osi możliwe jest samodzielne Home Z. Można też
wykonać Home XY przed Home Z albo od razu Home XYZ.
Po zakończeniu bazowania pojedynczej osi potwierdzony prześwit i otwarty
PC7 są zachowywane tylko przy niezmienionej pozycji, żeby sekwencja
X → Y → Z nie dodawała kolejnych 5 mm odsunięcia stołu.
Ręczny ruch, utrata referencji Z lub błąd bazowania unieważniają ten stan.

Wymagany prześwit stołu 5 mm, sprawdzenie PC7 i temperatura dyszy
180°C przy bazowaniu Z pozostają bez zmian. Błędny komunikat
`Home XY first, or use G28 for XYZ` zastąpiono jednoznacznym opisem.

W OLED przy Home X/Y/Z/XY/XYZ pozostaje wybrana pozycja; animacje
aktywnej procedury mogą czasowo przełączyć widok, a po zakończeniu
przywracają menu i kursor. Fluidd wyświetla tę samą procedurę oraz
jej fazy.

Ikona Klippera zawiera teraz **pełny symbol V/dyszy i napis „klipper”**
wewnątrz oryginalnego obrysu drukarki 50×50 px. Ujednolicono
rozmiar i grubość z odzyskanymi oryginalnymi ikonami, stosując trzy
poziomy jasności OLED (7, 11 i 15) odwzorowujące ciemnoszary,
czerwony i jasny kolor logo. Zachowano animację głowicy u góry.
[Wzór SVG](../assets/menu-symbols/klipper-full-logo-50x50.svg).

Wszystkie poprzednie poprawki, w tym krótkie 35 ms i długie 140 ms
sygnały menu, pozostają. Firmware MCU i bootloader nie wymagają
ponownego wgrywania.

Przy stanie Ready i bezczynnym druku na Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Następnie odśwież Fluidd (Cmd+Shift+R). Wymagana walidacja wydania:
692 testów hosta, scenariusze G28, kompilacja STM32 i Fluidd oraz
kontrola sum SHA-256. Testy nie zastępują nadzorowanego sprawdzenia
fizycznego ruchu głowicy i stołu na drukarce.
