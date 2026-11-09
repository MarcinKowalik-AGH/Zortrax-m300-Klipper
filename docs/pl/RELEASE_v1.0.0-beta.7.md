# M300 v1.0.0-beta.7 — poprawka bezpiecznej aktualizacji z beta.4 i beta.5

W beta.6 występował błąd w instalatorze Orange Pi: pięć plików hosta
z oficjalnych, zweryfikowanych wydań beta.4 i beta.5 nie było uwzględnionych
w `SUPPORTED_BASELINES.json`. Pierwszym z nich był `m300_menu.py`,
dlatego instalator zgłaszał `Existing unknown M300 runtime module`.

**Poprawiono to bez wyłączania zabezpieczenia.** Dodano pięć ściśle
określonych sum SHA-256 z opublikowanych manifestów oraz test regresyjny
porównujący oficjalne beta.4, beta.5 i beta.6 z bieżącą paczką.
Niestandardowe lokalne modyfikacje nadal powodują odmowę z podaniem sumy
SHA-256 wykrytego pliku.

## Aktualizacja istniejącej M300 Classic

Drukarka musi być bezczynna, a Klipper musi mieć stan **Ready**.
Na Orange Pi wykonaj:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Po instalacji odśwież Fluidd przez `Cmd+Shift+R`. Nie wgrywaj ponownie
firmware MCU. Wydanie zachowuje nowe menu Home X/Y/Z/XY/XYZ, migające
ikony kartezjańskie i pamięć pozycji kursora wprowadzone w beta.6.

Jeżeli aktualizacja ponownie zgłosi nieznany plik, odczytaj faktyczną sumę:

```bash
sha256sum /home/klipper/m300-test01-0.13.2/klipper/klippy/extras/m300_menu.py
```

Oficjalny plik beta.4/beta.5 ma SHA-256
`e514682d2701f6cd3a2e13a6b69d971386ab3fe8bdf5442b3764f0261b25e205`.
Jeśli plik ma inną sumę, może zawierać indywidualne poprawki — nie nadpisuj
go bez porównania, nie kasuj pliku i nie wyłączaj kontroli SHA.
Pierwszy komunikat `Wait until Klipper is Ready and the printer is idle`
jest osobnym zabezpieczeniem i pozostaje prawidłowy.

Dla nowej instalacji użyj
[kompletnej instrukcji](FIRST_INSTALL.md).
Badania CI są testami programowymi, nie fizycznym potwierdzeniem
ruchu, temperatur i kontaktu głowicy ze stołem.
